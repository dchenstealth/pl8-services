import json

import boto3
import pytest
from aws_lambda_powertools import Logger
from moto import mock_aws
from pl8_base.manager import BasePL8

from pl8_event_handler.manager import EventManager

TABLE_NAME = "test-pl8-table"
REGION = "us-east-1"


@pytest.fixture
def aws_environment(monkeypatch):
    """Fake credentials so a misconfigured test cannot reach real AWS."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


@pytest.fixture
def mocked_aws(aws_environment):
    with mock_aws():
        yield


@pytest.fixture
def table_name():
    return TABLE_NAME


@pytest.fixture
def dynamodb_client(mocked_aws, table_name):
    client = boto3.client("dynamodb", region_name=REGION)
    client.create_table(
        TableName=table_name,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[{
            "IndexName": "GSI1",
            "KeySchema": [
                {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        }],
    )
    return client


@pytest.fixture
def logger():
    return Logger(service="pl8-event-handler-test", level="DEBUG")


@pytest.fixture
def mgr(dynamodb_client, table_name, logger):
    return BasePL8(dynamodb_client=dynamodb_client, table_name=table_name,
                   logger=logger)


@pytest.fixture
def event_manager(mgr, logger):
    return EventManager(mgr, logger)


def sqs_record(detail, message_id="msg-1"):
    """An SQS record carrying an EventBridge envelope, as the rule delivers it."""
    envelope = {"version": "0", "id": "eb-id", "detail-type": detail.get("type"),
                "source": "pl8", "account": "123456789012",
                "time": "2026-09-22T00:00:00Z", "region": REGION,
                "resources": [], "detail": detail}
    return {"messageId": message_id, "receiptHandle": "rh",
            "body": json.dumps(envelope), "attributes": {},
            "messageAttributes": {}, "eventSource": "aws:sqs"}
