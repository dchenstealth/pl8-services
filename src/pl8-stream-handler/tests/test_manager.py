import json

from botocore.exceptions import ClientError
from conftest import FakeEventsClient, issue_image, record

from pl8_stream_handler.manager import StreamManager

BUS = "test-pl8-events"
SOURCE = "pl8"


def manager(events_client, logger):
    return StreamManager(events_client=events_client, event_bus_name=BUS,
                         source=SOURCE, logger=logger)


def ready():
    return record("INSERT", new=issue_image("TODO"))


def deleted():
    return record("REMOVE", old=issue_image("TODO"))


def test_sends_one_entry_per_event_in_order(logger):
    client = FakeEventsClient()
    records = [ready(), record("INSERT", new=issue_image("DONE")), deleted()]

    response = manager(client, logger).handle_event({"Records": records})

    assert response == {"batchItemFailures": []}
    assert [e["DetailType"] for e in client.entries] == ["IssueReady", "IssueDeleted"]
    entry = client.entries[0]
    assert entry["Source"] == SOURCE
    assert entry["EventBusName"] == BUS
    detail = json.loads(entry["Detail"])
    assert detail["type"] == "IssueReady"
    assert detail["issue_id"] == "abc123"


def test_empty_batch(logger):
    assert manager(FakeEventsClient(), logger).handle_event({"Records": []}) == {
        "batchItemFailures": []}


def test_failed_entry_stops_batch_at_that_record(logger):
    client = FakeEventsClient(fail_on=1)
    records = [ready(), deleted(), ready()]

    response = manager(client, logger).handle_event({"Records": records})

    assert response == {"batchItemFailures": [
        {"itemIdentifier": records[1]["dynamodb"]["SequenceNumber"]}]}
    # The third record was never attempted.
    assert len(client.entries) == 2


def test_client_error_stops_batch_at_that_record(logger):
    exc = ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
                      "PutEvents")
    client = FakeEventsClient(fail_on=0, raise_exc=exc)
    records = [ready(), deleted()]

    response = manager(client, logger).handle_event({"Records": records})

    assert response == {"batchItemFailures": [
        {"itemIdentifier": records[0]["dynamodb"]["SequenceNumber"]}]}
    assert len(client.entries) == 1


def test_records_without_events_are_skipped(logger):
    client = FakeEventsClient()
    records = [record("MODIFY", old=issue_image("TODO"), new=issue_image("TODO", title="x"))]

    assert manager(client, logger).handle_event({"Records": records}) == {
        "batchItemFailures": []}
    assert client.entries == []
