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

`data` is the method's result as plain JSON. Paginated operations
(`get_spaces`, `get_issues_by_status`, `get_issue_blockers`,
`get_issue_blocking`) return `{"items": [...], "cursor": "..." | null}`; pass
`cursor` back as a param for the next page.

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

Any other exception is not caught, so the invocation itself fails
(`FunctionError`) — treat that as a server-side bug.

## Operations

[`src/pl8_interface/operations.yaml`](src/pl8_interface/operations.yaml) is
the allow-list: each entry names a `BasePL8` method and the JSON Schema for its
params. Params map 1:1 onto the method's keyword arguments.

To add an operation, add an entry there. `tests/test_operations_yaml.py`
fails unless the schema's properties and `required` list match the method's
signature, and its expected-operations set must be updated too.
`handle_*` methods are reserved for pl8-event-handler and are rejected.

## Development

```bash
uv sync
uv run ruff check .
uv run pytest
./build.sh    # -> dist/pl8-interface.zip (arm64, python3.14)
```
