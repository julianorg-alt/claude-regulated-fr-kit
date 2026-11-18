variable "name" {
  description = "Name of the IAM role assumed by the LLM gateway."
  type        = string
  default     = "claude-gateway-bedrock-eu"
}

variable "account_id" {
  description = "AWS account that owns the inference profiles (12 digits)."
  type        = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be a 12-digit AWS account id."
  }
}

variable "models" {
  description = "Claude models the gateway may call, by inventory name (for example \"Claude Sonnet 5\")."
  type        = list(string)
  validation {
    condition     = length(var.models) > 0
    error_message = "At least one model is required."
  }
  validation {
    condition     = alltrue([for m in var.models : !can(regex("(?i)fable|mythos", m))])
    error_message = "Claude Fable and Mythos have no EU profile on Bedrock and retain traffic for 30 days (docs/sources/verifications.md V8, V9)."
  }
}

variable "mode" {
  description = "geo: eu. profile through bedrock-runtime (multi-country EU). in_region_mantle: single-Region processing through bedrock-mantle."
  type        = string
  default     = "geo"
  validation {
    condition     = contains(["geo", "in_region_mantle"], var.mode)
    error_message = "mode must be geo or in_region_mantle."
  }
}

variable "source_region" {
  description = "Region the gateway calls. Must be an EU member-state Region (London and Zurich add non-EU destinations, see V5)."
  type        = string
  default     = "eu-west-3"
}

variable "residency" {
  description = "eu (default, EU member states only) or eu_plus_adequacy (adds London and Zurich)."
  type        = string
  default     = "eu"
  validation {
    condition     = contains(["eu", "eu_plus_adequacy"], var.residency)
    error_message = "residency must be eu or eu_plus_adequacy."
  }
}

variable "routes_file" {
  description = "Route inventory produced by tools/crfr/bedrock_inventory.py for the chosen residency."
  type        = string
  default     = null
}

variable "trusted_principal_arns" {
  description = "Principals allowed to assume the gateway role (the gateway's workload identity)."
  type        = list(string)
  validation {
    condition     = length(var.trusted_principal_arns) > 0
    error_message = "At least one trusted principal is required."
  }
}

variable "permissions_boundary_arn" {
  description = "Optional permissions boundary attached to the role."
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default     = {}
}

variable "kill_switch" {
  description = "Level 3 of the gateway kill switch (backlog E2.6): attach an explicit deny on every Bedrock action to the gateway role. An explicit deny overrides any allow; IAM changes are eventually consistent, so the delay before it applies everywhere is not guaranteed by AWS (verifications.md V18). Levels 1 and 2 act in seconds at the gateway."
  type        = bool
  default     = false
}
