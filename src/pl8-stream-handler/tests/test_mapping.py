import pytest
from conftest import (
    ISSUE_ID,
    SPACE_ID,
    blocker_image,
    comment_image,
    issue_image,
    record,
    space_image,
)

from pl8_stream_handler.mapping import events_for_record


def names(events):
    return [type(e).__name__ for e in events]


@pytest.mark.parametrize(("rec", "expected"), [
    # INSERT
    (record("INSERT", new=issue_image("TODO")), ["IssueReady"]),
    (record("INSERT", new=issue_image("IN_PROGRESS")), []),
    (record("INSERT", new=issue_image("BLOCKED")), []),
    (record("INSERT", new=issue_image("DONE")), []),
    # MODIFY: status transitions
    (record("MODIFY", old=issue_image("IN_PROGRESS"), new=issue_image("TODO")), ["IssueReady"]),
    (record("MODIFY", old=issue_image("TODO"), new=issue_image("IN_PROGRESS")), []),
    (record("MODIFY", old=issue_image("IN_PROGRESS"), new=issue_image("DONE")), ["IssueDone"]),
    (record("MODIFY", old=issue_image("TODO"), new=issue_image("DONE")), ["IssueDone"]),
    (record("MODIFY", old=issue_image("TODO"), new=issue_image("BLOCKED", 1)), []),
    # MODIFY: no transition
    (record("MODIFY", old=issue_image("TODO"), new=issue_image("TODO", title="x")), []),
    (record("MODIFY", old=issue_image("DONE"), new=issue_image("DONE")), []),
    # MODIFY: blocker counter
    (record("MODIFY", old=issue_image("BLOCKED", 1), new=issue_image("BLOCKED", 0)),
     ["IssueNumActiveBlockersZeroed"]),
    (record("MODIFY", old=issue_image("BLOCKED", 2), new=issue_image("BLOCKED", 1)), []),
    (record("MODIFY", old=issue_image("BLOCKED", 1), new=issue_image("BLOCKED", 2)), []),
    # MODIFY: comment counter. Every comment add and delete moves it on the
    # IssueInfo row, which passes the event source mapping's filter.
    (record("MODIFY", old=issue_image("TODO"), new=issue_image("TODO", num_comments=1)), []),
    (record("MODIFY", old=issue_image("DONE", num_comments=1),
            new=issue_image("DONE", num_comments=0)), []),
    # Unblocked by the event handler: counter already 0, status BLOCKED -> TODO
    (record("MODIFY", old=issue_image("BLOCKED", 0), new=issue_image("TODO", 0)), ["IssueReady"]),
    # REMOVE
    (record("REMOVE", old=issue_image("TODO")), ["IssueDeleted"]),
    (record("REMOVE", old=issue_image("DONE")), ["IssueDeleted"]),
    # Other row types. The event source mapping filters these out, so they
    # should never arrive; mapping nothing is what keeps that filter from
    # being the only thing standing between them and being read as Issues.
    (record("INSERT", new=blocker_image()), []),
    (record("REMOVE", old=blocker_image()), []),
    (record("INSERT", new=space_image()), []),
    (record("REMOVE", old=space_image()), []),
    (record("INSERT", new=comment_image()), []),
    (record("MODIFY", old=comment_image(), new=comment_image()), []),
    (record("REMOVE", old=comment_image()), []),
])
def test_events_for_record(rec, expected):
    assert names(events_for_record(rec)) == expected


def test_event_ids_come_from_the_image():
    [event] = events_for_record(record("REMOVE", old=issue_image("TODO")))
    assert (event.space_id, event.issue_id) == (SPACE_ID, ISSUE_ID)


def test_non_issue_info_row_at_issue_info_key_is_ignored():
    image = issue_image()
    partial = {"PK": image["PK"], "SK": image["SK"],
               "num_active_blockers": {"N": "-1"}}
    assert events_for_record(record("INSERT", new=partial)) == []
    assert events_for_record(record("REMOVE", old=partial)) == []


def test_comment_rows_share_the_issue_partition():
    """A comment's PK is its Issue's, so only the SK keeps it out of the
    event source mapping's filter; see infra/lambda.tf."""
    assert comment_image()["PK"] == issue_image()["PK"]
    assert comment_image()["SK"] != issue_image()["SK"]
