import pytest
import yaml
from pl8_base.errors import (
    DDBAttachmentStatusError,
    DDBInternalError,
    StorageInternalError,
    StorageObjectMissingError,
)
from pl8_base.types import SpaceInfo

from pl8_interface.manager import InterfaceManager


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


@pytest.mark.parametrize("field, other", [("name", "description"),
                                          ("description", "name")])
def test_update_space_changes_one_field_alone(invoke, space, field, other):
    response = invoke("update_space", space_id="ENG", **{field: "new"})
    assert response["ok"] is True
    assert response["data"][field] == "new"
    assert response["data"][other] == space[other]


@pytest.mark.parametrize("field, other", [("title", "description"),
                                          ("description", "title")])
def test_update_issue_changes_one_field_alone(invoke, space, field, other):
    issue = create_issue(invoke)

    response = invoke("update_issue", space_id="ENG",
                      issue_id=issue["issue_id"], **{field: "new"})
    assert response["ok"] is True
    assert response["data"][field] == "new"
    assert response["data"][other] == issue[other]


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


@pytest.fixture
def named_result_invoke(mgr, logger, tmp_path):
    """An interface whose one operation names the parts of its result tuple.

    Marked on a plain read here, so the unpacking is exercised on its own
    rather than through whichever attachment operation happens to return what.
    """
    path = tmp_path / "operations.yaml"
    path.write_text(yaml.safe_dump({"operations": [{
        "method": "get_space",
        "returns": ["space", "upload"],
        "schema": {"type": "object", "additionalProperties": False,
                   "required": ["space_id"],
                   "properties": {"space_id": {"type": "string"}}},
    }]}))
    interface = InterfaceManager(mgr, logger, operations=path)

    def _invoke(**params):
        return interface.handle_event({"operation": "get_space",
                                       "params": params})
    return _invoke


def test_named_result_shapes_the_entity_and_passes_the_rest(named_result_invoke,
                                                            mgr, monkeypatch):
    """A tuple of an entity plus a presigned target: the entity is shaped like
    any other result, and what is not an entity attribute is carried through
    untouched, under the names operations.yaml gave."""
    space = SpaceInfo(space_id="ENG", name="Eng", description="d",
                      creator="alice")
    upload = {"url": "https://example.invalid/upload",
              "fields": {"key": "space/ENG/object"}}
    monkeypatch.setattr(mgr, "get_space", lambda **kwargs: (space, upload))

    data = named_result_invoke(space_id="ENG")["data"]

    assert data.keys() == {"space", "upload"}
    assert data["upload"] == upload
    assert data["space"]["space_id"] == "ENG"
    assert not {"PK", "SK", "GSI1PK", "GSI1SK"} & data["space"].keys()


def test_named_result_carries_a_null_part(named_result_invoke, mgr, monkeypatch):
    """get_issue_attachment's download URL is None until the attachment is
    UPLOADED, and null is a result, not a missing key."""
    space = SpaceInfo(space_id="ENG", name="Eng", description="d",
                      creator="alice")
    monkeypatch.setattr(mgr, "get_space", lambda **kwargs: (space, None))

    assert named_result_invoke(space_id="ENG")["data"]["upload"] is None


@pytest.mark.parametrize("result", [
    ("one",),
    ("one", "two", "three"),
])
def test_named_result_length_mismatch_faults(named_result_invoke, mgr, monkeypatch,
                                             result):
    """The marker and the method disagreeing would drop or invent a part, so it
    faults rather than answering with a half-shaped result."""
    monkeypatch.setattr(mgr, "get_space", lambda **kwargs: result)

    with pytest.raises(ValueError, match="get_space"):
        named_result_invoke(space_id="ENG")


@pytest.mark.parametrize(("exc", "expected_message"), [
    # A storage fault is hidden like a database fault: the detail would name
    # the bucket.
    (StorageInternalError("arn:aws:s3:::secret-bucket"), "Internal error"),
    # Caller-fixable: the bytes were never POSTed, so there is nothing to
    # confirm. Escaping as a FunctionError would report this as a fault.
    (StorageObjectMissingError("Object not found"), "Object not found"),
    # The row is not PENDING, so the caller already confirmed it.
    (DDBAttachmentStatusError("Attachment is not PENDING"),
     "Attachment is not PENDING"),
])
def test_attachment_errors_map_to_error_responses(invoke, mgr, monkeypatch, exc,
                                                  expected_message):
    def boom(**kwargs):
        raise exc

    monkeypatch.setattr(mgr, "confirm_issue_attachment_uploaded", boom)

    response = invoke("confirm_issue_attachment_uploaded", space_id="ENG",
                      issue_id="abc123", attachment_id="att001")

    assert response == {"ok": False, "error": {"type": type(exc).__name__,
                                               "message": expected_message}}
