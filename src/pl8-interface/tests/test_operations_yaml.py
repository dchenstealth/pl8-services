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
    "get_issue_comments_after", "update_issue_comment", "delete_issue_comment",
    "initiate_issue_attachment_upload", "resign_issue_attachment_upload",
    "confirm_issue_attachment_uploaded", "get_issue_attachment",
    "get_issue_attachments", "get_issue_comment_attachments",
    "delete_issue_attachment",
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


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e["method"])
def test_response_shape_markers_are_exclusive(entry):
    """paginated: true and returns: [names] are the two shapes an operation's
    result can take beyond a single entity; nothing may claim both."""
    names = entry.get("returns")

    if names is not None:
        assert isinstance(names, list)
        assert names and all(isinstance(name, str) and name for name in names)
        assert len(set(names)) == len(names)
        assert not entry.get("paginated", False)


@pytest.mark.parametrize("returns", [
    "dict",             # the shape, not the names
    [],                 # a tuple of nothing
    ["attachment", ""],
    ["attachment", "attachment"],
])
def test_rejects_malformed_returns(tmp_path, mgr, logger, returns):
    path = tmp_path / "operations.yaml"
    path.write_text(yaml.safe_dump({"operations": [
        {"method": "get_space", "returns": returns,
         "schema": {"type": "object"}}]}))

    with pytest.raises(ValueError, match="get_space"):
        InterfaceManager(mgr, logger, operations=path)


def test_rejects_returns_combined_with_paginated(tmp_path, mgr, logger):
    path = tmp_path / "operations.yaml"
    path.write_text(yaml.safe_dump({"operations": [
        {"method": "get_spaces", "returns": ["items", "cursor"],
         "paginated": True, "schema": {"type": "object"}}]}))

    with pytest.raises(ValueError, match="get_spaces"):
        InterfaceManager(mgr, logger, operations=path)


@pytest.mark.parametrize("method", ["handle_issue_done", "_private", "no_such_method"])
def test_rejects_non_invokable_methods(tmp_path, mgr, logger, method):
    path = tmp_path / "operations.yaml"
    path.write_text(yaml.safe_dump(
        {"operations": [{"method": method, "schema": {"type": "object"}}]}))

    with pytest.raises(ValueError, match=method):
        InterfaceManager(mgr, logger, operations=path)
