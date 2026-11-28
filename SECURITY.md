# Security policy

## Reporting a vulnerability

Report privately through GitHub's "Report a vulnerability" (Security tab of this repository), not in a public issue or pull request. Do not include real personal data, credentials or a working exploit against a third party's system; a minimal reproduction on the local stack (`make demo`) is enough.

What to expect: an acknowledgement within 7 days and a first assessment within 14 days. This is a best-effort commitment from a small project, not a contractual service level. Fixes land on `main`. There is no bug bounty.

## Supported versions

Only the latest commit of `main` receives fixes.

## Scope

In scope: everything in this repository, including the gateway and its guard, the pseudonymisation code, the Terraform modules, the Rego policies, the evaluation and red-team tooling, and the compliance inventory. Examples of reports we want:

- A route that lets a request be processed outside the declared jurisdiction (a non-EU inference region, a `global.` profile, an unlisted egress host). This is treated as a vulnerability.
- A way to bypass authentication, the per-group model authorisation, the pseudonymisation of personal data or the audit chain.
- A policy (Rego or Terraform) that passes while allowing what its test says it forbids.
- A secret, token or personal data committed anywhere in the history.

Out of scope: the local demo stack's fixed development keys and fake Bedrock (they are fictitious by design), findings that need a deployment this kit does not describe, volumetric denial of service, vulnerabilities in third-party components with no effect on the kit (report those upstream), and legal conclusions in `docs/compliance/` (open an issue instead; they are not security vulnerabilities).

## Secrets and personal data

The kit never needs real credentials in the repository. Values that look like keys in tests (for example `AKIA...` patterns) are fictitious fixtures. CI runs `gitleaks` on the full history on every run. Anything that looks like a real secret in a commit is a bug: report it, and rotate the credential.

## Coordinated disclosure

Please allow a reasonable time to fix before any public disclosure. Reporters who wish to be credited are named in the fix's commit message.
