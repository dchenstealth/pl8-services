locals {
  # Built rather than referenced from the resource to avoid a dependency
  # cycle: the DLQ's redrive_allow_policy needs this ARN, and
  # event_handler's own redrive_policy needs the DLQ's ARN in turn. SQS
  # ARNs are deterministic from account/region/name, so this is safe.
  event_handler_queue_arn = "arn:aws:sqs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:${var.environment}-pl8-event-handler"
}

resource "aws_sqs_queue" "event_handler_dlq" {
  name                      = "${var.environment}-pl8-event-handler-dlq"
  message_retention_seconds = var.event_queue_message_retention_seconds

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [local.event_handler_queue_arn]
  })
}

resource "aws_sqs_queue" "event_handler" {
  name                       = "${var.environment}-pl8-event-handler"
  visibility_timeout_seconds = var.event_queue_visibility_timeout_seconds
  message_retention_seconds  = var.event_queue_message_retention_seconds

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.event_handler_dlq.arn
    maxReceiveCount     = var.event_queue_max_receive_count
  })
}

# Lets the EventBridge rule deliver matching events onto this queue.
resource "aws_sqs_queue_policy" "event_handler" {
  queue_url = aws_sqs_queue.event_handler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "events.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.event_handler.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_cloudwatch_event_rule.core_lifecycle.arn
          }
        }
      }
    ]
  })
}

# On-failure destination for pl8-stream-handler: records it could not turn
# into events after its retries. Holds the stream batch's metadata (shard and
# sequence numbers), not the records themselves.
resource "aws_sqs_queue" "stream_handler_dlq" {
  name                      = "${var.environment}-pl8-stream-handler-dlq"
  message_retention_seconds = var.event_queue_message_retention_seconds
}
