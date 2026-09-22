# pl8-services

Infrastructure (and, eventually, Lambda code) for running
[PL8](https://github.com/dchenstealth/pl8-base) in AWS.

## Status

This repo covers PL8's stateful and eventing backbone plus the
`pl8-interface` Lambda. The `pl8-stream-handler` and `pl8-event-handler`
Lambdas are follow-up slices, not yet implemented here.

## Resources

Managed with [OpenTofu](https://opentofu.org/):

- A DynamoDB table (`PK`/`SK` + `GSI1`) matching the schema
  [`pl8-base`](https://github.com/dchenstealth/pl8-base) expects, with
  DynamoDB Streams enabled
- A custom EventBridge event bus
- An EventBridge rule routing PL8's internal lifecycle events to an SQS
  queue
- An SQS queue (with a dead-letter queue) that a future event-handler
  Lambda will consume from
- The `pl8-interface` Lambda (see below)
- A Lambda layer holding the third-party dependencies shared by every
  function

## Lambda functions

Each function lives under `src/` as a member of one
[uv](https://docs.astral.sh/uv/) workspace, so a single `src/uv.lock` pins
the dependencies of all of them. Those dependencies ship once, in the
`<environment>-pl8-deps` layer that `src/build-layer.sh` installs for arm64
`python3.14`. Each function's own zip holds only its source package.
OpenTofu builds both zips with `archive_file`; fixed file modes and a build
script that strips machine-specific files keep their hashes identical
across rebuilds and machines, so an unchanged function or layer doesn't
redeploy.

### pl8-interface

The interface agents call directly through the Lambda `Invoke` API (IAM
authenticated, no API Gateway), typically via `pl8-cli`. It validates each
request and dispatches it onto [`pl8-base`](https://github.com/dchenstealth/pl8-base).
See [`src/pl8-interface/README.md`](src/pl8-interface/README.md) for the
request/response contract.

Runs on the arm64 `python3.14` runtime with the shared layer. The function
is tagged
`Type=PL8Interface`; invoke permission is granted against that tag outside
this repo.

## Deployment

### Prerequisites

Deployment expects a sibling checkout of this org's shared per-environment
config repo (referred to below as `tfconfig`), which provides, for each
environment:

- `<environment>.tfbackend` — OpenTofu S3 backend settings (bucket, region,
  locking)
- `<environment>.tfvars` — shared variables passed to every project in this
  account (`aws_region`, `environment`)

This repo's own `infra/tfvars/<environment>.tfvars` supplies values specific
to `pl8-services` only (table capacity, queue settings, etc).

### Plan and apply

Build the shared layer first; `infra/lambda.tf` zips `src/build/layer` at
plan time. Requires `uv`.

```bash
src/build-layer.sh
cd infra
tofu init -backend-config <path-to-tfconfig>/<environment>.tfbackend
tofu plan \
  -var-file tfvars/<environment>.tfvars \
  -var-file <path-to-tfconfig>/<environment>.tfvars \
  -out plan.tfplan
tofu apply plan.tfplan
```

Currently deployed manually, after authenticating to the target AWS
account.
