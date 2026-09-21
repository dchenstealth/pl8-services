def create_issue(invoke, status="TODO", space_id="ENG"):
    response = invoke("create_issue", space_id=space_id, title="t",
                      description="d", status=status)
    assert response["ok"] is True
    return response["data"]


def test_space_round_trip(invoke):
    created = invoke("create_space", space_id="ENG", name="Eng", description="d")
    assert created["ok"] is True

    fetched = invoke("get_space", space_id="ENG")
    assert fetched["ok"] is True
    assert fetched["data"]["space_id"] == "ENG"
    assert fetched["data"]["name"] == "Eng"
    assert fetched["data"]["description"] == "d"


def test_missing_space_maps_ddb_error(invoke):
    response = invoke("get_space", space_id="ENG")
    assert response["ok"] is False
    assert response["error"]["type"] == "DDBMissingError"


def test_transition_issue(invoke):
    issue = create_issue(invoke)

    response = invoke("transition_issue", space_id="ENG",
                      issue_id=issue["issue_id"], status="IN_PROGRESS")
    assert response["ok"] is True
    assert response["data"]["status"] == "IN_PROGRESS"


def test_transition_out_of_done_maps_ddb_error(invoke):
    issue = create_issue(invoke, status="DONE")

    response = invoke("transition_issue", space_id="ENG",
                      issue_id=issue["issue_id"], status="TODO")
    assert response["ok"] is False
    assert response["error"]["type"] == "DDBTerminalStatusError"


def test_get_issues_by_status_cursor_round_trip(invoke):
    ids = {create_issue(invoke)["issue_id"] for _ in range(3)}

    first = invoke("get_issues_by_status", space_id="ENG", status="TODO", limit=2)
    page, cursor = first["data"]["items"], first["data"]["cursor"]
    assert len(page) == 2
    assert isinstance(cursor, str)

    second = invoke("get_issues_by_status", space_id="ENG", status="TODO",
                    limit=2, cursor=cursor)
    rest = second["data"]["items"]
    assert {i["issue_id"] for i in page + rest} == ids


def test_add_and_get_issue_blockers(invoke):
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
