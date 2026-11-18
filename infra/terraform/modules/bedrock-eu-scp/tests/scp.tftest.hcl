mock_provider "aws" {}

variables {
  allowed_regions = ["eu-central-1", "eu-north-1", "eu-south-1", "eu-south-2", "eu-west-1", "eu-west-3"]
  target_ids      = ["ou-abcd-11111111"]
}

run "renders_three_denies" {
  command = plan
  assert {
    condition     = length(jsondecode(output.policy_json).Statement) == 3
    error_message = "Expected three Deny statements."
  }
  assert {
    condition     = alltrue([for s in jsondecode(output.policy_json).Statement : s.Effect == "Deny"])
    error_message = "An SCP of the kit only denies."
  }
}

run "refuses_us_region" {
  command = plan
  variables {
    allowed_regions = ["eu-west-3", "us-east-1"]
  }
  expect_failures = [var.allowed_regions]
}

run "exemption_is_applied_to_every_statement" {
  command = plan
  variables {
    exempt_principal_arns = ["arn:aws:iam::111122223333:role/break-glass"]
  }
  assert {
    condition     = alltrue([for s in jsondecode(output.policy_json).Statement : can(s.Condition.ArnNotLike)])
    error_message = "Break-glass exemption missing on a statement."
  }
}
