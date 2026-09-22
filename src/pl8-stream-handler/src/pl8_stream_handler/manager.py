from botocore.exceptions import ClientError
from pl8_base.errors import EventSendError
from pl8_base.util import send_event

from pl8_stream_handler.mapping import events_for_record


class StreamManager:
    """Publishes the PL8 events implied by a batch of DynamoDB stream records."""

    def __init__(self, *, events_client, event_bus_name, source, logger):
        self._events_client = events_client
        self._event_bus_name = event_bus_name
        self._source = source
        self._logger = logger

    def handle_event(self, event):
        """Send each record's events, one at a time, in shard order.

        Stops at the first record that fails to send and reports it, so
        Lambda retries the shard from there and events are never sent out of
        order. Events already sent for that record are sent again on the
        retry; delivery is at-least-once.

        Returns:
            dict: {"batchItemFailures": [...]} partial batch response
        """
        for record in event["Records"]:
            sequence_number = record["dynamodb"]["SequenceNumber"]

            for pl8_event in events_for_record(record):
                try:
                    send_event(events_client=self._events_client,
                               event=pl8_event, source=self._source,
                               event_bus_name=self._event_bus_name)
                except (EventSendError, ClientError):
                    self._logger.exception("Failed to send event",
                                           event_type=type(pl8_event).__name__,
                                           event_id=pl8_event.event_id,
                                           sequence_number=sequence_number)
                    return {"batchItemFailures": [
                        {"itemIdentifier": sequence_number}]}

                self._logger.info("Sent event",
                                  event_type=type(pl8_event).__name__,
                                  event_id=pl8_event.event_id,
                                  space_id=pl8_event.space_id,
                                  issue_id=pl8_event.issue_id)

        return {"batchItemFailures": []}
