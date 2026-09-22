variable "name" {
  type        = string
  description = "Function name; also names its role, execution policy and log group"
}

variable "source_dir" {
  type        = string
  description = "Directory zipped as the function's code (its source package only; dependencies ship in the layer)"
}

variable "zip_output_path" {
  type        = string
  description = "Where to write the function's zip"
}

variable "handler" {
  type        = string
  description = "Lambda handler, as module.function"
}

variable "layers" {
  type        = list(string)
  description = "Layer version ARNs attached to the function"
  default     = []
}

variable "memory_mb" {
  type        = number
  description = "Memory (MB) allocated to the function"
}

variable "timeout_seconds" {
  type        = number
  description = "Invocation timeout (seconds)"
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch Logs retention period for the function's log group"
}

variable "environment_variables" {
  type        = map(string)
  description = "Environment variables set on the function"
  default     = {}
}

variable "policy_statements" {
  type = list(object({
    sid       = string
    actions   = list(string)
    resources = list(string)
  }))
  description = "Allow statements granted to the function's role, beyond writing to its own log group"
}

variable "tags" {
  type        = map(string)
  description = "Tags set on the function"
  default     = {}
}
