import importlib
from types import SimpleNamespace

CONTEXT = SimpleNamespace(
    function_name="pl8-stream-handler",
    memory_limit_in_mb=256,
    invoked_function_arn="arn:aws:lambda:us-east-1:123456789012:function:pl8-stream-handler",
    aws_request_id="request-id",
)


def test_lambda_handler_wires_manager_from_env(monkeypatch, aws_environment):
    monkeypatch.setenv("PL8_EVENT_BUS_NAME", "test-pl8-events")
    monkeypatch.setenv("PL8_EVENT_SOURCE", "pl8")
    import pl8_stream_handler.handler
    handler = importlib.reload(pl8_stream_handler.handler)

    assert handler.manager._event_bus_name == "test-pl8-events"
    assert handler.manager._source == "pl8"
    assert handler.lambda_handler({"Records": []}, CONTEXT) == {"batchItemFailures": []}
