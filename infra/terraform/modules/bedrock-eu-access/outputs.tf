output "role_arn" {
  description = "IAM role the gateway assumes to call Bedrock."
  value       = aws_iam_role.gateway.arn
}

output "policy_json" {
  description = "Rendered IAM policy (reviewable, and checked by the conftest policies)."
  value       = jsonencode(local.policy)
}

output "routes" {
  description = "Routes granted: model, mode, source Region, profile and destination Regions."
  value       = local.selected
}

output "allowed_regions" {
  description = "Every Region a request may be processed in."
  value       = sort(distinct(concat([var.source_region], local.destinations)))
}
