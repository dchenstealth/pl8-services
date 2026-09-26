locals {
  base_bucket_name = "${var.environment}-pl8-bucket"
}

# Holds IssueAttachment objects, under space/{space_id}/issue/{issue_id}/...
# (see pl8-base). Callers never touch the bucket directly: pl8-interface hands
# out presigned URLs and the object bytes go straight between the caller and
# S3.
#
# MUST be in the same region as the Lambdas that sign for it. A presigned
# request to the wrong regional endpoint is answered with a 307 redirect, and
# following it re-signs nothing: the signature covers the host it was made
# for, so the redirected request fails authentication. Both come from
# var.aws_region here, so they cannot diverge.
#
# force_destroy is deliberately left unset (false): the bucket holds caller
# data, and terraform destroy must not empty it, matching the table's
# deletion_protection_enabled.
resource "aws_s3_bucket" "pl8_bucket" {
  bucket           = format("%s-%s-%s-an", local.base_bucket_name, data.aws_caller_identity.current.account_id, data.aws_region.current.region)
  bucket_namespace = "account-regional"
}

resource "aws_s3_bucket_versioning" "pl8_bucket_versioning" {
  bucket = aws_s3_bucket.pl8_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

# AES256 (SSE-S3) rather than SSE-KMS, deliberately. A presigned URL is meant
# to be self-contained: whoever holds it can use it with no AWS credentials of
# their own. Reading a KMS-encrypted object requires the *caller* to hold
# kms:Decrypt on the key, and writing one requires kms:GenerateDataKey, so a
# KMS bucket would break exactly that property. SSE-S3 needs no permission
# from the URL's consumer.
resource "aws_s3_bucket_server_side_encryption_configuration" "pl8_bucket_encryption" {
  bucket = aws_s3_bucket.pl8_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "pl8_bucket_public_block" {
  bucket = aws_s3_bucket.pl8_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "pl8_bucket_expire_noncurrent" {
  bucket = aws_s3_bucket.pl8_bucket.id

  rule {
    id     = "expire-noncurrent"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.pl8_bucket_versioning]
}
