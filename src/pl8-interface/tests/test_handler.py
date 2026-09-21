import importlib
from types import SimpleNamespace

import pytest

CONTEXT = SimpleNamespace(
    function_name="pl8-interface",
    memory_limit_in_mb=256,
    invoked_function_arn="arn:aws:lambda:us-east-1:123456789012:function:pl8-interface",
    aws_request_id="request-id",
)


@pytest.fixture
def handler(monkeypatch, dynamodb_client, table_name):
    monkeypatch.setenv("PL8_TABLE_NAME", table_name)
    import pl8_interface.handler
    return importlib.reload(pl8_interface.handler)


def test_lambda_handler_dispatches(handler):
    response = handler.lambda_handler({"operation": "get_spaces"}, CONTEXT)
    assert response == {"ok": True, "data": {"items": [], "cursor": None}}


def test_unexpected_error_propagates(handler, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(handler.manager._pl8, "get_spaces", boom)

    with pytest.raises(RuntimeError, match="boom"):
        handler.lambda_handler({"operation": "get_spaces"}, CONTEXT)
