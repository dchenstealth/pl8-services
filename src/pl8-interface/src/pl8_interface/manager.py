from importlib.resources import files

import fastjsonschema
import yaml
from pl8_base.errors import (
    DDBError,
    DDBInternalError,
    StorageError,
    StorageInternalError,
)

DEFAULT_OPERATIONS = files(__package__) / "operations.yaml"

INTERNAL_ERROR_MESSAGE = "Internal error"

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


def public_result(value):
    """Shape one result value for the response body.

    An entity becomes its public_dict(); dicts and lists are walked so a part
    holding entities is shaped whatever its nesting. Anything else -- a URL, a
    dict of presigned form fields, None -- passes through.

    Args:
        value: an entity, or any JSON-encodable value, or a container of them

    Returns:
        The value with every entity in it replaced by its public dict
    """
    if isinstance(value, dict):
        return {key: public_result(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [public_result(item) for item in value]

    public_dict = getattr(value, "public_dict", None)
    return public_dict() if callable(public_dict) else value


def result_names(entry):
    """Validate and return one entry's `returns` marker.

    Args:
        entry (dict): an operations.yaml entry

    Returns:
        tuple[str] or None: the names the result tuple unpacks into, or None
            for an operation returning a single entity

    Raises:
        ValueError: if the marker is malformed, or is combined with paginated
    """
    method = entry["method"]
    names = entry.get("returns")

    if names is None:
        return None

    if (not isinstance(names, list) or not names
            or not all(isinstance(name, str) and name for name in names)):
        raise ValueError(f"Operation {method!r} has a malformed returns: "
                         f"{names!r}; expected a list of names")

    if len(set(names)) != len(names):
        raise ValueError(f"Operation {method!r} repeats a returns name: "
                         f"{names!r}")

    if entry.get("paginated", False):
        raise ValueError(f"Operation {method!r} cannot be both paginated and "
                         f"name its returns")

    return tuple(names)


class InterfaceManager:
    """Validates invoke events and dispatches them onto a BasePL8."""

    def __init__(self, pl8, logger, operations=DEFAULT_OPERATIONS):
        self._pl8 = pl8
        self._logger = logger
        self._validate_envelope = fastjsonschema.compile(ENVELOPE_SCHEMA)
        self._validators = {}
        self._paginated = set()
        self._result_names = {}

        for entry in yaml.safe_load(operations.read_text())["operations"]:
            method = entry["method"]
            # Only allow-listed public methods are reachable; handle_* belong
            # to pl8-event-handler.
            if method.startswith(("_", "handle_")) or not callable(getattr(pl8, method, None)):
                raise ValueError(f"Operation {method!r} is not an invokable BasePL8 method")
            self._validators[method] = fastjsonschema.compile(entry["schema"])
            names = result_names(entry)

            if entry.get("paginated", False):
                self._paginated.add(method)

            if names is not None:
                self._result_names[method] = names

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
        # Storage failures are handled alongside the database ones, and split
        # the same way. A StorageError is caller-fixable -- the object is not
        # there at confirm, because the upload never happened -- so it belongs
        # in an error response like any other; letting it escape would make
        # Lambda report a FunctionError and the CLI a fault.
        except (DDBInternalError, StorageInternalError) as exc:
            # Server-side fault: log the detail, but don't hand raw AWS error
            # text (account, role, table and bucket ARNs) back to the caller.
            self._logger.exception("Operation failed with internal error",
                                   operation=operation,
                                   error_type=type(exc).__name__)
            return error(type(exc).__name__, INTERNAL_ERROR_MESSAGE)
        except (DDBError, StorageError) as exc:
            self._logger.info("Operation failed", operation=operation,
                              error_type=type(exc).__name__)
            return error(type(exc).__name__, str(exc))

        if operation in self._paginated:
            items, cursor = result
            data = {"items": [item.public_dict() for item in items],
                    "cursor": cursor}
        elif operation in self._result_names:
            # The same transformation as (items, cursor) above, with the keys
            # named by operations.yaml instead of hardcoded: an operation
            # returning an entity plus something that is not one of its
            # attributes (a presigned target, a download URL) hands back a
            # tuple, and the marker says what each part is called on the wire.
            names = self._result_names[operation]

            # A length mismatch means the marker and the method disagree, which
            # would otherwise silently drop a part of the result. That is a bug
            # in the pairing, not a caller error, so let it fault.
            if len(names) != len(result):
                raise ValueError(
                    f"Operation {operation!r} returned {len(result)} values "
                    f"for names {names}")

            data = {name: public_result(part)
                    for name, part in zip(names, result)}
        else:
            data = None if result is None else result.public_dict()

        return {"ok": True, "data": data}
