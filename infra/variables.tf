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
  description = "Visibility timeout for the pl8 event-handler SQS queue"
}

variable "event_queue_max_receive_count" {
  type        = number
  description = "Number of times a message may be received from the event-handler queue before moving to its DLQ"
}

variable "event_queue_message_retention_seconds" {
  type        = number
  description = "Message retention period for the event-handler queue and its DLQ"
}
