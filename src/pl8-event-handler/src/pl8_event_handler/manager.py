import json

from pl8_base.errors import DDBError, EventCorruptedError
from pl8_base.types import IssueDeleted, IssueDone, IssueNumActiveBlockersZeroed
from pl8_base.util import parse_event

# Core lifecycle events and the BasePL8 handler each one drives. Must match
# the detail-types infra/eventbridge.tf routes to this function's queue.
HANDLERS = {
    IssueDone: "handle_issue_done",
    IssueDeleted: "handle_issue_deleted",
    IssueNumActiveBlockersZeroed: "handle_issue_num_active_blockers_zeroed",
}


class EventManager:
    """Applies the core lifecycle events delivered by SQS onto a BasePL8."""

    def __init__(self, pl8, logger):
        self._pl8 = pl8
        self._logger = logger

    def handle_event(self, event):
        """Apply each SQS record's event, reporting failures per record.

        The handle_* methods are idempotent and tolerate late or duplicate
        delivery, so a failed record is simply redelivered, and after the
        queue's maxReceiveCount it lands in the DLQ.

        Any exception other than the ones handled below is a bug and fails
        the whole invocation, so the batch is redelivered.

        Returns:
            dict: {"batchItemFailures": [...]} partial batch response
        """
        failures = []

        for record in event["Records"]:
            message_id = record["messageId"]
            if not self.handle_record(record, message_id):
                failures.append({"itemIdentifier": message_id})

        return {"batchItemFailures": failures}

    def handle_record(self, record, message_id):
        """Apply one record's event. Returns False if it should be retried."""
        try:
            # SQS carries the whole EventBridge envelope; the PL8 event is its
            # detail.
            pl8_event = parse_event(json.loads(record["body"])["detail"])
        except (ValueError, KeyError, TypeError, EventCorruptedError) as exc:
            self._logger.error("Malformed event", message_id=message_id,
                               error=str(exc))
            return False

        event_type = type(pl8_event).__name__
        method = HANDLERS.get(type(pl8_event))
        if method is None:
            self._logger.error("Unhandled event type", message_id=message_id,
                               event_type=event_type)
            return False

        log_fields = {"message_id": message_id, "event_type": event_type,
                      "event_id": pl8_event.event_id,
                      "space_id": pl8_event.space_id,
                      "issue_id": pl8_event.issue_id}

        try:
            getattr(self._pl8, method)(space_id=pl8_event.space_id,
                                       issue_id=pl8_event.issue_id)
        except DDBError as exc:
            self._logger.exception("Failed to handle event",
                                   error_type=type(exc).__name__, **log_fields)
            return False

        self._logger.info("Handled event", **log_fields)
        return True
