from pl8_base.types import (
    IssueDeleted,
    IssueDone,
    IssueInfo,
    IssueNumActiveBlockersZeroed,
    IssueReady,
    IssueStatus,
)

ISSUE_INFO_SK = IssueInfo.KEY_ATTRS["SK"]


def _issue_info(image):
    """Read the fields event detection needs from an IssueInfo stream image.

    Reads raw attributes rather than parsing the whole item: the handler has
    no use for the rest (description is gzipped), and a malformed field it
    doesn't need must not stall the shard.

    Returns None unless the image is an IssueInfo row. The type is checked as
    well as the SK so that anything else written at that key, which pl8-base
    never does, is skipped rather than misread.
    """
    if not image or image.get("SK", {}).get("S") != ISSUE_INFO_SK:
        return None

    if image.get("type", {}).get("S") != "IssueInfo":
        return None

    return {
        "space_id": image["space_id"]["S"],
        "issue_id": image["issue_id"]["S"],
        "status": image["status"]["S"],
        "num_active_blockers": int(image.get("num_active_blockers", {}).get("N", "0")),
    }


def events_for_record(record):
    """Map one DynamoDB stream record to the PL8 events it implies.

    See pl8-docs architecture/backend/events.md. Only IssueInfo rows produce
    events; blocker and space rows map to nothing.

    Args:
        record (dict): a DynamoDB stream record, as delivered to Lambda

    Returns:
        list[BaseEvent]: events to send, in order; empty if none
    """
    event_name = record["eventName"]
    ddb = record["dynamodb"]
    old = _issue_info(ddb.get("OldImage"))
    new = _issue_info(ddb.get("NewImage"))

    if event_name == "INSERT":
        # An Issue created DONE has nothing to unblock, so no IssueDone.
        if new and new["status"] == IssueStatus.TODO:
            return [IssueReady(space_id=new["space_id"], issue_id=new["issue_id"])]
        return []

    if event_name == "REMOVE":
        if old:
            return [IssueDeleted(space_id=old["space_id"], issue_id=old["issue_id"])]
        return []

    if event_name != "MODIFY" or not (old and new):
        return []

    ids = {"space_id": new["space_id"], "issue_id": new["issue_id"]}
    events = []

    if old["status"] != IssueStatus.DONE and new["status"] == IssueStatus.DONE:
        events.append(IssueDone(**ids))

    if old["num_active_blockers"] > 0 and new["num_active_blockers"] == 0:
        events.append(IssueNumActiveBlockersZeroed(**ids))

    if old["status"] != IssueStatus.TODO and new["status"] == IssueStatus.TODO:
        events.append(IssueReady(**ids))

    return events
