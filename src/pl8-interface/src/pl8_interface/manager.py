from importlib.resources import files

import fastjsonschema
import msgspec
import yaml
from pl8_base.errors import DDBError

DEFAULT_OPERATIONS = files(__package__) / "operations.yaml"

ENVELOPE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["operation"],
    "properties": {
        "operation": {"type": "string"},
        "params": {"type": "object", "default": {}},
    },
}


def error(error_type, message):
    return {"ok": False, "error": {"type": error_type, "message": message}}


class InterfaceManager:
    """Validates invoke events and dispatches them onto a BasePL8."""

    def __init__(self, pl8, logger, operations=DEFAULT_OPERATIONS):
        self._pl8 = pl8
        self._logger = logger
        self._validate_envelope = fastjsonschema.compile(ENVELOPE_SCHEMA)
        self._validators = {}

        for entry in yaml.safe_load(operations.read_text()):
            method = entry["method"]
            # Only allow-listed public methods are reachable; handle_* belong
            # to pl8-event-handler.
            if method.startswith(("_", "handle_")) or not callable(getattr(pl8, method, None)):
                raise ValueError(f"Operation {method!r} is not an invokable BasePL8 method")
            self._validators[method] = fastjsonschema.compile(entry["schema"])

    @property
    def operations(self):
        return frozenset(self._validators)

    def handle_event(self, event):
        try:
            event = self._validate_envelope(event, name_prefix="event")
        except fastjsonschema.JsonSchemaValueException as exc:
            return error("InvalidRequest", exc.message)

        operation = event["operation"]
        validate_params = self._validators.get(operation)
        if validate_params is None:
            return error("UnknownOperation", f"Unknown operation: {operation}")

        try:
            params = validate_params(event["params"], name_prefix="params")
        except fastjsonschema.JsonSchemaValueException as exc:
            return error("InvalidParams", exc.message)

        try:
            result = getattr(self._pl8, operation)(**params)
        except DDBError as exc:
            self._logger.info("Operation failed", operation=operation,
                              error_type=type(exc).__name__)
            return error(type(exc).__name__, str(exc))

        # Paginated BasePL8 queries return (items, cursor).
        if isinstance(result, tuple):
            items, cursor = result
            result = {"items": items, "cursor": cursor}

        return {"ok": True, "data": msgspec.to_builtins(result)}
