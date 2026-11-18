# Request policy of the gateway (backlog E2.5), evaluated by OPA for every call before it reaches
# Bedrock. The guard (gateway/guard) sends the input below and refuses the call with 403 and the
# reasons when "allow" is false. Any OPA error is a refusal (fail closed).
#
# input: {user, app, team, groups[], model, request_bytes, max_tokens, stream, pii: {residual[]}}
package crfr.gateway

import rego.v1

default decision := {"allow": false, "reasons": ["no-decision"]}

decision := {"allow": count(deny) == 0, "reasons": sort_reasons(deny)}

sort_reasons(set) := sort([r | some r in set])

deny contains "missing-identity" if not valid_identity

valid_identity if {
	is_string(input.user)
	input.user != ""
	is_string(input.app)
	input.app != ""
}

deny contains "model-not-allowed-for-groups" if not model_allowed

model_allowed if {
	some group in input.groups
	input.model in config.models_by_group[group]
}

deny contains "request-too-large" if input.request_bytes > config.max_request_bytes

# "not f(x)" is not used on input fields: when the field is absent, OPA would leave the rule
# undefined and the request would pass. Positive helper rules make an absent field a refusal.
deny contains "max-tokens-missing" if not max_tokens_given

max_tokens_given if is_number(input.max_tokens)

deny contains "max-tokens-too-high" if {
	is_number(input.max_tokens)
	input.max_tokens > config.max_output_tokens
}

# An identifier with a valid check digit (NIR, IBAN, card) is still in clear text: the
# pseudonymisation stage did not run or missed it. Nothing of it may reach the model.
deny contains "not-pseudonymised" if count(input.pii.residual) > 0

deny contains "pii-check-missing" if not pii_checked

pii_checked if is_array(input.pii.residual)
