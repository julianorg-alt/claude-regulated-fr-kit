output "gateway_security_group_id" {
  description = "Attach this security group to the gateway: its only egress is HTTPS to the Bedrock endpoints."
  value       = aws_security_group.gateway.id
}

output "endpoint_ids" {
  description = "Interface endpoints, by service."
  value       = { for k, v in aws_vpc_endpoint.bedrock : k => v.id }
}
