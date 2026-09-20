resource "aws_sqs_queue" "event_handler_dlq" {
  name                      = "${var.environment}-pl8-event-handler-dlq"
  message_retention_seconds = var.event_queue_message_retention_seconds
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
