from aws_lambda_powertools.utilities.batch import (
    BatchProcessor,
    EventType,
    process_partial_response,
)
from pl8_base.types import IssueDeleted, IssueDone, IssueNumActiveBlockersZeroed
from pl8_base.util import parse_event

# Core lifecycle events and the BasePL8 handler each one drives. Must match
# the detail-types infra/eventbridge.tf routes to this function's queue.
HANDLERS = {
    IssueDone: "handle_issue_done",
    IssueDeleted: "handle_issue_deleted",
    IssueNumActiveBlockersZeroed: "handle_issue_num_active_blockers_zeroed",
}

# Per-record log keys. Reset for every record, so one record's keys never
# appear on the next record's log lines.
RECORD_LOG_KEYS = ("message_id", "event_type", "event_id", "space_id", "issue_id")


class UnhandledEventError(Exception):
    """Raised for a well-formed PL8 event this function has no handler for."""


class EventManager:
    """Applies the core lifecycle events delivered by SQS onto a BasePL8."""

    def __init__(self, pl8, logger):
        self._pl8 = pl8
        self._logger = logger
        # Logs each failed record, with its traceback, at warning level. An
        # entirely failed batch is reported like any other rather than raised,
        # so the function's Errors metric counts only crashes, not bad
        # messages; the DLQ alarm covers those.
        self._processor = BatchProcessor(event_type=EventType.SQS, logger=logger,
                                         raise_on_entire_batch_failure=False)

    def handle_event(self, event, context=None):
        """Apply each SQS record's event, reporting failures per record.

        Any exception fails only its own record. The handle_* methods are
        idempotent and tolerate late or duplicate delivery, so a failed
        record is simply redelivered, and after the queue's maxReceiveCount
        it lands in the DLQ. That holds even when every record fails: each
        is reported, and the invocation still succeeds.

        Returns:
            dict: {"batchItemFailures": [...]} partial batch response
        """
        try:
            return process_partial_response(event=event, context=context,
                                            processor=self._processor,
                                            record_handler=self.handle_record)
        finally:
            self._logger.remove_keys(RECORD_LOG_KEYS)

    def handle_record(self, record):
        """Apply one SQSRecord's event, raising if it should be retried.

        Raises:
            ValueError, KeyError, TypeError: if the body isn't an
                EventBridge envelope
            EventCorruptedError: if its detail isn't a valid PL8 event
            UnhandledEventError: if the event isn't a core lifecycle event
            DDBError: if the handle_* call fails
        """
        self._logger.append_keys(**(dict.fromkeys(RECORD_LOG_KEYS)
                                    | {"message_id": record.message_id}))

        # SQS carries the whole EventBridge envelope; the PL8 event is its
        # detail.
        pl8_event = parse_event(record.json_body["detail"])
        event_type = type(pl8_event).__name__
        self._logger.append_keys(event_type=event_type,
                                 event_id=pl8_event.event_id,
                                 space_id=pl8_event.space_id,
                                 issue_id=pl8_event.issue_id)

        method = HANDLERS.get(type(pl8_event))
        if method is None:
            raise UnhandledEventError(f"No handler for {event_type}")

        getattr(self._pl8, method)(space_id=pl8_event.space_id,
                                   issue_id=pl8_event.issue_id)
        self._logger.info("Handled event")
