# Contributing

- One change per pull request, squash-merged once CI is green.
- `make ci` must pass locally: lint, tests, offline plan checked by conftest, supply-chain gate, secret scan.
- Pin everything: GitHub Actions by commit SHA, images by `sha256` digest, Python packages with `==` (locked with hashes in `uv.lock`). The supply-chain gate enforces it.
- Every control needs a test that fails when the control is removed, and a line in the traceability matrix (`compliance/`).
- Facts about providers (Regions, retention, certifications) need a primary source and a date in `docs/sources/verifications.md`.
- No real personal data, no customer names, no secrets. Test data is synthetic.
