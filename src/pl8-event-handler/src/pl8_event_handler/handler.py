import os

import boto3
from aws_lambda_powertools import Logger
from pl8_base.manager import BasePL8

from pl8_event_handler.manager import EventManager

logger = Logger()
manager = EventManager(
    BasePL8(
        dynamodb_client=boto3.client("dynamodb"),
        table_name=os.environ["PL8_TABLE_NAME"],
        # handle_issue_attachment_deleted deletes the object its row pointed
        # at, so this function needs the bucket as well as the table.
        s3_client=boto3.client("s3"),
        bucket_name=os.environ["PL8_BUCKET_NAME"],
        logger=logger,
    ),
    logger,
)


@logger.inject_lambda_context
def lambda_handler(event, context):
    return manager.handle_event(event, context)
