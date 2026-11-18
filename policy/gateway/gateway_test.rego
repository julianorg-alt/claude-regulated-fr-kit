package crfr.gateway

import rego.v1

fixture_config := {
	"models_by_group": {"claude-users": ["claude-sonnet-5"], "claude-power-users": ["claude-opus-5-5"]},
	"max_request_bytes": 1000,
	"max_output_tokens": 100,
}

base := {
	"user": "alice", "app": "demo-app", "team": "team-risk", "groups": ["claude-users"],
	"model": "claude-sonnet-5", "request_bytes": 200, "max_tokens": 64, "stream": false,
	"pii": {"residual": []},
}

decide(overrides) := result if {
	result := decision with input as object.union(base, overrides) with config as fixture_config
}

test_allows_clean_request if {
	decide({}) == {"allow": true, "reasons": []}
}

test_model_must_be_allowed_for_a_group if {
	decide({"model": "claude-opus-5-5"}).reasons == ["model-not-allowed-for-groups"]
	decide({"model": "claude-opus-5-5", "groups": ["claude-users", "claude-power-users"]}).allow
	decide({"groups": []}).reasons == ["model-not-allowed-for-groups"]
	decide({"model": null}).reasons == ["model-not-allowed-for-groups"]
}

test_size_limits if {
	decide({"request_bytes": 1001}).reasons == ["request-too-large"]
	decide({"max_tokens": 101}).reasons == ["max-tokens-too-high"]
	decide({"max_tokens": null}).reasons == ["max-tokens-missing"]
	decide({"max_tokens": "64"}).reasons == ["max-tokens-missing"]
}

test_refuses_clear_identifiers if {
	decide({"pii": {"residual": ["NIR"]}}).reasons == ["not-pseudonymised"]
	without_pii := object.remove(base, {"pii"})
	result := decision with input as without_pii with config as fixture_config
	result.reasons == ["pii-check-missing"]
}

test_absent_fields_are_refusals if {
	no_max := object.remove(base, {"max_tokens"})
	r := decision with input as no_max with config as fixture_config
	r.reasons == ["max-tokens-missing"]
	r2 := decision with input as {} with config as fixture_config
	not r2.allow
}

test_identity_required if {
	decide({"user": ""}).reasons == ["missing-identity"]
	decide({"app": null}).reasons == ["missing-identity"]
}

test_all_reasons_reported_sorted if {
	decide({"model": "x", "max_tokens": 1000, "pii": {"residual": ["IBAN_FR"]}}).reasons == [
		"max-tokens-too-high", "model-not-allowed-for-groups", "not-pseudonymised",
	]
}
