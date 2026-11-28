# Verification report A (28 November 2026)

Clean-clone verification of three repositories. Everything below was run in a disposable Linux container on 28/11/2026, from fresh clones; nothing is quoted from memory. Where a result is a failure or a limit, it is stated as such.

Repositories: `claude-regulated-fr` (private source, HEAD `a1a5870`), `claude-regulated-fr-kit` (public, `main` at `77c08d2`), `mcp-dpe-fr` (public, `main` at `6d75e5d`).

## 1. Tests and demo on clean clones

| Check | Result |
|---|---|
| Kit, `make ci` (lint, tests, Terraform tests, Conftest, supply-chain gate, gitleaks) | **passed**, exit 0, 4 min 37 s. Counts: tools 79, pseudonymisation 55, guard 69, evals 67, agents 73 pytest tests, 0 failed; Terraform 6 modules (2+10+3+4+4+4 test runs) and 1 offline plan, 0 failed; Conftest 6 + 7 policy tests + 5 plan tests, 0 failed; supply-chain gate 0 finding; gitleaks on the clone's history: no leaks |
| Private, `make ci` | **passed**, exit 0 (tools suite has 96 tests instead of 79: the extra tests check the owner-only publication files and the export script, which the public kit does not ship) |
| Kit, `make demo` | **passed after a workaround, not as documented** (see below). The three steps print the expected result: no token gives 401; a model with no EU route gives 403; a prompt with an NIR and an IBAN reaches the fake Bedrock as `<NIR_1>` and `<IBAN_1>` |
| Kit, `make e2e` (36 tests against the running stack) | **passed** (OK) |
| Kit, kill-switch drill | three levels refuse in 0.21 to 0.31 s |
| Private, `make demo` | **passed** (same workaround; images were the ones built from the kit, not rebuilt from the private tree) |
| `mcp-dpe-fr`: `uv sync`, `ruff check`, `ruff format --check`, `pytest -q`, `evals/run_eval.py --mode replay` | **all passed**: 45 tests passed; replay 19/19 |

Reading the CI numbers without error:

- The cassette replay reports **96 of 100 passed, 4 failed**. The raw 4 failures are real and are not hidden: the pass threshold is applied by `crfr_eval report`, not by promptfoo (the Makefile sets `PROMPTFOO_FAILED_TEST_EXIT_CODE=0`).
- The negative control reports 100 of 100 failed on purpose; `crfr_eval negative` then checks that nothing passed (`not_failed: []`). The red-team self-test shows 12 of 24 on the fake models by design ("obedient agent caught, refusing agent passed").
- The cassettes are written by hand and the red-team runs on a fake model: this is the kit's own stated limit and stays visible in the README. The replay therefore proves the pipeline and the scoring, not the quality of a live model.
- `mcp-dpe-fr` replay compares the tool's output with a reference computed from recorded API responses; 19 questions, no measure of answer quality.

Defect found: `make demo` fails on a clean clone behind a TLS-inspecting proxy, and the proxy workaround written in `gateway/README.md` did not work either: the documented command builds the guard image from `gateway/guard` as context, but its Dockerfile needs the repository root as context (error: `/pseudonymisation/crfr_pseudo: not found`). Corrected in this branch (the image names and the context are now given). Without a proxy, `make demo` builds the images itself; that path was not re-tested here because the sandbox has a TLS-inspecting proxy.

Not verified: `make eval-live`, `make benchmark` with the optional GLiNER backend, `make redteam-live`, `make up` with real AWS or Keycloak realms (they need credentials or models), the weekly API-drift job of `mcp-dpe-fr`, and PyPI publication of `mcp-dpe-fr`.

## 2. CI status of the latest commits

| Repository | Latest commit | State |
|---|---|---|
| Kit `main` (`77c08d2`) | push, scheduled `ci` and scheduled `redteam` runs | all **success** (last: `ci` 23/11, `redteam` 24/11) |
| Kit PR #1 (`b1dad42`) | `ci` on the pull request | success (10:13 UTC today) |
| Private `main` (`a1a5870`) | push, scheduled `ci` and scheduled `redteam` | all **success** (last: `ci` 23/11, `redteam` 24/11) |
| `mcp-dpe-fr` `main` (`6d75e5d`) | push `CI` | **success** (25/11). Only one run exists: the weekly drift job has not fired yet |

Earlier failures in the 20 latest private runs: one (a pull-request run on 21/11, fixed by the next push of the same branch). No failure on `main`.

## 3. Secret and identity scan of the public history

Scope: every revision of every branch of both public repositories (`git rev-list --all`).

| Check | Kit | `mcp-dpe-fr` |
|---|---|---|
| gitleaks on the full history | no leaks (3 commits, 3.75 MB) | no leaks (1 commit, 0.45 MB) |
| Commit authors and committers | 3 commits, all `claude-regulated-fr <noreply@example.invalid>` | **1 commit, author and committer carry a personal e-mail address** |
| E-mail addresses in files | only fictitious `example.org` or `.example` addresses, and one public institutional address (a French central bank contact) | none |
| AWS-style keys | two fictitious values: `AKIAIOSFODNN7EXAMPLE` (AWS documentation example) and `AKIAFAKEFAKEFAKE0000` | none |
| Forbidden terms of the private export script (9 patterns) | **one hit, on the PR #1 branch only** (an owner-only handoff note added by that pull request, see below); none on `main` | one hit: the owner's GitHub account name in the repository URL of the README install line (expected for a public URL, not a leak) |

Findings, by decreasing importance:

1. **Kit PR #1 puts an owner-only planning note in the public repository.** The branch is publicly readable even as a draft. The note must not be merged; closing the PR and deleting the branch is the owner's decision (history of a public branch cannot be un-published once indexed). The export script would have excluded it.
2. **`mcp-dpe-fr` first commit exposes a personal e-mail address as author and committer.** Fixing it means rewriting the single commit (force push), which changes the repository history: not done here, left to the owner. Alternative: leave as is.
3. Kit `main` contained `.claude/settings.json`, an owner-only file that the current export script excludes (the kit was published before that rule). Its content is harmless (auto-compaction setting and a command allow-list), no secret. Removed in this branch.

## 4. Re-alignment of the kit on the private repository

The kit `main` was built from the private tree before the exclusion of `.claude`. A fresh export of private HEAD `a1a5870` (`scripts/export-public.sh --no-ci`, forbidden-term scan: 0) was compared with kit `main`: **identical except `.claude/`, which the export no longer ships**. The kit is not behind on content; it is one export rule behind. This branch removes `.claude/` and does not rewrite history (an export as a new single-commit repository would; it was deliberately not used for the public repository).

## 5. Corrections in this branch (no history rewrite)

- `SECURITY.md`: reporting channel, expected response times (a best-effort commitment, to be confirmed by the owner), supported versions, in and out of scope, secrets and disclosure. Previously 6 lines.
- English summary at the top of the 11 compliance documents (`docs/compliance/**`, matrix included). The matrix is generated, so the summary is added in `tools/crfr/traceability.py` and the file regenerated; `make test-traceability` and the tools tests pass (79).
- `gateway/README.md`: working proxy build command.
- Removal of `.claude/settings.json`.
- The same changes are proposed on the private repository (branch `claude/verif-a-prive`) so that the next export does not revert them.

Public pull request: draft, not merged. Merging a public change is the owner's decision after a review of the final diff.
