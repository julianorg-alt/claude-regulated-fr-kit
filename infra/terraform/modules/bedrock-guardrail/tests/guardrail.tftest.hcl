# Runs offline: the AWS provider is mocked, no credentials needed (decision K3).
mock_provider "aws" {}

run "anonymize_by_default" {
  command = plan
  assert {
    condition     = alltrue([for p in aws_bedrock_guardrail.pii.sensitive_information_policy_config[0].pii_entities_config : p.action == "ANONYMIZE"])
    error_message = "Every PII type must be anonymised by default."
  }
  assert {
    condition     = contains([for p in aws_bedrock_guardrail.pii.sensitive_information_policy_config[0].pii_entities_config : p.type], "INTERNATIONAL_BANK_ACCOUNT_NUMBER")
    error_message = "IBANs must be covered."
  }
  assert {
    condition     = length(aws_bedrock_guardrail.pii.sensitive_information_policy_config[0].regexes_config) == 2
    error_message = "The French NIR and IBAN shapes must be covered by regexes."
  }
}

run "regexes_have_no_lookaround" {
  command = plan
  assert {
    condition     = alltrue([for r in aws_bedrock_guardrail.pii.sensitive_information_policy_config[0].regexes_config : !can(regex("\\(\\?<?[=!]", r.pattern)) && length(r.pattern) <= 500])
    error_message = "Guardrails regexes allow no lookaround and at most 500 characters."
  }
}

run "block_mode" {
  command = plan
  variables {
    action = "BLOCK"
  }
  assert {
    condition     = alltrue([for r in aws_bedrock_guardrail.pii.sensitive_information_policy_config[0].regexes_config : r.action == "BLOCK"])
    error_message = "BLOCK must apply to the regexes too."
  }
}

run "unknown_action_refused" {
  command = plan
  variables {
    action = "LOG"
  }
  expect_failures = [var.action]
}
