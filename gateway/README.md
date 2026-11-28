# Gateway

Envoy AI Gateway v1.2.1 (Apache-2.0) in standalone mode (`aigw run`), in front of Amazon Bedrock. Clients send Anthropic Messages requests to `POST /anthropic/v1/messages` with a short model alias; the gateway checks the caller's token, maps the alias to the `eu.` inference profile and signs the request with SigV4 for the source Region.

```bash
make up    # gateway on 127.0.0.1:1975, Keycloak on 127.0.0.1:8081 (override: CRFR_GATEWAY_PORT, CRFR_KEYCLOAK_PORT); guard, OPA and fake Bedrock inside the network
make e2e   # end-to-end tests (gateway/tests/test_e2e*.py)
make down
```

Behind a TLS-inspecting proxy, build the two local images first with the proxy's CA bundle passed as the `build_ca` build secret (from the repository root: `docker buildx build --secret id=build_ca,src=ca.crt -f gateway/guard/Dockerfile -t gateway-guard -t gateway-audit-shipper .` and `docker buildx build --secret id=build_ca,src=ca.crt -t gateway-fake-bedrock gateway/fake-bedrock`; the guard image needs the repository root as build context), then run `make up UP_FLAGS=`. The image names are the ones Compose expects for the default project directory name `gateway`; check with `docker compose -f gateway/compose.yaml config --images` if you renamed it.

## Request path

```
client ──> Envoy listener "edge" :1975 ──> Envoy listener "ai" :1976 ──> Bedrock (eu. profile, SigV4)
             jwt_authn                        jwt_authn
             guard (ext_proc) ──> OPA         AI Gateway (model routing, translation)
             rbac (group claude-users)        rbac
```

The guard (`guard/`) is a gRPC external processor. It sees every request body before Envoy AI Gateway does and every response on its way back. Two listeners are needed because Envoy AI Gateway inserts its own external processor first in the filter chain of its listener and translates the request from the body it read there: a filter placed after it on the same listener can refuse a call but cannot change what reaches Bedrock. The pseudonymisation stage (backlog E3.5) rewrites bodies, so it runs on the edge listener.

## What is enforced

| Control | How | Test |
|---|---|---|
| Only models with an EU route are reachable | `config/aigw.yaml` is generated from `infra/inventory/routes-eu.json` by `tools/crfr/gateway_config.py`; any other model name gets 404 | `test_models_outside_inventory_are_not_routable` |
| Caller authenticated | JWT from the corporate identity provider (Keycloak locally), issuer and audience `claude-gateway` checked; expired or tampered tokens get 401 | `test_rejects_missing_token`, `test_rejects_tampered_token` |
| Caller authorised | `groups` claim must contain `claude-users`, otherwise 403 | `test_rejects_user_outside_group` |
| Requests signed for the EU source Region, `eu.` profile only | `BackendSecurityPolicy` (SigV4, `eu-west-3`); the fake Bedrock refuses anything else, as the Terraform IAM policy does in a real account | `test_allowed_model_is_signed_for_paris_and_uses_eu_profile` |
| No client identity or address sent to Bedrock | no `claimToHeaders`; `ClientTrafficPolicy` stops Envoy from deriving and forwarding the client address (`x-envoy-external-address`, `x-forwarded-for`); `headerMutation` removes location headers | same test, which also fails on any new `x-*` header |
| Daily token quota per user, team and application (E2.4) | guard ledger (SQLite), limits in `config/guard.json`; usage read from the response, charged when it completes | `test_user_quota_exceeded_is_refused_and_traced`, `test_usage_is_charged_to_user_team_and_app` |
| Monthly budget per user, team and application, blocking (E2.4) | cost = tokens × per-million price of the model, in `config/guard.json`; 429 once spent ≥ budget | `test_monthly_budget_exceeded_is_refused_and_traced` |
| Models allowed per group, size limits, no identifier in clear text (E2.5) | OPA policy `policy/gateway/gateway.rego`; OPA down means 503 (fail closed) | `test_model_allowed_by_group`, `test_clear_identifier_never_reaches_bedrock`, `test_size_limits`, `test_policy_engine_down_fails_closed` |
| Kill switch, three levels (E2.6) | 1: `crfr_guard.admin revoke app\|user\|team KEY` (403); 2: `crfr_guard.admin stop` (503 on every call); 3: Terraform `kill_switch = true` on `bedrock-eu-access`, an explicit IAM deny (simulated locally by the fake Bedrock) | `KillSwitch` tests, timed; `kill_switch_*` Terraform tests |
| Egress to EU Bedrock endpoints only, no admin interface exposed (E2.7) | generated `Backend` objects are EU Bedrock hosts, the guard and the gateway itself, all TLS-verified; internal Docker network for guard, OPA and fake Bedrock; Keycloak admin console and admin API disabled; in AWS, `infra/terraform/modules/gateway-egress` | `test_egress_allowlist`, `Egress` tests, `gateway-egress` Terraform tests |
| Prompt caching through the gateway (E2.8) | `cache_control` blocks are forwarded unchanged; cache usage fields come back to the client and are priced separately | `test_cache_control_passes_through_and_usage_comes_back` |
| Personal data replaced by pseudonyms before Bedrock, restored in the answer (E3.5) | guard calls `pseudonymisation/crfr_pseudo` on the edge listener: request body rewritten, buffered and streamed answers re-identified; the vault is encrypted and expires | `gateway/tests/test_e2e_pseudo.py` (canaries: absent from Bedrock, container logs, content log, audit store and ledger) |
| Audit trail in three flows (E5.1) | one line per decision, without content, with `prompt_hmac` (HMAC of the SHA-256 of the request body) and a MAC chain (`prev`, `mac`); optional content log holding only what Bedrock saw (pseudonymised), refused by the configuration unless pseudonymisation is on, purged after 1 to 30 days; pseudonym mappings only in the vault | `tests/test_audit.py`, `test_content_log_keeps_only_what_bedrock_saw`, `test_e2e_audit.py` |
| Audit lines stored where nobody can delete them (E5.2) | the guard writes time segments; `audit-shipper` (same image, other process and credentials) copies closed segments to S3-compatible storage under Object Lock in compliance mode, checks MD5 and retention, then deletes the local copy; locally RustFS (decision K14), in AWS `infra/terraform/modules/gateway-audit-store` | `test_stored_segment_cannot_be_deleted`, `gateway-audit-store` Terraform tests |
| GenAI telemetry without content (E5.3) | one OpenTelemetry span per call (`chat`, `gen_ai.provider.name = aws.bedrock`, model, token usage, decision), OTLP/HTTP to a collector; the guard has no content-capture option and the collector deletes the GenAI content attributes anyway | `tests/test_telemetry.py`, `test_siem_receives_a_genai_span_without_content` |
| Provider credentials never in the repository | `${AWS_ACCESS_KEY_ID}` placeholders, injected at start-up; in production, a role from `infra/terraform/modules/bedrock-eu-access` | `test_no_credentials_in_rendered_config` |

## Findings while building it

- Envoy AI Gateway forwards its own routing headers to the provider: `x-ai-eg-model`, `x-ai-eg-original-path`, `x-ai-eg-internal-req-id`. They carry no personal data, and removing them breaks routing. The end-to-end test lists them explicitly, so any new header fails the build.
- By default Envoy sends the client IP to the provider in `x-envoy-external-address` and `x-forwarded-for`. Under the GDPR, an IP address is personal data. `headerMutation` on the backend does not remove `x-envoy-external-address`, because Envoy adds it after the AI Gateway filter. The kit's `ClientTrafficPolicy` stops it.
- An `EnvoyExtensionPolicy` with an inline Lua filter made every route answer 500 (`direct_response`) in standalone mode, without an error in the logs. The kit does not use Lua.
- The upstream project moved from `envoyproxy/ai-gateway` to `theagentrouter/agent-router` on GitHub; the container image is still `docker.io/envoyproxy/ai-gateway-cli`, pinned here by digest. The release ships no checksum for the `aigw` binary, which is one more reason to use the image by digest.

- The token quotas built into Envoy AI Gateway (usage-based rate limiting and `QuotaPolicy`) both need Redis and a separate rate-limit service, and `QuotaPolicy` fails open by default when that service is unreachable. Its time windows stop at one day, so a monthly budget is out of reach. The guard keeps quotas and budgets in one ledger next to the decision log, fails closed, and covers the month.
- In OPA, `deny contains "x" if not is_array(input.field)` does not fire when the field is absent: the request passes. The gateway policy only negates positive helper rules (`not pii_checked`), and a test sends inputs with the fields removed.
- Usage is charged after the response, as Envoy AI Gateway does for its own limits: the call that crosses a limit completes, the next one is refused. The same holds for streamed answers.
- Prompt caching: the gateway forwards `cache_control` untouched and returns the `cache_read_input_tokens` and `cache_creation_input_tokens` fields to the client. The fake Bedrock uses the Anthropic field names. Anthropic's documentation sends Bedrock users to the Bedrock guide for the usage-field names on Bedrock; that guide does not show them for InvokeModel, so the names on a real account remain to be checked (verifications.md, open points).

- MinIO no longer publishes container images (Docker Hub answers "repository does not exist", quay.io 401). The local store is RustFS; the shipper speaks plain S3 (SigV4 checked against the AWS example), so any S3 service with Object Lock works.
- Recreating the guard container alone left the gateway answering 500 on every call until the stack was restarted: the gateway fails closed when it loses the guard, as designed, but does not always reconnect on its own. Restart `aigw` after replacing the guard.

## Exit route (E10)

The generator can add a second provider reached through an OpenAI-compatible API (`--exit-provider`, from `infra/inventory/exit-providers.json`; `--exit-model alias=model`; the key comes from `EXIT_PROVIDER_API_KEY`). Envoy AI Gateway translates the Anthropic Messages request, so clients change nothing (finding V65).

- `--exit-mode standby` (the local stack): `exit-<alias>` aliases reach the second provider, reserved to `claude-power-users` by the OPA configuration. Used for drills and for replaying the evaluation suite.
- `--exit-mode switch`: the production aliases themselves go to the second provider. `make exit-drill` runs it on the local stack (`gateway/config/aigw-switch.yaml`), checks that Bedrock receives nothing, then restores the standby configuration.
- There is no automatic failover to another provider: that would change the sub-processor without a decision. Failover between two Regions of the same provider stays available (`--fallback-region`).
- The same guard applies on this path: pseudonymisation, policy, quotas and budgets (prices of `exit-*` aliases in `guard.json`), audit lines. The exit provider's host must be in the inventory.
- Local stack: `fake-bedrock` also plays the second provider at `/v1/chat/completions`, with its own request log (`/data/exit-requests.jsonl`) so that the "every Bedrock request is EU" check stays meaningful.
- Streamed usage is only counted when the provider sends it in a final chunk without choices (what OpenAI sends with `include_usage`); the e2e test `test_streamed_exit_answers_are_counted_against_quotas_and_budgets` guards that.

The exit plan itself is `docs/compliance/plan-de-sortie.md`.

## Operating the guard

```bash
docker compose -f gateway/compose.yaml exec guard python -s -E -m crfr_guard.admin stop --reason "incident"
docker compose -f gateway/compose.yaml exec guard python -s -E -m crfr_guard.admin resume
docker compose -f gateway/compose.yaml exec guard python -s -E -m crfr_guard.admin revoke app demo-app --reason "leaked secret"
docker compose -f gateway/compose.yaml exec guard python -s -E -m crfr_guard.admin usage team team-risk
```

The admin command writes to the guard's SQLite file; the guard reads it on every request, so a switch applies to the next call. In the local drill each level takes well under a second (the end-to-end run prints the timings). In AWS, level 3 depends on IAM propagation, which AWS describes as eventually consistent without a figure: levels 1 and 2 are the ones that meet the five-minute objective, level 3 is the backstop when the gateway itself is not trusted.

Prices in `config/guard.json` are placeholders (one unit per million tokens). Copy each model's prices from your AWS price list before relying on budgets.

### Audit trail

Each audit line records who called which model, the decision, the reason, the token counts and `prompt_hmac`, never the prompt or the answer. The guard prints each line on its standard output (for the SIEM) and appends it to `/data/audit/audit-<start>.jsonl`, one file per `audit.segment_s` seconds (5 in the demo, 300 by default). Commands, with `CRFR_AUDIT_KEY` set:

```bash
python -s -E -m crfr_guard.admin verify-audit audit-*.jsonl              # MAC chain, in time order
python -s -E -m crfr_guard.admin verify-audit --prev <mac> audit-*.jsonl # segments following an earlier batch
python -s -E -m crfr_guard.admin fingerprint request.json                # prompt_hmac of a body, to find its line
```

The chain detects an edited, inserted, removed or reordered line, and a line written with another key. It does not detect lines cut from the end of the last segment; the head of the chain kept in `/data/audit/.head` and the copies under Object Lock cover that case. With a KMS HMAC key (`KmsMac`), each line costs two `GenerateMac` calls: size the KMS request quota accordingly. The demo key in `compose.yaml` is public: never reuse it.

The content log is off by default. The demo turns it on (7 days) to show what it holds: the request after pseudonymisation and the answer before re-identification. Retention of audit lines follows CNIL recommendation 2021-122: 6 months to 1 year, up to 3 years with a documented justification (`audit_retention_days`, 180 to 1 095). The local bucket keeps objects for one day only, so that a demo leaves nothing locked for months.

## Local stack only

The fake Bedrock (`fake-bedrock/`) is a test double: it checks the SigV4 credential scope and the profile, then answers from a cassette of recorded responses or with a deterministic echo. It logs every request it receives, which is how the tests prove what would have reached AWS. Keycloak runs in development mode with demo users (`alice`, in `claude-users`, `claude-power-users` and `team-risk`; `carol`, in `claude-users` and `team-claims`, with a 30-token daily quota; `mallory`, in no group), two demo clients (`demo-app`, and `budget-demo` with a tiny monthly budget) and fixed demo passwords: never reuse this realm outside a laptop.
