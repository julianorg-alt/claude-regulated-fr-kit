mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "111122223333" }
  }
  mock_data "aws_region" {
    defaults = { region = "eu-west-3" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
}

run "worm_and_validation" {
  command = plan
  assert {
    condition     = aws_s3_bucket_object_lock_configuration.audit.rule[0].default_retention[0].mode == "COMPLIANCE"
    error_message = "Logs must be locked in compliance mode."
  }
  assert {
    condition     = aws_cloudtrail.audit.enable_log_file_validation
    error_message = "Log file validation must be on (tamper evidence)."
  }
  assert {
    condition     = aws_kms_key.audit.enable_key_rotation
    error_message = "KMS key rotation must be on."
  }
}

run "retention_bounds" {
  command = plan
  variables {
    retention_days = 30
  }
  expect_failures = [var.retention_days]
}
