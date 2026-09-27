import json

import pytest
from botocore.exceptions import ClientError
from conftest import (
    ISSUE_ID,
    SPACE_ID,
    TTL_USER_IDENTITY,
    FakeEventsClient,
    attachment_image,
    comment_image,
    issue_image,
    record,
)
from pl8_base.types import IssueCommentDeleted

from pl8_stream_handler.manager import StreamManager, event_fields

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
    """send_event wraps a failed call in EventSendError, so this is the same
    path as a failed entry."""
    exc = ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
                      "PutEvents")
    client = FakeEventsClient(fail_on=0, raise_exc=exc)
    records = [ready(), deleted()]

    response = manager(client, logger).handle_event({"Records": records})

    assert response == {"batchItemFailures": [
        {"itemIdentifier": records[0]["dynamodb"]["SequenceNumber"]}]}
    assert len(client.entries) == 1


@pytest.mark.parametrize(("image_fn", "detail_type", "id_attr"), [
    (comment_image, "IssueCommentDeleted", "comment_id"),
    (attachment_image, "IssueAttachmentDeleted", "attachment_id"),
])
def test_deleted_child_row_sends_its_own_id(logger, image_fn, detail_type, id_attr):
    client = FakeEventsClient()
    image = image_fn()

    response = manager(client, logger).handle_event(
        {"Records": [record("REMOVE", old=image)]})

    assert response == {"batchItemFailures": []}
    [entry] = client.entries
    assert entry["DetailType"] == detail_type
    assert json.loads(entry["Detail"])[id_attr] == image[id_attr]["S"]


def sent_event_logs(caplog):
    return [r for r in caplog.records if r.getMessage() == "Sent event"]


def test_ttl_expiry_is_marked_on_the_sent_event_log(logger, caplog):
    image = attachment_image()

    manager(FakeEventsClient(), logger).handle_event({"Records": [
        record("REMOVE", old=image, user_identity=TTL_USER_IDENTITY)]})

    [log] = sent_event_logs(caplog)
    assert log.removed_by == "ttl"
    assert log.space_id == SPACE_ID
    assert log.issue_id == ISSUE_ID
    assert log.attachment_id == image["attachment_id"]["S"]


def test_a_callers_delete_is_not_marked(logger, caplog):
    manager(FakeEventsClient(), logger).handle_event({"Records": [
        record("REMOVE", old=attachment_image())]})

    [log] = sent_event_logs(caplog)
    assert not hasattr(log, "removed_by")


def test_event_fields_are_the_events_own_ids():
    """What the manager logs per event. Envelope fields are excluded, so a
    log key can never be a type_version or a timestamp."""
    event = IssueCommentDeleted(space_id=SPACE_ID, issue_id=ISSUE_ID,
                                comment_id="c001")

    assert event_fields(event) == {"space_id": SPACE_ID, "issue_id": ISSUE_ID,
                                  "comment_id": "c001"}


def test_records_without_events_are_skipped(logger):
    client = FakeEventsClient()
    records = [record("MODIFY", old=issue_image("TODO"), new=issue_image("TODO", title="x"))]

    assert manager(client, logger).handle_event({"Records": records}) == {
        "batchItemFailures": []}
    assert client.entries == []
