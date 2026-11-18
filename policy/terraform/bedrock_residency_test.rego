package main

import rego.v1

plan(statements) := {"resource_changes": [{
	"type": "aws_iam_role_policy",
	"change": {"after": {"policy": json.marshal({"Version": "2012-10-17", "Statement": statements})}},
}]}

guards := [
	{"Effect": "Deny", "Action": ["bedrock:InvokeModel*"], "Resource": ["*"], "Condition": {"StringEquals": {"aws:RequestedRegion": "unspecified"}}},
	{"Effect": "Deny", "Action": ["bedrock:InvokeModel*"], "Resource": ["*"], "Condition": {"StringNotEquals": {"aws:RequestedRegion": ["eu-west-3", "eu-west-1"]}}},
]

allow(resource) := {"Effect": "Allow", "Action": ["bedrock:InvokeModel"], "Resource": [resource]}

test_eu_profile_passes if {
	count(deny) == 0 with input as plan(array.concat([allow("arn:aws:bedrock:eu-west-3:111122223333:inference-profile/eu.anthropic.claude-sonnet-5")], guards))
}

test_us_region_denied if {
	count(deny) > 0 with input as plan(array.concat([allow("arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-5")], guards))
}

test_global_profile_denied if {
	count(deny) > 0 with input as plan(array.concat([allow("arn:aws:bedrock:eu-west-3:111122223333:inference-profile/global.anthropic.claude-sonnet-5")], guards))
}

test_fable_denied if {
	count(deny) > 0 with input as plan(array.concat([allow("arn:aws:bedrock:eu-west-3::foundation-model/anthropic.claude-fable-5-2")], guards))
}

test_missing_global_guard if {
	"Missing Deny on global routing (aws:RequestedRegion = unspecified)" in deny with input as plan([allow("arn:aws:bedrock:eu-west-3:111122223333:inference-profile/eu.anthropic.claude-sonnet-5"), guards[1]])
}

test_region_fence_with_london_fails if {
	fence := {"Effect": "Deny", "Action": ["bedrock:InvokeModel*"], "Resource": ["*"], "Condition": {"StringNotEquals": {"aws:RequestedRegion": ["eu-west-3", "eu-west-2"]}}}
	"Missing Deny on Regions outside the inventory" in deny with input as plan([allow("arn:aws:bedrock:eu-west-3:111122223333:inference-profile/eu.x"), guards[0], fence])
}
