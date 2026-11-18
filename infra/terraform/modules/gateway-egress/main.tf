# Network egress of the gateway (backlog E2.7, and the optional VPC endpoint of E1.5).
#
# The gateway's security group may only open HTTPS connections to the Bedrock interface endpoints
# of its own Region, nothing else: no Internet, no other AWS endpoint. Amazon DNS is not filtered by
# security groups (verifications.md V22), so name resolution keeps working. The endpoint policy only
# lets the gateway role call inference, on eu. inference profiles.
#
# Availability of the endpoint services in a given Region is not listed by the Bedrock guide
# (verifications.md, open points): the plan fails on a Region without them, which is the check.

locals {
  eu_regions = ["eu-central-1", "eu-north-1", "eu-south-1", "eu-south-2", "eu-west-1", "eu-west-3"]
  services   = concat(["bedrock-runtime"], var.enable_mantle ? ["bedrock-mantle"] : [])
}

data "aws_iam_policy_document" "endpoint" {
  statement {
    sid    = "GatewayInferenceOnEuProfiles"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = [var.gateway_role_arn]
    }
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
      "bedrock-mantle:CreateInference",
    ]
    resources = ["*"] # the role policy (bedrock-eu-access) narrows to eu. profiles and their destinations
  }
  statement {
    sid    = "DenyNonEuProfiles"
    effect = "Deny"
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    actions = ["bedrock:InvokeModel*"]
    resources = [
      "arn:aws:bedrock:*:*:inference-profile/global.*",
      "arn:aws:bedrock:*:*:inference-profile/us.*",
      "arn:aws:bedrock:*:*:inference-profile/apac.*",
    ]
  }
}

resource "aws_security_group" "gateway" {
  name        = "${var.name}-gateway"
  description = "Claude gateway: HTTPS egress to the Bedrock endpoints only"
  vpc_id      = var.vpc_id
  tags        = var.tags
}

resource "aws_security_group" "endpoints" {
  name        = "${var.name}-bedrock-endpoints"
  description = "Bedrock interface endpoints: HTTPS from the Claude gateway only"
  vpc_id      = var.vpc_id
  tags        = var.tags
}

resource "aws_vpc_security_group_egress_rule" "gateway_to_bedrock" {
  security_group_id            = aws_security_group.gateway.id
  referenced_security_group_id = aws_security_group.endpoints.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "HTTPS to the Bedrock interface endpoints"
}

resource "aws_vpc_security_group_ingress_rule" "bedrock_from_gateway" {
  security_group_id            = aws_security_group.endpoints.id
  referenced_security_group_id = aws_security_group.gateway.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "HTTPS from the Claude gateway"
}

resource "aws_vpc_endpoint" "bedrock" {
  for_each            = toset(local.services)
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.subnet_ids
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true
  policy              = data.aws_iam_policy_document.endpoint.json
  tags                = merge(var.tags, { Name = "${var.name}-${each.key}" })
  lifecycle {
    precondition {
      condition     = contains(local.eu_regions, var.region)
      error_message = "region ${var.region} is not an EU member-state Region."
    }
  }
}
