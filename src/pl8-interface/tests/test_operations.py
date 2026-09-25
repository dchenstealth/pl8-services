import pytest
from pl8_base.errors import DDBInternalError


@pytest.fixture
def space(invoke):
    """The ENG Space, which create_issue requires to exist."""
    response = invoke("create_space", space_id="ENG", name="Eng", description="d",
                      creator="alice")
    assert response["ok"] is True
    return response["data"]


def create_issue(invoke, status="TODO", space_id="ENG"):
    response = invoke("create_issue", space_id=space_id, title="t",
                      description="d", status=status, creator="alice")
    assert response["ok"] is True
    return response["data"]


def create_comment(invoke, issue, body="b", creator="alice"):
    response = invoke("create_issue_comment", space_id="ENG",
                      issue_id=issue["issue_id"], body=body, creator=creator)
    assert response["ok"] is True
    return response["data"]


def test_space_round_trip(invoke):
    created = invoke("create_space", space_id="ENG", name="Eng", description="d",
                     creator="alice")
    assert created["ok"] is True

    fetched = invoke("get_space", space_id="ENG")
    assert fetched["ok"] is True
    assert fetched["data"]["space_id"] == "ENG"
    assert fetched["data"]["name"] == "Eng"
    assert fetched["data"]["description"] == "d"
    assert fetched["data"]["creator"] == "alice"


def test_results_omit_storage_keys(invoke, space):
    issue = create_issue(invoke)

    listed = invoke("get_spaces")["data"]["items"]
    for data in (issue, *listed):
        assert not {"PK", "SK", "GSI1PK", "GSI1SK"} & data.keys()


def test_delete_returns_null_data(invoke, space):
    issue = create_issue(invoke)

    response = invoke("delete_issue", space_id="ENG", issue_id=issue["issue_id"])
    assert response == {"ok": True, "data": None}


def test_internal_error_hides_detail(invoke, mgr, monkeypatch):
    def boom(**kwargs):
        raise DDBInternalError("arn:aws:iam::123456789012:role/secret")

    monkeypatch.setattr(mgr, "get_space", boom)

    response = invoke("get_space", space_id="ENG")
    assert response == {"ok": False, "error": {"type": "DDBInternalError",
                                               "message": "Internal error"}}


def test_missing_space_maps_ddb_error(invoke):
    response = invoke("get_space", space_id="ENG")
    assert response["ok"] is False
    assert response["error"]["type"] == "DDBMissingError"


def test_issue_in_missing_space_maps_ddb_error(invoke):
    response = invoke("create_issue", space_id="ENG", title="t",
                      description="d", status="TODO", creator="alice")
    assert response["ok"] is False
    assert response["error"]["type"] == "DDBMissingError"


def test_empty_creator_maps_ddb_error(invoke):
    response = invoke("create_space", space_id="ENG", name="Eng", description="d",
                      creator="")
    assert response["ok"] is False
    assert response["error"]["type"] == "DDBArgsError"


def test_delete_non_empty_space_maps_ddb_error(invoke, space):
    create_issue(invoke)

    response = invoke("delete_space", space_id="ENG")
    assert response["ok"] is False
    assert response["error"]["type"] == "DDBSpaceNotEmptyError"


def test_space_results_include_issue_count(invoke, space):
    assert space["issue_count"] == 0
    create_issue(invoke)

    assert invoke("get_space", space_id="ENG")["data"]["issue_count"] == 1


def test_transition_issue(invoke, space):
    issue = create_issue(invoke)

    response = invoke("transition_issue", space_id="ENG",
                      issue_id=issue["issue_id"], status="IN_PROGRESS")
    assert response["ok"] is True
    assert response["data"]["status"] == "IN_PROGRESS"


def test_transition_out_of_done_maps_ddb_error(invoke, space):
    issue = create_issue(invoke, status="DONE")

    response = invoke("transition_issue", space_id="ENG",
                      issue_id=issue["issue_id"], status="TODO")
    assert response["ok"] is False
    assert response["error"]["type"] == "DDBTerminalStatusError"


def test_get_issues_by_status_cursor_round_trip(invoke, space):
    ids = {create_issue(invoke)["issue_id"] for _ in range(3)}

    first = invoke("get_issues_by_status", space_id="ENG", status="TODO", limit=2)
    page, cursor = first["data"]["items"], first["data"]["cursor"]
    assert len(page) == 2
    assert isinstance(cursor, str)

    second = invoke("get_issues_by_status", space_id="ENG", status="TODO",
                    limit=2, cursor=cursor)
    rest = second["data"]["items"]
    assert {i["issue_id"] for i in page + rest} == ids


def test_add_and_get_issue_blockers(invoke, space):
    blocking = create_issue(invoke)
    blocked = create_issue(invoke)

    added = invoke("add_issue_blocker",
                   blocking_issue_space_id="ENG", blocking_issue_id=blocking["issue_id"],
                   blocked_issue_space_id="ENG", blocked_issue_id=blocked["issue_id"])
    assert added["ok"] is True

    response = invoke("get_issue_blockers", space_id="ENG",
                      blocked_issue_id=blocked["issue_id"])
    blockers = response["data"]["items"]
    assert [b["blocking_issue_id"] for b in blockers] == [blocking["issue_id"]]


def test_comment_round_trip(invoke, space):
    issue = create_issue(invoke)
    comment = create_comment(invoke, issue, body="first")

    fetched = invoke("get_issue_comment", space_id="ENG",
                     issue_id=issue["issue_id"],
                     comment_id=comment["comment_id"])
    assert fetched["ok"] is True
    assert fetched["data"]["body"] == "first"
    assert fetched["data"]["creator"] == "alice"


def test_comment_on_missing_issue_maps_ddb_error(invoke, space):
    response = invoke("create_issue_comment", space_id="ENG", issue_id="nope12",
                      body="b", creator="alice")
    assert response["ok"] is False
    assert response["error"]["type"] == "DDBMissingError"


def test_issue_results_include_num_comments(invoke, space):
    issue = create_issue(invoke)
    assert issue["num_comments"] == 0
    create_comment(invoke, issue)

    fetched = invoke("get_issue", space_id="ENG", issue_id=issue["issue_id"])
    assert fetched["data"]["num_comments"] == 1


def test_get_issue_comments_pages_in_creation_order(invoke, space):
    issue = create_issue(invoke)
    bodies = [create_comment(invoke, issue, body=str(n))["body"] for n in range(3)]

    first = invoke("get_issue_comments", space_id="ENG",
                   issue_id=issue["issue_id"], limit=2)
    page, cursor = first["data"]["items"], first["data"]["cursor"]
    assert [c["body"] for c in page] == bodies[:2]
    assert isinstance(cursor, str)

    second = invoke("get_issue_comments", space_id="ENG",
                    issue_id=issue["issue_id"], limit=2, cursor=cursor)
    assert [c["body"] for c in second["data"]["items"]] == bodies[2:]


def test_update_comment_replaces_the_body(invoke, space):
    issue = create_issue(invoke)
    comment = create_comment(invoke, issue, body="first")

    response = invoke("update_issue_comment", space_id="ENG",
                      issue_id=issue["issue_id"],
                      comment_id=comment["comment_id"], body="second",
                      version=comment["version"])
    assert response["ok"] is True
    assert response["data"]["body"] == "second"
    assert response["data"]["creator"] == "alice"


def test_stale_comment_version_maps_ddb_error(invoke, space):
    issue = create_issue(invoke)
    comment = create_comment(invoke, issue)

    response = invoke("update_issue_comment", space_id="ENG",
                      issue_id=issue["issue_id"],
                      comment_id=comment["comment_id"], body="b",
                      version=comment["version"] + 1)
    assert response["ok"] is False
    assert response["error"]["type"] == "DDBVersionConflictError"


def test_delete_comment_uncounts_it(invoke, space):
    issue = create_issue(invoke)
    comment = create_comment(invoke, issue)

    response = invoke("delete_issue_comment", space_id="ENG",
                      issue_id=issue["issue_id"],
                      comment_id=comment["comment_id"])
    assert response == {"ok": True, "data": None}

    fetched = invoke("get_issue", space_id="ENG", issue_id=issue["issue_id"])
    assert fetched["data"]["num_comments"] == 0


def test_comments_do_not_gate_deleting_the_issue(invoke, space):
    """The sweep itself is pl8-event-handler's, driven by IssueDeleted."""
    issue = create_issue(invoke)
    create_comment(invoke, issue)

    response = invoke("delete_issue", space_id="ENG", issue_id=issue["issue_id"])
    assert response == {"ok": True, "data": None}
