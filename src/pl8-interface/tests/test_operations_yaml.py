import inspect

import pytest
import yaml
from pl8_base.manager import BasePL8
from pl8_base.types import IssueStatus

from pl8_interface.manager import DEFAULT_OPERATIONS, InterfaceManager

EXPECTED_OPERATIONS = {
    "create_space", "get_space", "get_spaces", "update_space", "delete_space",
    "create_issue", "get_issue", "get_issues_by_status", "update_issue",
    "transition_issue", "delete_issue",
    "create_issue_comment", "get_issue_comment", "get_issue_comments",
    "update_issue_comment", "delete_issue_comment",
    "add_issue_blocker", "delete_issue_blocker",
    "get_issue_blockers", "get_issue_blocking",
}

ENTRIES = yaml.safe_load(DEFAULT_OPERATIONS.read_text())["operations"]


def test_lists_exactly_the_expected_operations():
    methods = [entry["method"] for entry in ENTRIES]
    assert len(methods) == len(set(methods))
    assert set(methods) == EXPECTED_OPERATIONS


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e["method"])
def test_schema_matches_signature(entry):
    params = inspect.signature(getattr(BasePL8, entry["method"])).parameters.values()
    kwonly = [p for p in params if p.kind is inspect.Parameter.KEYWORD_ONLY]
    assert len(kwonly) == len(params) - 1, "all params besides self must be keyword-only"

    schema = entry["schema"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {p.name for p in kwonly}
    assert set(schema["required"]) == {p.name for p in kwonly if p.default is p.empty}

    # Paginated methods, and only those, take a cursor.
    assert entry.get("paginated", False) == ("cursor" in schema["properties"])

    if "status" in schema["properties"]:
        assert set(schema["properties"]["status"]["enum"]) == set(IssueStatus)


@pytest.mark.parametrize("method", ["handle_issue_done", "_private", "no_such_method"])
def test_rejects_non_invokable_methods(tmp_path, mgr, logger, method):
    path = tmp_path / "operations.yaml"
    path.write_text(yaml.safe_dump(
        {"operations": [{"method": method, "schema": {"type": "object"}}]}))

    with pytest.raises(ValueError, match=method):
        InterfaceManager(mgr, logger, operations=path)
