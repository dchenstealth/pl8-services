import json

import pytest
from conftest import sqs_record
from pl8_base.errors import DDBInternalError
from pl8_base.types import (
    IssueDeleted,
    IssueDone,
    IssueNumActiveBlockersZeroed,
    IssueReady,
)

from pl8_event_handler.manager import RECORD_LOG_KEYS

SPACE = "ENG"
CREATOR = "alice"


@pytest.fixture
def blocked_pair(mgr):
    """A blocks B, so B is BLOCKED with one active blocker."""
    mgr.create_space(space_id=SPACE, name=SPACE, description="d", creator=CREATOR)
    a = mgr.create_issue(space_id=SPACE, title="A", description="d", status="TODO",
                         creator=CREATOR)
    b = mgr.create_issue(space_id=SPACE, title="B", description="d", status="TODO",
                         creator=CREATOR)
    mgr.add_issue_blocker(blocking_issue_space_id=SPACE, blocking_issue_id=a.issue_id,
                          blocked_issue_space_id=SPACE, blocked_issue_id=b.issue_id)
    return a, b


def detail(event_cls, issue):
    return event_cls(space_id=issue.space_id, issue_id=issue.issue_id).dict()


def handle(event_manager, *details):
    records = [sqs_record(d, message_id=f"msg-{i}") for i, d in enumerate(details)]
    return event_manager.handle_event({"Records": records})


def test_issue_done_satisfies_blockers(mgr, event_manager, blocked_pair):
    a, b = blocked_pair
    mgr.transition_issue(space_id=SPACE, issue_id=a.issue_id, status="DONE")

    assert handle(event_manager, detail(IssueDone, a)) == {"batchItemFailures": []}

    [blocker], _ = mgr.get_issue_blocking(space_id=SPACE, blocking_issue_id=a.issue_id)
    assert blocker.is_blocking_issue_done
    b_after = mgr.get_issue(space_id=SPACE, issue_id=b.issue_id)
    assert b_after.num_active_blockers == 0
    # Unblocking is the next event's job.
    assert b_after.status == "BLOCKED"


def test_num_active_blockers_zeroed_unblocks(mgr, event_manager, blocked_pair):
    a, b = blocked_pair
    mgr.transition_issue(space_id=SPACE, issue_id=a.issue_id, status="DONE")
    handle(event_manager, detail(IssueDone, a))

    assert handle(event_manager, detail(IssueNumActiveBlockersZeroed, b)) == {
        "batchItemFailures": []}

    assert mgr.get_issue(space_id=SPACE, issue_id=b.issue_id).status == "TODO"


def test_issue_deleted_sweeps_blockers(mgr, event_manager, blocked_pair):
    a, b = blocked_pair
    mgr.delete_issue(space_id=SPACE, issue_id=a.issue_id)

    assert handle(event_manager, detail(IssueDeleted, a)) == {"batchItemFailures": []}

    assert mgr.get_issue_blockers(space_id=SPACE, blocked_issue_id=b.issue_id) == ([], None)
    assert mgr.get_issue(space_id=SPACE, issue_id=b.issue_id).num_active_blockers == 0


def test_issue_deleted_sweeps_comments(mgr, event_manager, blocked_pair):
    """Comments never gate deleting an Issue, so the sweep is what removes
    them; see pl8-base's handle_issue_deleted."""
    a, _ = blocked_pair
    mgr.create_issue_comment(space_id=SPACE, issue_id=a.issue_id, body="b",
                             creator=CREATOR)
    mgr.delete_issue(space_id=SPACE, issue_id=a.issue_id)

    assert handle(event_manager, detail(IssueDeleted, a)) == {"batchItemFailures": []}

    assert mgr.get_issue_comments(space_id=SPACE, issue_id=a.issue_id) == ([], None)


def test_replayed_events_are_no_ops(mgr, event_manager, blocked_pair):
    a, b = blocked_pair
    mgr.transition_issue(space_id=SPACE, issue_id=a.issue_id, status="DONE")

    response = handle(event_manager, detail(IssueDone, a), detail(IssueDone, a),
                      detail(IssueNumActiveBlockersZeroed, b),
                      detail(IssueNumActiveBlockersZeroed, b))

    assert response == {"batchItemFailures": []}
    b_after = mgr.get_issue(space_id=SPACE, issue_id=b.issue_id)
    assert (b_after.status, b_after.num_active_blockers) == ("TODO", 0)


@pytest.mark.parametrize("body", [
    "not json",
    json.dumps({"no": "detail"}),
    json.dumps({"detail": {"space_id": SPACE, "issue_id": "x"}}),
    json.dumps({"detail": {"type": "Bogus", "space_id": SPACE, "issue_id": "x"}}),
    json.dumps({"detail": {"type": "IssueDone", "space_id": SPACE}}),
])
def test_malformed_record_fails_only_itself(mgr, event_manager, blocked_pair, body):
    a, _ = blocked_pair
    mgr.transition_issue(space_id=SPACE, issue_id=a.issue_id, status="DONE")
    bad = sqs_record({}, message_id="bad") | {"body": body}
    good = sqs_record(detail(IssueDone, a), message_id="good")

    response = event_manager.handle_event({"Records": [bad, good]})

    assert response == {"batchItemFailures": [{"itemIdentifier": "bad"}]}
    [blocker], _ = mgr.get_issue_blocking(space_id=SPACE, blocking_issue_id=a.issue_id)
    assert blocker.is_blocking_issue_done


def noop():
    """An event that succeeds as a no-op: nothing is blocked on the Issue."""
    return IssueDone(space_id=SPACE, issue_id="noop01").dict()


def test_consumer_facing_event_is_rejected(event_manager):
    ready = IssueReady(space_id=SPACE, issue_id="abc123").dict()
    assert handle(event_manager, ready, noop()) == {
        "batchItemFailures": [{"itemIdentifier": "msg-0"}]}


def test_invalid_space_id_fails_record(event_manager):
    bad = IssueDone(space_id="bad#space", issue_id="abc123").dict()
    assert handle(event_manager, bad, noop()) == {
        "batchItemFailures": [{"itemIdentifier": "msg-0"}]}


def test_ddb_error_fails_only_its_record(mgr, event_manager, blocked_pair, monkeypatch):
    a, b = blocked_pair

    def boom(**kwargs):
        raise DDBInternalError("boom")

    monkeypatch.setattr(mgr, "handle_issue_deleted", boom)
    mgr.transition_issue(space_id=SPACE, issue_id=a.issue_id, status="DONE")

    response = handle(event_manager, detail(IssueDeleted, b), detail(IssueDone, a))

    assert response == {"batchItemFailures": [{"itemIdentifier": "msg-0"}]}
    assert mgr.get_issue(space_id=SPACE, issue_id=b.issue_id).num_active_blockers == 0


def test_unexpected_error_fails_only_its_record(mgr, event_manager, blocked_pair,
                                                monkeypatch):
    a, b = blocked_pair

    def boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(mgr, "handle_issue_deleted", boom)
    mgr.transition_issue(space_id=SPACE, issue_id=a.issue_id, status="DONE")

    response = handle(event_manager, detail(IssueDeleted, b), detail(IssueDone, a))

    assert response == {"batchItemFailures": [{"itemIdentifier": "msg-0"}]}
    assert mgr.get_issue(space_id=SPACE, issue_id=b.issue_id).num_active_blockers == 0


def test_entire_batch_failing_reports_every_record(mgr, event_manager, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(mgr, "handle_issue_done", boom)
    done = IssueDone(space_id=SPACE, issue_id="abc123").dict()

    assert handle(event_manager, done, done) == {"batchItemFailures": [
        {"itemIdentifier": "msg-0"}, {"itemIdentifier": "msg-1"}]}


def test_record_log_keys_do_not_outlive_the_batch(event_manager, logger):
    handle(event_manager, noop())
    assert not set(RECORD_LOG_KEYS) & set(logger.get_current_keys())
