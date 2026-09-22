output "pl8_table_name" {
  value       = aws_dynamodb_table.pl8_table.name
  description = "Name of the pl8 DynamoDB table"
}

output "pl8_table_stream_arn" {
  value       = aws_dynamodb_table.pl8_table.stream_arn
  description = "Stream ARN for the pl8 table, consumed by pl8-stream-handler"
}

output "pl8_event_bus_name" {
  value       = aws_cloudwatch_event_bus.pl8.name
  description = "Name of the pl8 EventBridge event bus"
}

output "pl8_event_handler_queue_arn" {
  value       = aws_sqs_queue.event_handler.arn
  description = "ARN of the SQS queue feeding pl8-event-handler"
}

output "pl8_interface_function_name" {
  value       = module.pl8_interface.function_name
  description = "Name of the pl8-interface Lambda, for pl8-cli invoke configuration"
}

output "pl8_interface_function_arn" {
  value       = module.pl8_interface.function_arn
  description = "ARN of the pl8-interface Lambda"
}

output "pl8_stream_handler_function_name" {
  value       = module.pl8_stream_handler.function_name
  description = "Name of the pl8-stream-handler Lambda"
}

output "pl8_stream_handler_dlq_arn" {
  value       = aws_sqs_queue.stream_handler_dlq.arn
  description = "ARN of the pl8-stream-handler on-failure destination queue"
}

output "pl8_event_handler_function_name" {
  value       = module.pl8_event_handler.function_name
  description = "Name of the pl8-event-handler Lambda"
}

output "pl8_event_handler_dlq_arn" {
  value       = aws_sqs_queue.event_handler_dlq.arn
  description = "ARN of the pl8-event-handler dead-letter queue"
}
