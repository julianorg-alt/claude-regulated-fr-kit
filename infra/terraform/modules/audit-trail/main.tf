# Audit trail of Bedrock calls (backlog E1.4). Synchronous inference (InvokeModel, Converse and
# their streaming variants) is recorded as CloudTrail management events (verifications.md V10);
# asynchronous and bidirectional calls need data-event selectors, enabled here.
# Logs land in an S3 bucket with Object Lock in compliance mode (WORM), encrypted with a
# customer-managed KMS key. Retention follows CNIL recommendation 2021-122 (6 to 12 months by
# default, longer only if justified).

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

variable "name" {
  type    = string
  default = "claude-bedrock-audit"
}

variable "retention_days" {
  description = "Object Lock retention in compliance mode. Cannot be shortened once objects are written."
  type        = number
  default     = 365
  validation {
    condition     = var.retention_days >= 180 && var.retention_days <= 1095
    error_message = "retention_days must be between 180 (6 months) and 1095 (3 years, only with a documented justification)."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  account   = data.aws_caller_identity.current.account_id
  region    = data.aws_region.current.region
  partition = data.aws_partition.current.partition
  trail_arn = "arn:${local.partition}:cloudtrail:${local.region}:${local.account}:trail/${var.name}"
}

resource "aws_kms_key" "audit" {
  description         = "${var.name} log encryption"
  enable_key_rotation = true
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AccountAdmin"
        Effect    = "Allow"
        Principal = { AWS = "arn:${local.partition}:iam::${local.account}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "CloudTrailEncrypt"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = ["kms:GenerateDataKey*", "kms:DescribeKey"]
        Resource  = "*"
        Condition = {
          StringEquals = { "aws:SourceArn" = local.trail_arn }
          StringLike   = { "kms:EncryptionContext:aws:cloudtrail:arn" = "arn:${local.partition}:cloudtrail:*:${local.account}:trail/*" }
        }
      },
    ]
  })
  tags = var.tags
}

resource "aws_s3_bucket" "audit" {
  bucket_prefix       = "${var.name}-"
  object_lock_enabled = true
  tags                = var.tags
}

resource "aws_s3_bucket_public_access_block" "audit" {
  bucket                  = aws_s3_bucket.audit.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "audit" {
  bucket = aws_s3_bucket.audit.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_object_lock_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    default_retention {
      mode = "COMPLIANCE"
      days = var.retention_days
    }
  }
  depends_on = [aws_s3_bucket_versioning.audit]
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.audit.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_policy" "audit" {
  bucket = aws_s3_bucket.audit.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "CloudTrailAclCheck"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:GetBucketAcl"
        Resource  = aws_s3_bucket.audit.arn
        Condition = { StringEquals = { "aws:SourceArn" = local.trail_arn } }
      },
      {
        Sid       = "CloudTrailWrite"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.audit.arn}/AWSLogs/${local.account}/*"
        Condition = { StringEquals = { "s3:x-amz-acl" = "bucket-owner-full-control", "aws:SourceArn" = local.trail_arn } }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.audit.arn, "${aws_s3_bucket.audit.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
    ]
  })
}

resource "aws_cloudtrail" "audit" {
  name                          = var.name
  s3_bucket_name                = aws_s3_bucket.audit.id
  kms_key_id                    = aws_kms_key.audit.arn
  is_multi_region_trail         = true
  include_global_service_events = true
  enable_log_file_validation    = true

  advanced_event_selector {
    name = "Management events (synchronous Bedrock inference)"
    field_selector {
      field  = "eventCategory"
      equals = ["Management"]
    }
  }
  advanced_event_selector {
    name = "Bedrock data events (async and bidirectional inference)"
    field_selector {
      field  = "eventCategory"
      equals = ["Data"]
    }
    field_selector {
      field  = "eventSource"
      equals = ["bedrock.amazonaws.com"]
    }
  }
  tags       = var.tags
  depends_on = [aws_s3_bucket_policy.audit]
}

output "trail_arn" {
  value = aws_cloudtrail.audit.arn
}

output "bucket" {
  value = aws_s3_bucket.audit.id
}
