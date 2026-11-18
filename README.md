# claude-regulated-fr

Reference kit for deploying Claude in French regulated organisations: banks, insurers, healthcare providers and public bodies.

The kit does not ship a chat interface. It ships the layer that hyperscaler landing zones and risk catalogues leave out: proof of where requests are processed, an LLM gateway, pseudonymisation of French personal data, governance of agents and MCP servers, evaluation in French, and a compliance file that ties every control to a legal text and to an automated test.

Status: work in progress, version 0.8.0. Sprint 1 (Bedrock residency, gateway with authentication) is done; sprint 2 (quotas, budgets, request policy, kill switch, egress control, pseudonymisation of French personal data and its benchmark) is done; sprint 3 has added the audit trail, the evaluation in French and the traceability matrix, the compliance templates and a gap grid between the Anthropic DPA and DORA article 30.

## Problem

As of November 2026, EU processing of Claude is available through Amazon Bedrock's `eu.` inference profiles and through Google Cloud's `eu` endpoint. It is easy to lose by configuration:

- `global.` profiles route to every commercial AWS Region;
- the `eu.` profile called from London or Zurich adds London or Zurich to its destinations;
- Claude Fable and Mythos have no EU profile on Bedrock, and Fable traffic is retained for up to 30 days for abuse detection;
- AWS itself asks customers not to rely on the `eu.` prefix and to check every destination Region.

The kit turns these facts into checks that fail loudly. Sources and dates: [docs/sources/verifications.md](docs/sources/verifications.md) (in French).

## Architecture

```
application ──> Envoy gateway ──> Amazon Bedrock (eu. profile, EU source Region)
                 │ JWT and group check
                 │ guard: quotas, budgets, kill switch, OPA policy, pseudonymisation
                 └ audit lines (HMAC chain) ──> Object Lock storage
agent ──> MCP proxy (pinned registry, approval gate, destination allowlist) ──> MCP servers
```

The full diagram, with the vault, the exit route and the telemetry, is in [docs/architecture.md](docs/architecture.md).

## Quick start

Linux x86_64 with Docker, `uv` and `make`. No AWS account and no API key: Bedrock is replaced by a fake that enforces the same IAM rules.

```bash
make demo
```

The command starts the local stack (gateway, guard, OPA, Keycloak, fake Bedrock, audit store), then sends a prompt containing a social security number and an IBAN. It prints what the client sent, what Bedrock received (typed placeholders only) and what the client got back (originals restored). The three texts are printed in full. `make up` rebuilds the images by default (`UP_FLAGS=--build`); pass `UP_FLAGS=` to start already built images without rebuilding, for example when the images come from an earlier build or when Docker cannot reach the package registries during a build. Stop the stack with `make down`. A recorded run is in [docs/demo/demo.cast](docs/demo/demo.cast).

### Troubleshooting: a host port is already in use

`make up` first runs `scripts/portcheck.py`, which lists the host ports the kit publishes and the administration ports the end-to-end test probes, and refuses to start when one of them is already taken. The message names the port, the service that needs it and how to move on. The kit publishes two ports on `127.0.0.1`:

| Port | Service | Override |
|---|---|---|
| 1975 | gateway (Envoy AI Gateway) | `CRFR_GATEWAY_PORT=<free port> make up` |
| 8081 | Keycloak (token endpoint) | `CRFR_KEYCLOAK_PORT=<free port> make up` |

Export the same variable before `make e2e`, `make demo` or `make redteam` so that the clients use the new port. The gateway and Keycloak URLs can also be set in full with `CRFR_GATEWAY` and `CRFR_KEYCLOAK`. The scheduled garak configuration (`agents/scheduled/garak-rest.json`) still points at 1975.

The ports 1976, 19000, 9002 and 8181 are never published. The end-to-end test checks that the kit does not publish them (from `docker compose ps`, not from a bare connection attempt), so a process of your own that listens on one of them does not fail the test. The preflight does not check these ports either: it only checks the ports the kit publishes (1975 and 8081 by default), so an unrelated service on 127.0.0.1:8181 no longer blocks `make up`. If the kit ever published one of them, the end-to-end test would fail. To skip the preflight: `CRFR_SKIP_PREFLIGHT=1 make up`.

## Measured results

Every figure below is committed and checked by a test, so the README cannot drift from the results.

| Area | Result | Where |
|---|---|---|
| Pseudonymisation of French personal data | On 100 held-out documents in four sectors, recall 1.0 on identifiers with a check digit (NIR, IBAN, card, SIREN, SIRET), telephone numbers, e-mail addresses, dates of birth and addresses; person names 0.99; organisations recall 0.91 at precision 0.39. No hard negative (wrong check digit) is detected. The detectors were tuned on templates of the same generator, so these figures are an upper bound for other text. | [datasets/pii-fr/results/v1-test-spacy.md](datasets/pii-fr/results/v1-test-spacy.md) |
| Evaluation in French | 80 tasks in four sectors, 24 of them critical, graded by code first, then by a judge that may answer "unknown". CI replays hand-written cassette answers to test the harness; `make eval-live` measures a real model with pass^k. The fifth and last live run (Sonnet 5.5 answering, Opus 5.5 judging, K = 3) scored 0.9957 on decided tasks, pass^3 0.95, critical tasks 1.00, and passed the gate for the first time. A separate hold-out set of 20 tasks, never used to tune the prompt, scored 0.9667 (critical 0.90) and stays closed on one critical task. | [evals/README.md](evals/README.md), [live results](docs/evals/live-results-2026-11-17.md) |
| Red team of the gateway | 13 of 13 OWASP LLM attacks in French stopped, in CI against the running stack. | [evals/redteam/gateway.yaml](evals/redteam/gateway.yaml) |
| Indirect prompt injection | Attack success rate of 33 % with the kit's controls (4 of 12 scenarios), against 100 % without, assuming a fully compromised model. It was 42 % in version 0.7.0. The scenarios that still succeed are listed. | [agents/results/asr.md](agents/results/asr.md) |

## What is in the repository

| Path | What it does |
|---|---|
| `tools/crfr/bedrock_inventory.py` | Parses the public Bedrock model cards into an inventory of source and destination Regions per Claude model and endpoint; lists the routes that stay in the EU; compares the inventory with `aws bedrock get-inference-profile` answers from a real account. |
| `infra/inventory/` | The committed inventory (21 Claude models) and the allowed routes: 88 in strict EU mode, 10 of them single-Region (Ireland or Stockholm, through `bedrock-mantle`). A weekly CI job fails if AWS changes them. |
| `infra/terraform/modules/bedrock-eu-access` | IAM role for the gateway: allows only the `eu.` profile from an EU source Region and the foundation model in each listed destination, following the AWS-documented pattern; denies global routing, other geographies, Fable and Mythos, and every Region outside the inventory. Plan-time preconditions refuse London and Zurich sources (unless `residency = "eu_plus_adequacy"`) and models without a route. |
| `infra/terraform/modules/bedrock-eu-scp` | The same rules as an organisation Service Control Policy. |
| `infra/terraform/modules/audit-trail` | Multi-Region CloudTrail with log file validation, S3 Object Lock in compliance mode and a rotated KMS key; retention bounded to 6 months to 3 years (CNIL recommendation 2021-122). |
| `policy/terraform` | Conftest (Rego) policies run on the Terraform plan, with their own unit tests. |
| `gateway/` | Envoy AI Gateway (standalone) with JWT authentication and group authorisation (Keycloak locally), configuration generated from the inventory so that only EU-routable models exist, SigV4 signing for the EU source Region, and no client identity or IP address forwarded to Bedrock. A fake Bedrock enforces the IAM rules locally. See [gateway/README.md](gateway/README.md). |
| `gateway/guard` | Policy sidecar of the gateway (Envoy external processor): daily token quotas and monthly budgets per user, team and application, three-level kill switch, decision log without prompts, OPA decisions; fails closed. |
| `policy/gateway` | OPA policy of every call: models allowed per group, size limits, refusal of identifiers still in clear text (NIR, IBAN, card numbers with a valid check digit). |
| `pseudonymisation/` | Detection of French personal data (NIR, IBAN, card, SIREN and SIRET numbers checked by their keys, names, contact data) with Presidio and spaCy, typed pseudonyms kept in an encrypted vault, re-identification of responses and streams. The guard applies it before Bedrock sees the request. See [pseudonymisation/README.md](pseudonymisation/README.md). |
| `datasets/pii-fr` | Synthetic French documents with annotated personal data (CC BY 4.0) and the measured quality of the detectors. See [datasets/README.md](datasets/README.md). |
| `infra/terraform/modules/bedrock-guardrail` | Optional Bedrock guardrail that anonymises the sensitive information types it supports, as a second line behind the gateway. |
| `infra/terraform/modules/gateway-egress` | Security groups and Bedrock interface endpoints: the gateway's only egress is HTTPS to Bedrock in its Region. |
| `gateway/guard` (audit) | Audit lines without content, with an HMAC fingerprint of each request and a MAC chain; shipped to Object Lock storage (RustFS locally) by a separate process; optional pseudonymised content log with short retention; OpenTelemetry GenAI spans without content. |
| `infra/terraform/modules/gateway-audit-store` | Audit bucket under Object Lock in compliance mode (6 months to 3 years, CNIL recommendation 2021-122), content bucket that expires after days, HMAC KMS key, and the IAM policies of the two writers, which cannot delete. |
| `evals/` | Evaluation in French with promptfoo: 80 fictional tasks in four sectors, code graders first, then an LLM judge that may answer "unknown", then a human; negative control, judge calibration (Cohen's kappa), pass^k, model-migration check. CI replays hand-written reference answers; `make eval-live` measures a real model. See [evals/README.md](evals/README.md). |
| `compliance/`, `docs/compliance/matrix.md` | Controls and legal texts in TOML; `tools/crfr/traceability.py` checks in CI that every control cites a text and an existing automated test, that no text is unused, and that the generated matrix is current. Texts not yet read on their primary source are marked "à vérifier". `docs/compliance/modeles/` holds templates in French, prefilled with the kit's controls: DPIA (GDPR article 35), FRIA (AI Act article 27), DORA register entries and transfer impact assessment (EDPB recommendations 01/2020); the checker also verifies their required sections. `docs/compliance/fiches/` holds sector sheets (banking and insurance, health, public sector), with the article 50 notice and the GDPR and AI Act role matrix next to them. |
| `agents/` | MCP proxy that admits only registered servers and tools pinned by the SHA-256 of their descriptions, checks the token audience (RFC 8707) without passing the agent's token on, mints a short-lived credential per agent and server, and logs arguments and results in a chained log; Rule of Two sheet per agentic workflow; no irreversible action without a human approval bound to the exact call; destination allowlist. Red team: 13 OWASP LLM attacks in French against the gateway in CI, an indirect injection bench whose attack success rate is published per version, weekly garak and PyRIT runs. See [agents/README.md](agents/README.md). |
| `tools/crfr/supply_chain.py` | Fails on any GitHub Action not pinned to a commit SHA, any image without a digest, any unpinned Python requirement or npm dependency. |

## Run it

Linux x86_64, `uv` and `make`. No AWS account and no API key: the AWS provider is mocked in tests, and the example is planned with fake credentials.

```bash
make tools   # pinned, checksum-verified terraform, conftest, gitleaks, kind, kubectl, helm
make ci      # lint, unit tests, terraform tests, offline plan checked by conftest, supply chain, secrets
make up      # preflight of the host ports, then local gateway, Keycloak and fake Bedrock (Docker Compose)
make e2e     # end-to-end tests against the running stack
make redteam # OWASP LLM red team of the gateway, against the running stack
make down
```

To check a real account, save `get-inference-profile` answers as `<source-region>__<profile-id>.json` and run:

```bash
cd tools && uv run python -m crfr.bedrock_inventory check-aws --inventory ../infra/inventory/bedrock-claude.json answers/*.json
```

## Limits

- No Claude offering is processed in Paris only: Paris is a source and a destination of the `eu.` profile, never an in-Region option.
- The kit does not claim HDS (French health data hosting) certification or SecNumCloud qualification. Sensitive State data covered by article 31 of the SREN law stays out of scope (see the public sector sheet). The high-risk rules of the AI Act for annex III uses apply from 2 December 2027 since regulation (EU) 2026/1744.
- The Anthropic API offers only `global` or `us` as inference geography (checked on 2026-11-16), so the kit does not use it for EU residency. Microsoft Foundry is not covered: its EU options for Claude are still to be verified.

## Licence

Apache-2.0, see [LICENSE](LICENSE). Content derived from the FINOS AI Governance Framework is CC BY 4.0, see [NOTICE](NOTICE).
