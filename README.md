# pl8-services

Infrastructure (and, eventually, Lambda code) for running
[PL8](https://github.com/dchenstealth/pl8-base) in AWS.

## Status

This repo currently covers PL8's **infrastructure slice** only: the
stateful and eventing backbone that PL8's Lambdas will attach to. The
Lambda functions themselves (`pl8-interface`, `pl8-stream-handler`,
`pl8-event-handler`) are a follow-up slice, not yet implemented here.

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

```bash
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
