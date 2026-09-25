locals {
  pl8_interface_name = "${var.environment}-pl8-interface"
  lambda_build_dir   = "${path.module}/../src/build"
  lambda_src_dir     = "${path.module}/../src"

  # EventBridge Source on every event pl8-stream-handler sends.
  pl8_event_source = "pl8"

  # The table and its one GSI, as IAM resources.
  pl8_table_resources = [
    aws_dynamodb_table.pl8_table.arn,
    "${aws_dynamodb_table.pl8_table.arn}/index/GSI1",
  ]
}

# Third-party dependencies shared by every pl8-services Lambda, installed by
# src/build-layer.sh (must run before plan). Function zips hold only their own
# code. Fixed file modes keep the hash identical across machines regardless of
# umask; archive_file already ignores mtimes.
data "archive_file" "pl8_deps_layer" {
  type             = "zip"
  source_dir       = "${local.lambda_build_dir}/layer"
  output_path      = "${local.lambda_build_dir}/pl8-deps-layer.zip"
  output_file_mode = "0644"
}

resource "aws_lambda_layer_version" "pl8_deps" {
  layer_name               = "${var.environment}-pl8-deps"
  filename                 = data.archive_file.pl8_deps_layer.output_path
  source_code_hash         = data.archive_file.pl8_deps_layer.output_base64sha256
  compatible_runtimes      = ["python3.14"]
  compatible_architectures = ["arm64"]
}

module "pl8_interface" {
  source = "./modules/lambda_function"

  name            = local.pl8_interface_name
  source_dir      = "${local.lambda_src_dir}/pl8-interface/src"
  zip_output_path = "${local.lambda_build_dir}/pl8-interface.zip"
  handler         = "pl8_interface.handler.lambda_handler"
  layers          = [aws_lambda_layer_version.pl8_deps.arn]

  memory_mb          = var.pl8_interface_memory_mb
  timeout_seconds    = var.pl8_interface_timeout_seconds
  log_retention_days = var.pl8_interface_log_retention_days

  environment_variables = {
    PL8_TABLE_NAME          = aws_dynamodb_table.pl8_table.name
    POWERTOOLS_SERVICE_NAME = "pl8-interface"
  }

  # Exactly the calls pl8-base's CRUD/query methods make. ConditionCheckItem
  # covers the ConditionCheck inside add_issue_blocker's transaction.
  policy_statements = [{
    sid = "PL8TableAccess"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:TransactWriteItems",
      "dynamodb:ConditionCheckItem",
    ]
    resources = local.pl8_table_resources
  }]

  # Agents are granted invoke on functions carrying this tag, outside this repo.
  tags = {
    Type = "PL8Interface"
  }
}

moved {
  from = aws_iam_role.pl8_interface
  to   = module.pl8_interface.aws_iam_role.this
}

moved {
  from = aws_iam_role_policy.pl8_interface_execution
  to   = module.pl8_interface.aws_iam_role_policy.execution
}

moved {
  from = aws_cloudwatch_log_group.pl8_interface
  to   = module.pl8_interface.aws_cloudwatch_log_group.this
}

moved {
  from = aws_lambda_function.pl8_interface
  to   = module.pl8_interface.aws_lambda_function.this
}

module "pl8_stream_handler" {
  source = "./modules/lambda_function"

  name            = "${var.environment}-pl8-stream-handler"
  source_dir      = "${local.lambda_src_dir}/pl8-stream-handler/src"
  zip_output_path = "${local.lambda_build_dir}/pl8-stream-handler.zip"
  handler         = "pl8_stream_handler.handler.lambda_handler"
  layers          = [aws_lambda_layer_version.pl8_deps.arn]

  memory_mb          = var.pl8_stream_handler_memory_mb
  timeout_seconds    = var.pl8_stream_handler_timeout_seconds
  log_retention_days = var.pl8_stream_handler_log_retention_days

  environment_variables = {
    PL8_EVENT_BUS_NAME      = aws_cloudwatch_event_bus.pl8.name
    PL8_EVENT_SOURCE        = local.pl8_event_source
    POWERTOOLS_SERVICE_NAME = "pl8-stream-handler"
  }

  policy_statements = [
    {
      sid = "PL8TableStreamRead"
      actions = [
        "dynamodb:DescribeStream",
        "dynamodb:GetRecords",
        "dynamodb:GetShardIterator",
        "dynamodb:ListStreams",
      ]
      resources = [aws_dynamodb_table.pl8_table.stream_arn]
    },
    {
      sid       = "PL8EventBusPut"
      actions   = ["events:PutEvents"]
      resources = [aws_cloudwatch_event_bus.pl8.arn]
    },
    {
      # Lambda sends the on-failure destination record as the function's role.
      sid       = "StreamHandlerDLQSend"
      actions   = ["sqs:SendMessage"]
      resources = [aws_sqs_queue.stream_handler_dlq.arn]
    },
  ]
}

resource "aws_lambda_event_source_mapping" "pl8_stream_handler" {
  event_source_arn  = aws_dynamodb_table.pl8_table.stream_arn
  function_name     = module.pl8_stream_handler.function_name
  starting_position = "LATEST"
  batch_size        = var.pl8_stream_handler_batch_size

  # The handler reports the first record it failed to send, so the shard
  # resumes from there in order. Bisecting isolates a record that fails the
  # whole invocation. After the retries, the record's metadata goes to the
  # DLQ rather than being dropped when the stream's 24h retention expires.
  function_response_types        = ["ReportBatchItemFailures"]
  bisect_batch_on_function_error = true
  maximum_retry_attempts         = var.pl8_stream_handler_maximum_retry_attempts

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.stream_handler_dlq.arn
    }
  }

  # Only IssueInfo rows produce events (see src/pl8-stream-handler), so
  # blocker, comment and space rows never invoke the function. SpaceInfo
  # shares the 100#INFO SK, hence the PK prefix too, and an IssueComment
  # shares its Issue's PK, so the SK is what excludes it. The Issue counters
  # a blocker or comment write moves in the same transaction are on the
  # IssueInfo row, so those still invoke it: a num_active_blockers change can
  # emit an event, a num_comments change never does. Both come from
  # IssueInfo.KEY_ATTRS in pl8-base (pl8_base/types/issue.py); keep them in
  # step if the key format changes.
  filter_criteria {
    filter {
      pattern = jsonencode({
        dynamodb = {
          Keys = {
            PK = { S = [{ prefix = "ISSUE#" }] }
            SK = { S = ["100#INFO"] }
          }
        }
      })
    }
  }
}

module "pl8_event_handler" {
  source = "./modules/lambda_function"

  name            = "${var.environment}-pl8-event-handler"
  source_dir      = "${local.lambda_src_dir}/pl8-event-handler/src"
  zip_output_path = "${local.lambda_build_dir}/pl8-event-handler.zip"
  handler         = "pl8_event_handler.handler.lambda_handler"
  layers          = [aws_lambda_layer_version.pl8_deps.arn]

  memory_mb          = var.pl8_event_handler_memory_mb
  timeout_seconds    = var.pl8_event_handler_timeout_seconds
  log_retention_days = var.pl8_event_handler_log_retention_days

  environment_variables = {
    PL8_TABLE_NAME          = aws_dynamodb_table.pl8_table.name
    POWERTOOLS_SERVICE_NAME = "pl8-event-handler"
  }

  policy_statements = [
    {
      sid = "EventHandlerQueueConsume"
      actions = [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
      ]
      resources = [aws_sqs_queue.event_handler.arn]
    },
    {
      # Exactly the calls pl8-base's handle_* methods make: blocker queries
      # (both directions, so GSI1) and the consistent partition read that
      # sweeps a deleted Issue's comments and blockers, conditioned updates
      # and deletes, and the ConditionCheck inside satisfy_issue_blocker's
      # transaction.
      sid = "PL8TableAccess"
      actions = [
        "dynamodb:Query",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:TransactWriteItems",
        "dynamodb:ConditionCheckItem",
      ]
      resources = local.pl8_table_resources
    },
  ]
}

resource "aws_lambda_event_source_mapping" "pl8_event_handler" {
  event_source_arn = aws_sqs_queue.event_handler.arn
  function_name    = module.pl8_event_handler.function_name
  batch_size       = var.pl8_event_handler_batch_size

  # Failed records are redelivered alone; the queue's redrive policy moves
  # them to its DLQ after maxReceiveCount.
  function_response_types = ["ReportBatchItemFailures"]
}
