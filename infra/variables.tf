variable "aws_region" {
  type        = string
  description = "AWS Region"
}

variable "environment" {
  type        = string
  description = "Environment"
}

variable "pl8_table_on_demand_read_request_units" {
  type        = number
  description = "Max read request units for the pl8 table (assumes on-demand mode)"
}

variable "pl8_table_on_demand_write_request_units" {
  type        = number
  description = "Max write request units for the pl8 table (assumes on-demand mode)"
}

variable "event_queue_visibility_timeout_seconds" {
  type        = number
  description = "Visibility timeout for the pl8 event-handler SQS queue. AWS recommends 6x pl8_event_handler_timeout_seconds or more"
}

variable "event_queue_max_receive_count" {
  type        = number
  description = "Number of times a message may be received from the event-handler queue before moving to its DLQ"
}

variable "event_queue_message_retention_seconds" {
  type        = number
  description = "Message retention period for the event-handler queue and its DLQ"
}

variable "pl8_interface_memory_mb" {
  type        = number
  description = "Memory (MB) allocated to the pl8-interface Lambda"
}

variable "pl8_interface_timeout_seconds" {
  type        = number
  description = "Invocation timeout (seconds) for the pl8-interface Lambda"
}

variable "pl8_interface_log_retention_days" {
  type        = number
  description = "CloudWatch Logs retention period for the pl8-interface Lambda"
}

variable "pl8_stream_handler_memory_mb" {
  type        = number
  description = "Memory (MB) allocated to the pl8-stream-handler Lambda"
}

variable "pl8_stream_handler_timeout_seconds" {
  type        = number
  description = "Invocation timeout (seconds) for the pl8-stream-handler Lambda"
}

variable "pl8_stream_handler_log_retention_days" {
  type        = number
  description = "CloudWatch Logs retention period for the pl8-stream-handler Lambda"
}

variable "pl8_stream_handler_batch_size" {
  type        = number
  description = "Max stream records per pl8-stream-handler invocation"
}

variable "pl8_stream_handler_maximum_retry_attempts" {
  type        = number
  description = "Retries for a failing stream batch before its metadata goes to the stream-handler DLQ"
}

variable "pl8_event_handler_memory_mb" {
  type        = number
  description = "Memory (MB) allocated to the pl8-event-handler Lambda"
}

variable "pl8_event_handler_timeout_seconds" {
  type        = number
  description = "Invocation timeout (seconds) for the pl8-event-handler Lambda. Keep event_queue_visibility_timeout_seconds at 6x or more"
}

variable "pl8_event_handler_log_retention_days" {
  type        = number
  description = "CloudWatch Logs retention period for the pl8-event-handler Lambda"
}

variable "pl8_event_handler_batch_size" {
  type        = number
  description = "Max SQS messages per pl8-event-handler invocation"
}

variable "alarm_actions" {
  type        = list(string)
  description = "ARNs (e.g. SNS topics) notified when a DLQ alarm changes state"
  default     = []
}
