# IAM access to Claude on Amazon Bedrock that cannot leave the allowed jurisdiction.
# Built on the AWS-documented pattern (docs/sources/verifications.md V11): allow the inference
# profile in the source Region and the foundation model in each destination Region, filtered by
# bedrock:InferenceProfileArn; explicit Deny for global routing, other geographies, Fable/Mythos
# and any Region outside the inventory.

locals {
  routes_file  = coalesce(var.routes_file, "${path.module}/../../../inventory/routes-${replace(var.residency, "_", "-")}.json")
  inventory    = jsondecode(file(local.routes_file))
  all_routes   = local.inventory.routes
  eu_regions   = ["eu-central-1", "eu-north-1", "eu-south-1", "eu-south-2", "eu-west-1", "eu-west-3"]
  allowed_zone = var.residency == "eu" ? local.eu_regions : concat(local.eu_regions, ["eu-west-2", "eu-central-2"])

  selected = [
    for r in local.all_routes : r
    if contains(var.models, r.model) && r.mode == var.mode && r.source_region == var.source_region
  ]
  missing_models = setsubtract(var.models, [for r in local.selected : r.model])
  destinations   = distinct(flatten([for r in local.selected : r.destinations]))
  outside_zone   = setsubtract(local.destinations, local.allowed_zone)

  geo_profiles = [for r in local.selected : r.profile if r.mode == "geo"]
  profile_arns = [for p in local.geo_profiles : "arn:aws:bedrock:${var.source_region}:${var.account_id}:inference-profile/${p}"]

  geo_statements = [
    for r in local.selected : {
      Sid    = "InvokeViaEuProfile${replace(title(replace(r.model, ".", " ")), " ", "")}"
      Effect = "Allow"
      Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
      Resource = concat(
        ["arn:aws:bedrock:${var.source_region}:${var.account_id}:inference-profile/${r.profile}"],
        [for d in r.destinations : "arn:aws:bedrock:${d}::foundation-model/${trimprefix(r.profile, "eu.")}"]
      )
    } if r.mode == "geo"
  ]
  geo_guard = length(local.geo_profiles) == 0 ? [] : [{
    Sid      = "FoundationModelOnlyThroughAllowedProfiles"
    Effect   = "Deny"
    Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    Resource = ["arn:aws:bedrock:*::foundation-model/*"]
    Condition = {
      StringNotEquals = { "bedrock:InferenceProfileArn" = local.profile_arns }
    }
  }]
  mantle_statements = var.mode != "in_region_mantle" || length(local.selected) == 0 ? [] : [{
    Sid      = "InvokeInRegionMantle"
    Effect   = "Allow"
    Action   = ["bedrock-mantle:CreateInference"]
    Resource = ["*"] # resource ARN format to verify (verifications.md, open points)
    Condition = {
      StringEquals = { "aws:RequestedRegion" = var.source_region }
    }
  }]
  deny_statements = [
    {
      Sid       = "DenyGlobalRouting"
      Effect    = "Deny"
      Action    = ["bedrock:InvokeModel*", "bedrock:Converse*", "bedrock-mantle:*"]
      Resource  = ["*"]
      Condition = { StringEquals = { "aws:RequestedRegion" = "unspecified" } }
    },
    {
      Sid    = "DenyOtherGeographiesAndGlobalProfiles"
      Effect = "Deny"
      Action = ["bedrock:InvokeModel*", "bedrock:Converse*"]
      Resource = [
        for prefix in ["global", "us", "us-gov", "apac", "au", "jp", "in", "ca"] :
        "arn:aws:bedrock:*:*:inference-profile/${prefix}.*"
      ]
    },
    {
      Sid    = "DenyFableAndMythos"
      Effect = "Deny"
      Action = ["bedrock:InvokeModel*", "bedrock:Converse*", "bedrock-mantle:*"]
      Resource = [
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-fable-*",
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-mythos-*",
        "arn:aws:bedrock:*:*:inference-profile/*anthropic.claude-fable-*",
        "arn:aws:bedrock:*:*:inference-profile/*anthropic.claude-mythos-*",
      ]
    },
    {
      Sid       = "DenyRegionsOutsideInventory"
      Effect    = "Deny"
      Action    = ["bedrock:InvokeModel*", "bedrock:Converse*", "bedrock-mantle:*"]
      Resource  = ["*"]
      Condition = { StringNotEquals = { "aws:RequestedRegion" = distinct(concat([var.source_region], local.destinations)) } }
    },
  ]

  policy = {
    Version   = "2012-10-17"
    Statement = concat(local.geo_statements, local.geo_guard, local.mantle_statements, local.deny_statements)
  }
}

resource "terraform_data" "residency_guard" {
  input = local.selected
  lifecycle {
    precondition {
      condition     = contains(local.allowed_zone, var.source_region)
      error_message = "source_region ${var.source_region} is outside the ${var.residency} zone."
    }
    precondition {
      condition     = length(local.missing_models) == 0
      error_message = "No ${var.mode} route from ${var.source_region} in the inventory for: ${join(", ", local.missing_models)}."
    }
    precondition {
      condition     = length(local.outside_zone) == 0
      error_message = "Inventory destinations outside the ${var.residency} zone: ${join(", ", local.outside_zone)}."
    }
  }
}

data "aws_iam_policy_document" "trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = var.trusted_principal_arns
    }
  }
}

resource "aws_iam_role" "gateway" {
  name                 = var.name
  assume_role_policy   = data.aws_iam_policy_document.trust.json
  permissions_boundary = var.permissions_boundary_arn
  max_session_duration = 3600
  tags                 = var.tags
  depends_on           = [terraform_data.residency_guard]
}

resource "aws_iam_role_policy" "bedrock_eu" {
  name   = "bedrock-eu-only"
  role   = aws_iam_role.gateway.id
  policy = jsonencode(local.policy)
}

# Kill switch, level 3 (E2.6): the same mechanism AWS uses to revoke role sessions, an inline policy
# that denies everything, here limited to Bedrock so that the role stays inspectable.
resource "aws_iam_role_policy" "kill_switch" {
  count = var.kill_switch ? 1 : 0
  name  = "kill-switch-deny-bedrock"
  role  = aws_iam_role.gateway.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "KillSwitchDenyAllBedrock"
      Effect   = "Deny"
      Action   = ["bedrock:*", "bedrock-mantle:*"]
      Resource = ["*"]
    }]
  })
}
