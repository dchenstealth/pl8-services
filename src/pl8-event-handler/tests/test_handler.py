import importlib
from types import SimpleNamespace

import pytest
from conftest import sqs_record
from pl8_base.types import IssueDone

CONTEXT = SimpleNamespace(
    function_name="pl8-event-handler",
    memory_limit_in_mb=256,
    invoked_function_arn="arn:aws:lambda:us-east-1:123456789012:function:pl8-event-handler",
    aws_request_id="request-id",
)


@pytest.fixture
def handler(monkeypatch, dynamodb_client, table_name):
    monkeypatch.setenv("PL8_TABLE_NAME", table_name)
    import pl8_event_handler.handler
    return importlib.reload(pl8_event_handler.handler)


def test_lambda_handler_dispatches(handler):
    # An Issue with nothing blocking on it: handled as a no-op.
    record = sqs_record(IssueDone(space_id="ENG", issue_id="abc123").dict())
    assert handler.lambda_handler({"Records": [record]}, CONTEXT) == {
        "batchItemFailures": []}
