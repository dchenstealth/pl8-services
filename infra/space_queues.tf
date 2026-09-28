locals {
  # One file per environment, so each can watch different spaces. A missing
  # file means no space queues.
  space_queues_config_file = "${path.module}/space_queues/${var.environment}.yaml"
  space_queues_config = (
    fileexists(local.space_queues_config_file)
    ? yamldecode(file(local.space_queues_config_file))
    : { spaces = [] }
  )

  # Keyed by space id; a space listed twice fails the plan on the duplicate
  # key.
  space_queues = {
    for space in coalesce(local.space_queues_config.spaces, []) :
    space.space_id => space
  }

  # Every event type pl8-stream-handler sends (pl8-docs events.md). A typo
  # in the config would otherwise leave a queue that silently never
  # receives anything.
  pl8_event_types = [
    "IssueNumActiveBlockersZeroed",
    "IssueDeleted",
    "IssueDone",
    "IssueCommentDeleted",
    "IssueAttachmentDeleted",
    "IssueReady",
  ]
}

resource "aws_sqs_queue" "space" {
  for_each = local.space_queues

  name                      = "${var.environment}-pl8-space-${each.key}"
  message_retention_seconds = each.value.message_retention_seconds
  receive_wait_time_seconds = each.value.receive_wait_time_seconds

  # Lets watchers be granted access by tag, the way pl8-interface's invoke
  # permission is.
  tags = {
    Type    = "PL8SpaceQueue"
    SpaceId = each.key
  }

  lifecycle {
    precondition {
      condition     = can(regex("^[A-Za-z0-9_-]{1,64}$", each.key))
      error_message = "space_queues: \"${each.key}\" is not a valid space id."
    }
    precondition {
      # SQS queue names are capped at 80 characters.
      condition     = length("${var.environment}-pl8-space-${each.key}") <= 80
      error_message = "space_queues: queue name for \"${each.key}\" exceeds 80 characters."
    }
    precondition {
      condition = (
        length(each.value.events) > 0
        && length(setsubtract(each.value.events, local.pl8_event_types)) == 0
      )
      error_message = "space_queues: \"${each.key}\" events must be non-empty and drawn from ${join(", ", local.pl8_event_types)}."
    }
  }
}

resource "aws_cloudwatch_event_rule" "space" {
  for_each = local.space_queues

  name           = "${var.environment}-pl8-space-${each.key}"
  event_bus_name = aws_cloudwatch_event_bus.pl8.name

  event_pattern = jsonencode({
    source      = [local.pl8_event_source]
    detail-type = each.value.events
    detail      = { space_id = [each.key] }
  })
}

resource "aws_cloudwatch_event_target" "space_queue" {
  for_each = local.space_queues

  rule           = aws_cloudwatch_event_rule.space[each.key].name
  event_bus_name = aws_cloudwatch_event_bus.pl8.name
  arn            = aws_sqs_queue.space[each.key].arn
}

resource "aws_sqs_queue_policy" "space" {
  for_each = local.space_queues

  queue_url = aws_sqs_queue.space[each.key].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "events.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.space[each.key].arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_cloudwatch_event_rule.space[each.key].arn
          }
        }
      }
    ]
  })
}
