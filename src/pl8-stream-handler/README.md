# pl8-stream-handler

Consumes the PL8 table's DynamoDB stream and publishes PL8's lifecycle events
(see [pl8-docs `events.md`](https://github.com/dchenstealth/pl8-docs/blob/main/architecture/backend/events.md))
onto the PL8 EventBridge bus.

## Events

Only `IssueInfo` rows produce events. The event source mapping filters on
`SK = 100#INFO`, so blocker and space writes never invoke the function, and
[`mapping.py`](src/pl8_stream_handler/mapping.py) also checks each image's
`type`, so nothing else at that key is misread as an Issue.

| Record | Condition | Event |
| --- | --- | --- |
| INSERT | status is TODO | `IssueReady` |
| MODIFY | status changes to TODO | `IssueReady` |
| MODIFY | status changes to DONE | `IssueDone` |
| MODIFY | `num_active_blockers` goes from > 0 to 0 | `IssueNumActiveBlockersZeroed` |
| REMOVE | — | `IssueDeleted` |

An Issue created as DONE does not emit `IssueDone`: it cannot be blocking
anything yet.

## Delivery

Each event is sent on its own with `pl8_base.util.send_event`, with Source
`pl8` (`PL8_EVENT_SOURCE`). Records are processed in shard order. At the
first record that fails to send, the handler stops and reports that record
in `batchItemFailures`, so Lambda retries the shard from there and events
stay in order. Events already sent for that record are sent again.

After `pl8_stream_handler_maximum_retry_attempts` retries (the mapping also
bisects the batch when the whole invocation fails), the failed batch's
metadata goes to the `<environment>-pl8-stream-handler-dlq` queue. It
holds shard and sequence numbers, not the records themselves, and the
stream keeps records for only 24 hours.

## Development

```bash
uv sync
uv run ruff check .
uv run pytest
```
