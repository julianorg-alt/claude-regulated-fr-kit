output "guardrail_id" {
  description = "Send as X-Amzn-Bedrock-GuardrailIdentifier on InvokeModel (bedrock-runtime only; bedrock-mantle has no guardrails)."
  value       = aws_bedrock_guardrail.pii.guardrail_id
}

output "guardrail_version" {
  description = "Send as X-Amzn-Bedrock-GuardrailVersion."
  value       = aws_bedrock_guardrail_version.pii.version
}
