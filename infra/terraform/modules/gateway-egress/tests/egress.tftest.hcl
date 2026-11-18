# Runs offline: the AWS provider is mocked, no credentials needed (decision K3).
mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
  mock_resource "aws_security_group" {
    defaults = { id = "sg-0123456789abcdef0" }
  }
}

variables {
  vpc_id           = "vpc-0123456789abcdef0"
  subnet_ids       = ["subnet-0123456789abcdef0", "subnet-0123456789abcdef1"]
  gateway_role_arn = "arn:aws:iam::111122223333:role/claude-gateway-bedrock-eu"
}

run "paris_runtime_endpoint_only" {
  command = plan
  assert {
    condition     = keys(aws_vpc_endpoint.bedrock) == ["bedrock-runtime"]
    error_message = "Only the bedrock-runtime endpoint is created by default."
  }
  assert {
    condition     = aws_vpc_endpoint.bedrock["bedrock-runtime"].service_name == "com.amazonaws.eu-west-3.bedrock-runtime"
    error_message = "The endpoint must be in the gateway's Region."
  }
  assert {
    condition     = aws_vpc_endpoint.bedrock["bedrock-runtime"].private_dns_enabled
    error_message = "Private DNS keeps the default bedrock-runtime host name on the private path."
  }
}

run "gateway_egress_is_https_to_endpoints_only" {
  command = plan
  assert {
    condition     = aws_vpc_security_group_egress_rule.gateway_to_bedrock.from_port == 443 && aws_vpc_security_group_egress_rule.gateway_to_bedrock.to_port == 443
    error_message = "Egress must be HTTPS only."
  }
  assert {
    condition     = aws_vpc_security_group_egress_rule.gateway_to_bedrock.cidr_ipv4 == null && aws_vpc_security_group_egress_rule.gateway_to_bedrock.cidr_ipv6 == null
    error_message = "Egress must target the endpoint security group, never a CIDR."
  }
}

run "mantle_on_request" {
  command = plan
  variables {
    enable_mantle = true
  }
  assert {
    condition     = contains(keys(aws_vpc_endpoint.bedrock), "bedrock-mantle")
    error_message = "enable_mantle must add the bedrock-mantle endpoint."
  }
}

run "non_eu_region_refused" {
  command = plan
  variables {
    region = "us-east-1"
  }
  expect_failures = [aws_vpc_endpoint.bedrock]
}
