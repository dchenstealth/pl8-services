resource "aws_dynamodb_table" "pl8_table" {
  name                        = "${var.environment}-pl8-table"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "PK"
  range_key                   = "SK"
  deletion_protection_enabled = true

  # Enables pl8-stream-handler to react to entity changes (see
  # pl8-docs/architecture/backend/events.md). Both images are needed to
  # detect transitions such as status moving to DONE or
  # num_active_blockers zeroing.
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  on_demand_throughput {
    max_read_request_units  = var.pl8_table_on_demand_read_request_units
    max_write_request_units = var.pl8_table_on_demand_write_request_units
  }

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  # GSI1PK/GSI1SK are NOT declared here. aws_dynamodb_global_secondary_index
  # (below) adds them via its own UpdateTable call, whose key_schema already
  # carries their attribute_type. Declaring them on the table too would put
  # them in this resource's CreateTable call unused by any key schema here,
  # which AWS rejects with "All attributes must be indexed".
}

resource "aws_dynamodb_global_secondary_index" "gsi1" {
  table_name = aws_dynamodb_table.pl8_table.name
  index_name = "GSI1"

  projection {
    projection_type = "ALL"
  }

  key_schema {
    attribute_name = "GSI1PK"
    attribute_type = "S"
    key_type       = "HASH"
  }

  key_schema {
    attribute_name = "GSI1SK"
    attribute_type = "S"
    key_type       = "RANGE"
  }
}
