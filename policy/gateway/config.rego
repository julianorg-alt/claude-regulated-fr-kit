# Settings of the request policy. Edit for your organisation; the tests in gateway_test.rego
# override them, so they keep passing whatever you choose here.
package crfr.gateway

import rego.v1

config := {
	"models_by_group": {
		"claude-users": ["claude-haiku-4-5", "claude-sonnet-5"],
		# The exit-* aliases reach the second provider (E10.1): reserved to the group that runs exit drills.
		"claude-power-users": ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5-5", "exit-claude-haiku-4-5", "exit-claude-sonnet-5"],
	},
	"max_request_bytes": 1048576,
	"max_output_tokens": 8192,
}
