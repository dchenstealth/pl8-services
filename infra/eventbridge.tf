resource "aws_cloudwatch_event_bus" "pl8" {
  name = "${var.environment}-pl8-events"
}

# Routes pl8's internal lifecycle events (see
# pl8-base/src/pl8_base/types/events.py) to the event-handler queue.
# IssueReady is consumer-facing and deliberately not matched here —
# external consumers add their own rules against this bus.
resource "aws_cloudwatch_event_rule" "core_lifecycle" {
  name           = "${var.environment}-pl8-core-lifecycle"
  event_bus_name = aws_cloudwatch_event_bus.pl8.name

  event_pattern = jsonencode({
    detail-type = [
      "IssueNumActiveBlockersZeroed",
      "IssueDeleted",
      "IssueDone",
    ]
  })
}

resource "aws_cloudwatch_event_target" "event_handler_queue" {
  rule           = aws_cloudwatch_event_rule.core_lifecycle.name
  event_bus_name = aws_cloudwatch_event_bus.pl8.name
  arn            = aws_sqs_queue.event_handler.arn
}
