locals {
  pl8_interface_name = "${var.environment}-pl8-interface"
  # Built by src/pl8-interface/build.sh; must exist before plan.
  pl8_interface_zip = "${path.module}/../src/pl8-interface/dist/pl8-interface.zip"
}

data "aws_iam_policy_document" "pl8_interface_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "pl8_interface" {
  name               = local.pl8_interface_name
  assume_role_policy = data.aws_iam_policy_document.pl8_interface_assume_role.json
}

data "aws_iam_policy_document" "pl8_interface_execution" {
  statement {
    sid       = "CloudWatchLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.pl8_interface.arn}:*"]
  }

  # Exactly the calls pl8-base's CRUD/query methods make. ConditionCheckItem
  # covers the ConditionCheck inside add_issue_blocker's transaction.
  statement {
    sid    = "PL8TableAccess"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:TransactWriteItems",
      "dynamodb:ConditionCheckItem",
    ]
    resources = [
      aws_dynamodb_table.pl8_table.arn,
      "${aws_dynamodb_table.pl8_table.arn}/index/GSI1",
    ]
  }
}

resource "aws_iam_role_policy" "pl8_interface_execution" {
  name   = "${local.pl8_interface_name}-execution"
  role   = aws_iam_role.pl8_interface.id
  policy = data.aws_iam_policy_document.pl8_interface_execution.json
}

resource "aws_cloudwatch_log_group" "pl8_interface" {
  name              = "/aws/lambda/${local.pl8_interface_name}"
  retention_in_days = var.pl8_interface_log_retention_days
}

resource "aws_lambda_function" "pl8_interface" {
  function_name = local.pl8_interface_name
  role          = aws_iam_role.pl8_interface.arn

  filename         = local.pl8_interface_zip
  source_code_hash = filebase64sha256(local.pl8_interface_zip)
  handler          = "pl8_interface.handler.lambda_handler"
  runtime          = "python3.14"
  architectures    = ["arm64"]

  memory_size = var.pl8_interface_memory_mb
  timeout     = var.pl8_interface_timeout_seconds

  environment {
    variables = {
      PL8_TABLE_NAME          = aws_dynamodb_table.pl8_table.name
      POWERTOOLS_SERVICE_NAME = "pl8-interface"
    }
  }

  # Agents are granted invoke on functions carrying this tag, outside this repo.
  tags = {
    Type = "PL8Interface"
  }

  depends_on = [
    aws_cloudwatch_log_group.pl8_interface,
    aws_iam_role_policy.pl8_interface_execution,
  ]
}
