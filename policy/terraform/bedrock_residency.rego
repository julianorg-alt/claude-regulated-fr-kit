# Checks a Terraform plan (terraform show -json) of the kit: every IAM policy that touches
# Bedrock must keep inference inside the EU (backlog E1, docs/sources/verifications.md).
package main

import rego.v1

eu_regions := {"eu-central-1", "eu-north-1", "eu-south-1", "eu-south-2", "eu-west-1", "eu-west-3"}

bedrock_policies contains doc if {
	some rc in input.resource_changes
	rc.type == "aws_iam_role_policy"
	doc := json.unmarshal(rc.change.after.policy)
	some st in doc.Statement
	some action in as_array(st.Action)
	startswith(action, "bedrock")
}

as_array(x) := x if is_array(x)

as_array(x) := [x] if not is_array(x)

statements contains st if {
	some doc in bedrock_policies
	some st in doc.Statement
}

region_of(arn) := split(arn, ":")[3]

deny contains msg if {
	some st in statements
	st.Effect == "Allow"
	some res in as_array(st.Resource)
	startswith(res, "arn:aws:bedrock:")
	not region_of(res) in eu_regions
	msg := sprintf("Allow on a Bedrock resource outside the EU: %s", [res])
}

deny contains msg if {
	some st in statements
	st.Effect == "Allow"
	some res in as_array(st.Resource)
	regex.match(`inference-profile/(global|us|us-gov|apac|au|jp|in|ca)\.`, res)
	msg := sprintf("Allow on a non-EU inference profile: %s", [res])
}

deny contains msg if {
	some st in statements
	st.Effect == "Allow"
	some res in as_array(st.Resource)
	regex.match(`(?i)claude-(fable|mythos)`, res)
	msg := sprintf("Allow on Fable or Mythos (no EU profile, 30-day retention): %s", [res])
}

deny contains "Missing Deny on global routing (aws:RequestedRegion = unspecified)" if {
	count(bedrock_policies) > 0
	not global_denied
}

global_denied if {
	some st in statements
	st.Effect == "Deny"
	st.Condition.StringEquals["aws:RequestedRegion"] == "unspecified"
}

deny contains "Missing Deny on Regions outside the inventory" if {
	count(bedrock_policies) > 0
	not region_fence
}

region_fence if {
	some st in statements
	st.Effect == "Deny"
	regions := as_array(st.Condition.StringNotEquals["aws:RequestedRegion"])
	count(regions) > 0
	every r in regions {
		r in eu_regions
	}
}
