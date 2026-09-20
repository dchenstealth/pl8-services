output "pl8_table_name" {
  value       = aws_dynamodb_table.pl8_table.name
  description = "Name of the pl8 DynamoDB table"
}

output "pl8_table_stream_arn" {
  value       = aws_dynamodb_table.pl8_table.stream_arn
  description = "Stream ARN for the pl8 table, for a future pl8-stream-handler Lambda's event source mapping"
}

output "pl8_event_bus_name" {
  value       = aws_cloudwatch_event_bus.pl8.name
  description = "Name of the pl8 EventBridge event bus"
}

output "pl8_event_handler_queue_arn" {
  value       = aws_sqs_queue.event_handler.arn
  description = "ARN of the SQS queue feeding a future pl8-event-handler Lambda's event source mapping"
}
