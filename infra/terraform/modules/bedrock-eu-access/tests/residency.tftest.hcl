# Runs offline: the AWS provider is mocked, no credentials needed (decision K3).
mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
}

variables {
  account_id             = "111122223333"
  trusted_principal_arns = ["arn:aws:iam::111122223333:role/gateway-workload"]
  models                 = ["Claude Sonnet 5", "Claude Opus 5.5"]
}

run "paris_geo_stays_in_eu" {
  command = plan

  assert {
    condition     = length(output.routes) == 2
    error_message = "Both models must have a geo route from Paris."
  }
  assert {
    condition     = length(setsubtract(output.allowed_regions, ["eu-central-1", "eu-north-1", "eu-south-1", "eu-south-2", "eu-west-1", "eu-west-3"])) == 0
    error_message = "A Region outside the EU is reachable."
  }
  assert {
    condition     = strcontains(output.policy_json, "inference-profile/eu.anthropic.claude-sonnet-5")
    error_message = "The eu. profile must be allowed."
  }
  assert {
    condition     = strcontains(output.policy_json, "\"aws:RequestedRegion\":\"unspecified\"")
    error_message = "Global routing must be denied (V11)."
  }
  assert {
    condition     = strcontains(output.policy_json, "inference-profile/global.*")
    error_message = "global.* profiles must be denied."
  }
  assert {
    condition     = strcontains(output.policy_json, "foundation-model/anthropic.claude-fable-*")
    error_message = "Fable must be denied."
  }
}

run "london_source_refused_in_strict_eu" {
  command = plan
  variables {
    source_region = "eu-west-2"
  }
  expect_failures = [terraform_data.residency_guard]
}

run "london_source_accepted_with_adequacy" {
  command = plan
  variables {
    source_region = "eu-west-2"
    residency     = "eu_plus_adequacy"
  }
  assert {
    condition     = contains(output.allowed_regions, "eu-west-2")
    error_message = "London must be a destination when called from London."
  }
}

run "us_source_refused" {
  command = plan
  variables {
    source_region = "us-east-1"
  }
  expect_failures = [terraform_data.residency_guard]
}

run "fable_refused_by_validation" {
  command = plan
  variables {
    models = ["Claude Fable 5.2"]
  }
  expect_failures = [var.models]
}

run "model_without_route_refused" {
  command = plan
  variables {
    models = ["Claude 3 Haiku"]
  }
  expect_failures = [terraform_data.residency_guard]
}

run "in_region_ireland_via_mantle" {
  command = plan
  variables {
    mode          = "in_region_mantle"
    source_region = "eu-west-1"
    models        = ["Claude Sonnet 5"]
  }
  assert {
    condition     = length(output.allowed_regions) == 1 && output.allowed_regions[0] == "eu-west-1"
    error_message = "In-Region mode must process in Ireland only."
  }
  assert {
    condition     = strcontains(output.policy_json, "bedrock-mantle:CreateInference")
    error_message = "Mantle inference action must be allowed."
  }
}

run "in_region_unavailable_model_refused" {
  command = plan
  variables {
    mode          = "in_region_mantle"
    source_region = "eu-west-1"
    models        = ["Claude Opus 5.5"]
  }
  expect_failures = [terraform_data.residency_guard]
}

run "kill_switch_off_by_default" {
  command = plan
  assert {
    condition     = length(aws_iam_role_policy.kill_switch) == 0
    error_message = "The kill switch must be off unless asked for."
  }
}

run "kill_switch_denies_every_bedrock_action" {
  command = plan
  variables {
    kill_switch = true
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.kill_switch[0].policy).Statement[0].Effect == "Deny"
    error_message = "The kill switch must be an explicit deny."
  }
  assert {
    condition     = contains(jsondecode(aws_iam_role_policy.kill_switch[0].policy).Statement[0].Action, "bedrock:*") && contains(jsondecode(aws_iam_role_policy.kill_switch[0].policy).Statement[0].Action, "bedrock-mantle:*")
    error_message = "The kill switch must cover bedrock-runtime and bedrock-mantle."
  }
}
