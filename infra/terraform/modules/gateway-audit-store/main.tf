# Storage of the gateway's audit trail (backlog E5.2). Two buckets and two KMS keys:
# - audit: decision lines without content, shipped by the audit shipper; Object Lock in compliance
#   mode, so that no one, root included, can delete or shorten them before the end of retention.
#   Retention follows CNIL recommendation 2021-122: 6 months to 1 year, up to 3 years only with a
#   documented justification (verifications.md V32).
# - content: optional pseudonymised requests and answers, expired after a few days.
# - an HMAC KMS key for the fingerprints and MAC chain of the audit lines (GenerateMac); the key
#   material never leaves KMS. HMAC keys do not support automatic rotation (V33).
# The module outputs the IAM policies of the two writers; neither may delete anything.

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

variable "name" {
  description = "Prefix of the bucket and key names."
  type        = string
  default     = "crfr-gateway-audit"
}

variable "audit_retention_days" {
  description = "Object Lock retention of audit lines, compliance mode. Cannot be shortened once objects are written."
  type        = number
  default     = 365
  validation {
    condition     = var.audit_retention_days >= 180 && var.audit_retention_days <= 1095
    error_message = "audit_retention_days must be between 180 (6 months) and 1095 (3 years, only with a documented justification)."
  }
}

variable "content_retention_days" {
  description = "Days before pseudonymised content is deleted."
  type        = number
  default     = 7
  validation {
    condition     = var.content_retention_days >= 1 && var.content_retention_days <= 30
    error_message = "content_retention_days must be between 1 and 30."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  account   = data.aws_caller_identity.current.account_id
  partition = data.aws_partition.current.partition
  buckets   = { audit = aws_s3_bucket.audit, content = aws_s3_bucket.content }
}

resource "aws_kms_key" "storage" {
  description         = "${var.name} storage encryption"
  enable_key_rotation = true
  tags                = var.tags
}

resource "aws_kms_key" "mac" {
  description              = "${var.name} audit line fingerprints and MAC chain"
  customer_master_key_spec = "HMAC_256"
  key_usage                = "GENERATE_VERIFY_MAC"
  tags                     = var.tags
}

resource "aws_s3_bucket" "audit" {
  bucket              = "${var.name}-${local.account}"
  object_lock_enabled = true
  tags                = var.tags
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
      days = var.audit_retention_days
    }
  }
  depends_on = [aws_s3_bucket_versioning.audit]
}

resource "aws_s3_bucket" "content" {
  bucket = "${var.name}-content-${local.account}"
  tags   = var.tags
}

resource "aws_s3_bucket_lifecycle_configuration" "content" {
  bucket = aws_s3_bucket.content.id
  rule {
    id     = "expire-content"
    status = "Enabled"
    filter {}
    expiration {
      days = var.content_retention_days
    }
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each                = local.buckets
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = local.buckets
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.storage.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_policy" "this" {
  for_each = local.buckets
  bucket   = each.value.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [each.value.arn, "${each.value.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

locals {
  # The shipper writes and checks audit segments; it cannot delete, overwrite retention or read content.
  shipper_policy = {
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "WriteAndCheckAuditSegments"
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject", "s3:GetObjectRetention"]
        Resource = "${aws_s3_bucket.audit.arn}/audit/*"
      },
      {
        Sid      = "EncryptSegments"
        Effect   = "Allow"
        Action   = ["kms:GenerateDataKey", "kms:Decrypt"]
        Resource = aws_kms_key.storage.arn
      },
    ]
  }
  # The guard computes MACs with the HMAC key and writes pseudonymised content; it cannot read either bucket back.
  guard_policy = {
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AuditMac"
        Effect   = "Allow"
        Action   = "kms:GenerateMac"
        Resource = aws_kms_key.mac.arn
      },
      {
        Sid      = "WriteContent"
        Effect   = "Allow"
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.content.arn}/*"
      },
      {
        Sid      = "EncryptContent"
        Effect   = "Allow"
        Action   = "kms:GenerateDataKey"
        Resource = aws_kms_key.storage.arn
      },
    ]
  }
}

output "audit_bucket" {
  value = aws_s3_bucket.audit.bucket
}

output "content_bucket" {
  value = aws_s3_bucket.content.bucket
}

output "mac_key_arn" {
  description = "HMAC key for the guard's KmsMac (audit fingerprints and MAC chain)."
  value       = aws_kms_key.mac.arn
}

output "shipper_policy_json" {
  value = jsonencode(local.shipper_policy)
}

output "guard_policy_json" {
  value = jsonencode(local.guard_policy)
}
