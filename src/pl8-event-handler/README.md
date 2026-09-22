# pl8-event-handler

Consumes PL8's core lifecycle events from the `<environment>-pl8-event-handler`
SQS queue and applies them with [`pl8-base`](https://github.com/dchenstealth/pl8-base):

| Event | `BasePL8` method |
| --- | --- |
| `IssueDone` | `handle_issue_done` |
| `IssueDeleted` | `handle_issue_deleted` |
| `IssueNumActiveBlockersZeroed` | `handle_issue_num_active_blockers_zeroed` |

Each SQS message body is the full EventBridge envelope; the PL8 event is its
`detail`, parsed with `pl8_base.util.parse_event`.

## Failures

Records are processed with Powertools'
[`BatchProcessor`](https://docs.powertools.aws.dev/lambda/python/latest/utilities/batch/),
which reports failures per message (`batchItemFailures`). Any exception fails
only its own message and is logged at warning level with its traceback and
the message's `message_id` (plus `event_type`, `event_id`, `space_id` and
`issue_id` once parsed). Typical causes:

- its body isn't an EventBridge envelope with a valid PL8 event
- its event isn't one of the three above (e.g. `IssueReady`, which the rule
  doesn't route here), raising `UnhandledEventError`
- its `handle_*` call raises, e.g. a `pl8_base.errors.DDBError`

Failed messages are redelivered after the queue's visibility timeout, and
after `event_queue_max_receive_count` receives they move to the DLQ. The
`handle_*` methods are idempotent, so redelivery and duplicates are safe.

If every message in a batch fails, the invocation fails with
`BatchProcessingError` and the whole batch is redelivered.

Keep the queue's visibility timeout at six or more times this function's
timeout.

## Development

```bash
uv sync
uv run ruff check .
uv run pytest
```
