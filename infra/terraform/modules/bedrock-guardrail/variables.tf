variable "name" {
  description = "Guardrail name."
  type        = string
  default     = "claude-gateway-pii-last-layer"
}

variable "action" {
  description = "ANONYMIZE (replace by the type tag, irreversible) or BLOCK (refuse the whole request or answer)."
  type        = string
  default     = "ANONYMIZE"
  validation {
    condition     = contains(["ANONYMIZE", "BLOCK"], var.action)
    error_message = "action must be ANONYMIZE or BLOCK."
  }
}

variable "kms_key_arn" {
  description = "Customer managed KMS key for the guardrail (optional)."
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags for every resource."
  type        = map(string)
  default     = {}
}
