# pl8-services

Infrastructure (and, eventually, Lambda code) for running
[PL8](https://github.com/dchenstealth/pl8-base) in AWS.

## Status

This repo covers PL8's stateful and eventing backbone and all three of its
Lambdas: `pl8-interface`, `pl8-stream-handler` and `pl8-event-handler`.

## Resources

Managed with [OpenTofu](https://opentofu.org/):

- A DynamoDB table (`PK`/`SK` + `GSI1`) matching the schema
  [`pl8-base`](https://github.com/dchenstealth/pl8-base) expects, with
  DynamoDB Streams enabled
- A custom EventBridge event bus
- An EventBridge rule routing PL8's internal lifecycle events to an SQS
  queue
- An SQS queue (with a dead-letter queue) that `pl8-event-handler`
  consumes from
- The `pl8-interface`, `pl8-stream-handler` and `pl8-event-handler`
  Lambdas (see below), plus their event source mappings
- A dead-letter queue for records `pl8-stream-handler` fails to publish
- CloudWatch alarms on both dead-letter queues (notify via
  `alarm_actions`)
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

### Event flow

```
DynamoDB stream ─▶ pl8-stream-handler ─▶ EventBridge bus ─┬─▶ core lifecycle rule ─▶ SQS ─▶ pl8-event-handler
                                                          └─▶ IssueReady, for external consumers' own rules
```

Each hop delivers at-least-once, so every event can arrive more than once.
pl8-base's `handle_*` methods are idempotent for this reason, and
`IssueReady` consumers must tolerate duplicates too. The event handler's
writes land back on the stream, so one change can cascade: an Issue
reaching DONE satisfies its IssueBlockers, which zeroes a blocked Issue's
counter, which moves that Issue to TODO and emits `IssueReady`.

Only the Issue's own `100#INFO` row produces events, so the stream's event
source mapping filters everything else out, comments included; `IssueDeleted`
is what carries a deleted Issue's comments and blockers away with it.

Each function's zip, role, log group and function come from
`infra/modules/lambda_function`.

### pl8-stream-handler

Reads the table's stream and publishes the events in
[pl8-docs `events.md`](https://github.com/dchenstealth/pl8-docs/blob/main/architecture/backend/events.md)
onto the bus. See
[`src/pl8-stream-handler/README.md`](src/pl8-stream-handler/README.md).

### pl8-event-handler

Consumes the core lifecycle events from SQS and applies them with pl8-base's
`handle_*` methods. See
[`src/pl8-event-handler/README.md`](src/pl8-event-handler/README.md).

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

### Smoke test

After an apply, check the whole async loop end to end (requires `aws`,
`jq`, and invoke permission on the interface):

```bash
scripts/smoke-test.sh <environment>
```

It creates a throwaway Space, checks that finishing or deleting a blocking
Issue moves the blocked Issue back to TODO and that deleting a commented
Issue sweeps its comments, checks both DLQs are empty, and deletes what it
created on exit, pass or fail.
