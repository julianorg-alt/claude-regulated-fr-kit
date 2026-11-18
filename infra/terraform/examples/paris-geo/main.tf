# Reference deployment: the gateway in Paris calls Claude through the eu. profile.
# `make plan-offline` plans it without an AWS account (fake credentials, no API call) and checks
# the plan with the conftest policies in policy/terraform.

terraform {
  required_version = ">= 1.9.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0.0, < 7.0.0"
    }
  }
}

variable "offline" {
  description = "true for CI: fake credentials and no AWS API call."
  type        = bool
  default     = false
}

variable "account_id" {
  type    = string
  default = "111122223333"
}

provider "aws" {
  region                      = "eu-west-3"
  access_key                  = var.offline ? "offline-plan" : null
  secret_key                  = var.offline ? "offline-plan" : null
  skip_credentials_validation = var.offline
  skip_requesting_account_id  = var.offline
  skip_metadata_api_check     = var.offline
  skip_region_validation      = var.offline
}

module "bedrock_eu" {
  source                 = "../../modules/bedrock-eu-access"
  account_id             = var.account_id
  models                 = ["Claude Sonnet 5", "Claude Opus 5.5", "Claude Haiku 4.5"]
  source_region          = "eu-west-3"
  trusted_principal_arns = ["arn:aws:iam::${var.account_id}:role/claude-gateway-workload"]
  tags = {
    project = "claude-regulated-fr"
  }
}

output "allowed_regions" {
  value = module.bedrock_eu.allowed_regions
}

# Egress of the gateway: HTTPS to the Bedrock interface endpoint of Paris only (E2.7).
module "gateway_egress" {
  source           = "../../modules/gateway-egress"
  region           = "eu-west-3"
  vpc_id           = "vpc-0123456789abcdef0"
  subnet_ids       = ["subnet-0123456789abcdef0", "subnet-0123456789abcdef1"]
  gateway_role_arn = module.bedrock_eu.role_arn
  tags = {
    project = "claude-regulated-fr"
  }
}
