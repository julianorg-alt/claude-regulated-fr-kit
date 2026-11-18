# Organisation-wide guardrail (backlog E1.2): the same residency rules as the IAM module,
# enforced as a Service Control Policy so that no role in the targeted accounts can bypass them.
# AWS: if any destination Region of a profile is blocked by an SCP, the request fails
# (docs/sources/verifications.md V3), so allowed_regions must contain every destination.

variable "name" {
  type    = string
  default = "bedrock-eu-residency"
}

variable "allowed_regions" {
  description = "Every Region where Bedrock may process requests: source Regions plus all destinations (output allowed_regions of bedrock-eu-access)."
  type        = list(string)
  validation {
    condition     = length(var.allowed_regions) > 0 && alltrue([for r in var.allowed_regions : can(regex("^eu-(central|north|south|west)-[0-9]$", r))])
    error_message = "allowed_regions must be non-empty and contain only eu-* Regions."
  }
}

variable "target_ids" {
  description = "Organisation root, OU or account ids the SCP is attached to."
  type        = list(string)
  default     = []
}

variable "exempt_principal_arns" {
  description = "Break-glass principals exempted from the SCP (keep empty unless documented in the exit plan)."
  type        = list(string)
  default     = []
}

variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  actions = ["bedrock:InvokeModel*", "bedrock:Converse*", "bedrock:StartAsyncInvoke", "bedrock-mantle:*"]
  exempt  = length(var.exempt_principal_arns) == 0 ? {} : { ArnNotLike = { "aws:PrincipalArn" = var.exempt_principal_arns } }
  policy = {
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyBedrockOutsideAllowedRegions"
        Effect    = "Deny"
        Action    = local.actions
        Resource  = "*"
        Condition = merge({ StringNotEquals = { "aws:RequestedRegion" = var.allowed_regions } }, local.exempt)
      },
      {
        Sid       = "DenyGlobalRouting"
        Effect    = "Deny"
        Action    = local.actions
        Resource  = "*"
        Condition = merge({ StringEquals = { "aws:RequestedRegion" = "unspecified" } }, local.exempt)
      },
      merge({
        Sid    = "DenyNonEuProfilesFableMythos"
        Effect = "Deny"
        Action = local.actions
        Resource = concat(
          [for p in ["global", "us", "us-gov", "apac", "au", "jp", "in", "ca"] : "arn:aws:bedrock:*:*:inference-profile/${p}.*"],
          ["arn:aws:bedrock:*::foundation-model/anthropic.claude-fable-*", "arn:aws:bedrock:*::foundation-model/anthropic.claude-mythos-*"]
        )
      }, length(local.exempt) == 0 ? {} : { Condition = local.exempt }),
    ]
  }
}

resource "aws_organizations_policy" "this" {
  name        = var.name
  description = "Claude on Bedrock: EU processing only (claude-regulated-fr)"
  type        = "SERVICE_CONTROL_POLICY"
  content     = jsonencode(local.policy)
  tags        = var.tags
}

resource "aws_organizations_policy_attachment" "this" {
  for_each  = toset(var.target_ids)
  policy_id = aws_organizations_policy.this.id
  target_id = each.value
}

output "policy_json" {
  value = jsonencode(local.policy)
}
