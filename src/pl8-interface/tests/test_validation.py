import pytest


@pytest.mark.parametrize("event", [
    {},
    [],
    {"operation": 1},
    {"operation": "get_space", "params": []},
    {"operation": "get_space", "params": {}, "extra": 1},
])
def test_invalid_envelope(interface, event):
    response = interface.handle_event(event)
    assert response["ok"] is False
    assert response["error"]["type"] == "InvalidRequest"


@pytest.mark.parametrize("operation", ["handle_issue_done", "parse_item", "nope"])
def test_unknown_operation(interface, operation):
    response = interface.handle_event({"operation": operation, "params": {}})
    assert response["error"]["type"] == "UnknownOperation"


@pytest.mark.parametrize("operation, params", [
    ("get_space", {}),
    ("get_space", {"space_id": "ENG", "extra": 1}),
    ("get_space", {"space_id": 5}),
    ("get_spaces", {"limit": 0}),
    ("create_issue", {"space_id": "ENG", "title": "t", "description": "d",
                      "status": "WONTFIX"}),
])
def test_invalid_params(invoke, operation, params):
    response = invoke(operation, **params)
    assert response["ok"] is False
    assert response["error"]["type"] == "InvalidParams"
    assert response["error"]["message"].startswith("params")


def test_params_default_to_empty(interface, mgr):
    response = interface.handle_event({"operation": "get_spaces"})
    assert response == {"ok": True, "data": {"items": [], "cursor": None}}
