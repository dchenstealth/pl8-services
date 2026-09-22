import os

import boto3
from aws_lambda_powertools import Logger

from pl8_stream_handler.manager import StreamManager

logger = Logger()
manager = StreamManager(
    events_client=boto3.client("events"),
    event_bus_name=os.environ["PL8_EVENT_BUS_NAME"],
    source=os.environ["PL8_EVENT_SOURCE"],
    logger=logger,
)


@logger.inject_lambda_context
def lambda_handler(event, context):
    return manager.handle_event(event)
