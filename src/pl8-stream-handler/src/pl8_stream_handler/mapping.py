from pl8_base.types import (
    IssueAttachment,
    IssueAttachmentDeleted,
    IssueComment,
    IssueCommentDeleted,
    IssueDeleted,
    IssueDone,
    IssueInfo,
    IssueNumActiveBlockersZeroed,
    IssueReady,
    IssueStatus,
)

ISSUE_INFO_SK = IssueInfo.KEY_ATTRS["SK"]

# The literal part of each row's SK, ahead of its id. Taken from pl8-base's
# key formats rather than spelled out here, so a key format change cannot
# leave this module matching the old one. The event source mapping in
# infra/lambda.tf filters on these same prefixes and does have to spell them
# out; keep it in step.
COMMENT_SK_PREFIX = IssueComment.KEY_ATTRS["SK"].split("{", 1)[0]
ATTACHMENT_SK_PREFIX = IssueAttachment.KEY_ATTRS["SK"].split("{", 1)[0]

# principalId on a REMOVE that DynamoDB generated itself by expiring a row's
# TTL, rather than one a caller's DeleteItem produced.
TTL_PRINCIPAL_ID = "dynamodb.amazonaws.com"


def _is_row(image, *, sk_prefix, type_name):
    """Whether an image is a row of type_name whose SK starts with sk_prefix.

    Both checks matter, for the reason _issue_info gives: a sort key says
    where a row sits, not what it is, and reading one row type as another
    would either raise on a missing attribute or, worse, send an event naming
    an entity that does not exist.
    """
    if not image or not image.get("SK", {}).get("S", "").startswith(sk_prefix):
        return False

    return image.get("type", {}).get("S") == type_name


def _issue_info(image):
    """Read the fields event detection needs from an IssueInfo stream image.

    Reads raw attributes rather than parsing the whole item: the handler has
    no use for the rest (description is gzipped), and a malformed field it
    doesn't need must not stall the shard.

    Returns None unless the image is an IssueInfo row. The SK alone does not
    tell: SpaceInfo rows share SK 100#INFO. The event source mapping filters
    them out by PK, but this type check is what keeps them from being read as
    Issues (they have no issue_id) if the filter ever lets one through, so it
    must stay.
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


def _comment_row(image):
    """Read the ids naming an IssueComment from its stream image.

    Returns None unless the image is an IssueComment row; see _is_row. Only
    the ids are read: body is gzipped and nothing here needs it.
    """
    if not _is_row(image, sk_prefix=COMMENT_SK_PREFIX, type_name="IssueComment"):
        return None

    return {
        "space_id": image["space_id"]["S"],
        "issue_id": image["issue_id"]["S"],
        "comment_id": image["comment_id"]["S"],
    }


def _attachment_row(image):
    """Read the ids naming an IssueAttachment from its stream image.

    Returns None unless the image is an IssueAttachment row; see _is_row.
    """
    if not _is_row(image, sk_prefix=ATTACHMENT_SK_PREFIX,
                   type_name="IssueAttachment"):
        return None

    return {
        "space_id": image["space_id"]["S"],
        "issue_id": image["issue_id"]["S"],
        "attachment_id": image["attachment_id"]["S"],
    }


def is_ttl_expiry(record):
    """Whether DynamoDB, rather than a caller, removed the row."""
    return record.get("userIdentity", {}).get(
        "principalId") == TTL_PRINCIPAL_ID


def events_for_record(record):
    """Map one DynamoDB stream record to the PL8 events it implies.

    See pl8-docs architecture/backend/events.md. IssueInfo rows produce the
    Issue lifecycle events; a deleted IssueComment or IssueAttachment row
    produces the event that cascades its cleanup. Blocker and space rows map
    to nothing, and so do a comment or attachment create or update and an
    IssueInfo change to num_comments alone.

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
        old_image = ddb.get("OldImage")

        # A TTL expiry is mapped like any other REMOVE: the
        # IssueAttachmentDeleted it produces is what reaps an abandoned
        # upload's object. The manager logs which removals were expiries.
        comment = _comment_row(old_image)
        if comment:
            return [IssueCommentDeleted(**comment)]

        attachment = _attachment_row(old_image)
        if attachment:
            return [IssueAttachmentDeleted(**attachment)]

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
