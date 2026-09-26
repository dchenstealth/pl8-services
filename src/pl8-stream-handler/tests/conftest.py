import pytest
from aws_lambda_powertools import Logger
from pl8_base.types import (
    IssueAttachment,
    IssueBlocker,
    IssueComment,
    IssueInfo,
    SpaceInfo,
)

SPACE_ID = "ENG"
ISSUE_ID = "abc123"
CREATOR = "alice"

# What DynamoDB stamps on a REMOVE record it generated itself by expiring a
# row's TTL. A caller's DeleteItem carries no userIdentity at all.
TTL_USER_IDENTITY = {"type": "Service", "principalId": "dynamodb.amazonaws.com"}

_sequence = iter(range(1, 1_000_000))


def issue_image(status="TODO", num_active_blockers=0, **overrides):
    fields = {"space_id": SPACE_ID, "issue_id": ISSUE_ID, "title": "t",
              "description": "d", "status": status, "creator": CREATOR,
              "num_active_blockers": num_active_blockers} | overrides
    return IssueInfo(**fields).serialize()


def blocker_image():
    return IssueBlocker(blocking_issue_space_id=SPACE_ID,
                        blocking_issue_id="blk001",
                        blocked_issue_space_id=SPACE_ID,
                        blocked_issue_id=ISSUE_ID,
                        is_blocking_issue_done=False).serialize()


def space_image():
    return SpaceInfo(space_id=SPACE_ID, name="n", description="d",
                     creator=CREATOR).serialize()


def comment_image():
    return IssueComment(space_id=SPACE_ID, issue_id=ISSUE_ID, body="b",
                        creator=CREATOR).serialize()


def attachment_image(**overrides):
    """An IssueAttachment row image, as the stream delivers it.

    The defaults mirror what initiate_issue_attachment_upload is given; a
    freshly initiated attachment is PENDING and carries the expires_at the
    table's TTL reaps it by.
    """
    fields = {"space_id": SPACE_ID, "issue_id": ISSUE_ID, "name": "a.txt",
              "content_type": "text/plain", "size": 11,
              "creator": CREATOR} | overrides
    return IssueAttachment(**fields).serialize()


def record(event_name, *, old=None, new=None, user_identity=None):
    image = new or old
    ddb = {"Keys": {"PK": image["PK"], "SK": image["SK"]},
           "SequenceNumber": str(next(_sequence)),
           "StreamViewType": "NEW_AND_OLD_IMAGES"}
    if old is not None:
        ddb["OldImage"] = old
    if new is not None:
        ddb["NewImage"] = new
    rec = {"eventName": event_name, "eventSource": "aws:dynamodb",
           "dynamodb": ddb}
    if user_identity is not None:
        rec["userIdentity"] = user_identity
    return rec


class FakeEventsClient:
    """Records put_events calls; fail_on makes the Nth call (0-based) fail."""

    def __init__(self, fail_on=None, raise_exc=None):
        self.entries = []
        self._fail_on = fail_on
        self._raise_exc = raise_exc

    def put_events(self, Entries):
        call = len(self.entries)
        self.entries.extend(Entries)
        if call == self._fail_on:
            if self._raise_exc:
                raise self._raise_exc
            return {"FailedEntryCount": 1, "Entries": [
                {"ErrorCode": "InternalFailure", "ErrorMessage": "boom"}]}
        return {"FailedEntryCount": 0, "Entries": [{"EventId": str(call)}]}


@pytest.fixture
def aws_environment(monkeypatch):
    """Fake credentials so a misconfigured test cannot reach real AWS."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def logger():
    return Logger(service="pl8-stream-handler-test", level="DEBUG")
