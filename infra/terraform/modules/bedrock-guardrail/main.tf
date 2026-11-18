# Bedrock Guardrails as the last layer of pseudonymisation (backlog E3.6).
#
# Not sufficient alone, and irreversible:
# * ANONYMIZE replaces a value by its type tag ({NAME}, {EMAIL}); nothing maps it back, so the answer
#   cannot be re-identified, unlike the gateway's pseudonyms.
# * Guardrails has no French entity type (no NIR, SIREN, SIRET, tax number) and its regex filters
#   cannot check a key: the NIR regex below is a shape match only.
# * The trace of a guardrail keeps the original value, and invocation logs keep the original request
#   (verifications.md V31): the data still reaches AWS, the guardrail only hides it from the model.
# The gateway's pseudonymisation (pseudonymisation/, E3) is the control; this is defence in depth
# for an identifier the gateway missed.

locals {
  pii_types = [
    "NAME", "EMAIL", "PHONE", "ADDRESS",
    "INTERNATIONAL_BANK_ACCOUNT_NUMBER", "SWIFT_CODE",
    "CREDIT_DEBIT_CARD_NUMBER", "CREDIT_DEBIT_CARD_CVV", "CREDIT_DEBIT_CARD_EXPIRY",
    "IP_ADDRESS", "PASSWORD", "AWS_ACCESS_KEY", "AWS_SECRET_KEY",
  ]
}

resource "aws_bedrock_guardrail" "pii" {
  name                      = var.name
  description               = "Last-layer masking of personal data; the gateway pseudonymises first."
  blocked_input_messaging   = "Request refused: it contains data that must not reach the model."
  blocked_outputs_messaging = "Answer withheld: it contains data that must not leave the model."
  kms_key_arn               = var.kms_key_arn
  tags                      = var.tags

  sensitive_information_policy_config {
    dynamic "pii_entities_config" {
      for_each = local.pii_types
      content {
        type   = pii_entities_config.value
        action = var.action
      }
    }
    regexes_config {
      name        = "fr-nir-shape"
      description = "Shape of a French NIR (no check of the key)"
      pattern     = "[12][ .]?[0-9]{2}[ .]?[0-9]{2}[ .]?([0-9]{2}|2[ABab])[ .]?[0-9]{3}[ .]?[0-9]{3}[ .]?[0-9]{2}"
      action      = var.action
    }
    regexes_config {
      name        = "fr-iban-shape"
      description = "Shape of a French IBAN"
      pattern     = "FR[0-9]{2}( ?[A-Z0-9]{4}){5} ?[A-Z0-9]{3}"
      action      = var.action
    }
  }
}

resource "aws_bedrock_guardrail_version" "pii" {
  guardrail_arn = aws_bedrock_guardrail.pii.guardrail_arn
  description   = "Version used by the gateway"
}
