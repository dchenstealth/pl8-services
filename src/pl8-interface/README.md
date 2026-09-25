# pl8-interface

PL8's interface Lambda. Callers invoke it directly (Lambda `Invoke` API, IAM
auth). Each request is validated against a JSON Schema, then dispatched onto a
[`pl8-base`](https://github.com/dchenstealth/pl8-base) `BasePL8` method.

## Contract

Request:

```json
{"operation": "get_issue", "params": {"space_id": "ENG", "issue_id": "abc123"}}
```

`params` is optional and defaults to `{}`.

Success:

```json
{"ok": true, "data": { ... }}
```

`data` is the method's result as plain JSON, without DynamoDB key attributes
(`PK`, `SK`, `GSI1PK`, ...), or `null` for operations that return nothing (the
`delete_*` operations). Paginated operations (`get_spaces`,
`get_issues_by_status`, `get_issue_comments`, `get_issue_blockers`,
`get_issue_blocking`) return `{"items": [...], "cursor": "..." | null}`; pass
`cursor` back as a param for the next page. `limit` is 1–100 (default 50).

Failure:

```json
{"ok": false, "error": {"type": "InvalidParams", "message": "params must contain ['space_id'] properties"}}
```

| `type` | Meaning |
| --- | --- |
| `InvalidRequest` | Event isn't `{"operation": str, "params": object}` |
| `UnknownOperation` | `operation` isn't listed in `operations.yaml` |
| `InvalidParams` | `params` fails that operation's schema |
| `DDB*` | A [`pl8_base.errors`](https://github.com/dchenstealth/pl8-base/blob/main/src/pl8_base/errors.py) error, e.g. `DDBMissingError`, `DDBVersionConflictError` |

`DDBInternalError` and its subclass `DDBCorruptedError` are server-side
faults. They do **not** fail the invocation: they come back as a normal
`ok: false` response with the generic message `"Internal error"`, and the
detail is logged at error level in the function's log group.

Any other exception is not caught, so the invocation itself fails
(`FunctionError`) — treat that as a server-side bug.

## Operations

[`src/pl8_interface/operations.yaml`](src/pl8_interface/operations.yaml) is
the allow-list: each entry names a `BasePL8` method and the JSON Schema for its
params. Params map 1:1 onto the method's keyword arguments. Entries whose
method returns `(items, cursor)` set `paginated: true`.

`create_space`, `create_issue` and `create_issue_comment` take a `creator`,
a label the caller supplies. It is not authenticated: pl8-base records it as
given and never compares it with the invoking IAM principal, so it says who
*claims* to have created an item.

To add an operation, add an entry there. `tests/test_operations_yaml.py`
fails unless the schema's properties and `required` list match the method's
signature (and `paginated` is set exactly when the method takes a `cursor`),
and its expected-operations set must be updated too.
`handle_*` methods are reserved for pl8-event-handler and are rejected.

## Development

```bash
uv sync
uv run ruff check .
uv run pytest
```

Dependencies are locked in the workspace's `../uv.lock`. Runtime dependencies
are deployed in the shared layer (`../build-layer.sh`), not in this
function's zip.
