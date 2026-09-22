locals {
  pl8_interface_name = "${var.environment}-pl8-interface"
  lambda_build_dir   = "${path.module}/../src/build"
  lambda_src_dir     = "${path.module}/../src"

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
