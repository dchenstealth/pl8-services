# Anything in either DLQ is an event PL8 failed to publish or apply, so
# Issues may be stuck (e.g. BLOCKED with no active blockers).
locals {
  pl8_dlqs = {
    stream-handler = aws_sqs_queue.stream_handler_dlq.name
    event-handler  = aws_sqs_queue.event_handler_dlq.name
  }
}

resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  for_each = local.pl8_dlqs

  alarm_name          = "${var.environment}-pl8-${each.key}-dlq-not-empty"
  alarm_description   = "Messages in ${each.value}: PL8 lifecycle events failed. Inspect, fix, then redrive."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = each.value }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  alarm_actions = var.alarm_actions
  ok_actions    = var.alarm_actions
}
