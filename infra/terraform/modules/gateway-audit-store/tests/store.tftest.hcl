mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "111122223333" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_resource "aws_s3_bucket" {
    override_during = plan
    defaults        = { arn = "arn:aws:s3:::crfr-gateway-audit-111122223333" }
  }
  mock_resource "aws_kms_key" {
    override_during = plan
    defaults        = { arn = "arn:aws:kms:eu-west-3:111122223333:key/mock" }
  }
}

run "audit_is_worm_and_content_expires" {
  command = plan
  assert {
    condition     = aws_s3_bucket_object_lock_configuration.audit.rule[0].default_retention[0].mode == "COMPLIANCE"
    error_message = "Audit lines must be locked in compliance mode."
  }
  assert {
    condition     = aws_s3_bucket_object_lock_configuration.audit.rule[0].default_retention[0].days == 365
    error_message = "Default retention must be one year."
  }
  assert {
    condition     = aws_s3_bucket_lifecycle_configuration.content.rule[0].expiration[0].days == 7
    error_message = "Content must expire after content_retention_days."
  }
  assert {
    condition     = aws_kms_key.mac.customer_master_key_spec == "HMAC_256" && aws_kms_key.mac.key_usage == "GENERATE_VERIFY_MAC"
    error_message = "The MAC key must be an HMAC_256 KMS key."
  }
  assert {
    condition     = alltrue([for b in aws_s3_bucket_public_access_block.this : b.block_public_policy && b.restrict_public_buckets])
    error_message = "Both buckets must block public access."
  }
}

run "writers_cannot_delete" {
  command = plan
  assert {
    condition = length([
      for s in concat(jsondecode(output.shipper_policy_json).Statement, jsondecode(output.guard_policy_json).Statement) :
      s if length([for a in flatten([s.Action]) : a if can(regex("Delete|Bypass|PutObjectRetention|PutBucket|\\*", a))]) > 0
    ]) == 0
    error_message = "Shipper and guard policies must not allow deletion, retention changes or wildcards."
  }
}

run "audit_retention_bounds" {
  command = plan
  variables {
    audit_retention_days = 90
  }
  expect_failures = [var.audit_retention_days]
}

run "content_retention_bounds" {
  command = plan
  variables {
    content_retention_days = 90
  }
  expect_failures = [var.content_retention_days]
}
