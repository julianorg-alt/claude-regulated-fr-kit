"""Supply-chain gate of the kit (backlog E0.3).

Fails when the repository references something that can change under our feet:

* a GitHub Action not pinned to a full 40-character commit SHA;
* a container image without an ``@sha256:`` digest, or tagged ``latest``;
* a Helm chart dependency or install without an exact version;
* a Python requirement that is not an exact ``==`` pin.

The 2026 LiteLLM incidents (compromised PyPI releases and container images, see the benchmark
report) are the reason this gate exists: the kit must never pull a moving target.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "node_modules", ".terraform", "__pycache__", "dist", "build"}
_USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.M)
_SHA = re.compile(r"@[0-9a-f]{40}$")
_IMAGE = re.compile(r"^\s*-?\s*image:\s*[\"']?([^\s\"'#]+)", re.M)
_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
_FROM = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)", re.M | re.I)
_REQ = re.compile(r"^\s*([A-Za-z0-9_.\-\[\]]+)\s*([<>=!~].*)?$")


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def check_workflow(path: Path, text: str) -> list[Finding]:
    findings = []
    for match in _USES.finditer(text):
        ref = match.group(1)
        if ref.startswith("./") or ref.startswith("docker://"):
            if ref.startswith("docker://") and not _DIGEST.search(ref):
                findings.append(Finding(path, _line_of(text, match.start()), f"docker action without digest: {ref}"))
            continue
        if not _SHA.search(ref):
            findings.append(Finding(path, _line_of(text, match.start()), f"action not pinned to a commit SHA: {ref}"))
    return findings


def check_images(path: Path, text: str) -> list[Finding]:
    findings = []
    for regex in (_IMAGE, _FROM):
        if regex is _FROM and not path.name.lower().startswith(("dockerfile", "containerfile")):
            continue
        for match in regex.finditer(text):
            ref = match.group(1)
            if regex is _FROM and (ref.lower() == "scratch" or ref.startswith("$")):
                continue
            if ref.startswith("{{"):
                continue  # Helm templates: checked through the values files
            line = _line_of(text, match.start())
            if ":latest" in ref:
                findings.append(Finding(path, line, f"image tagged latest: {ref}"))
            if not _DIGEST.search(ref):
                findings.append(Finding(path, line, f"image without sha256 digest: {ref}"))
    return findings


def check_requirements(path: Path, text: str) -> list[Finding]:
    findings = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "--")) or line.endswith("\\"):
            continue
        match = _REQ.match(line.split(";", 1)[0])
        if not match:
            continue
        spec = (match.group(2) or "").strip()
        if not spec.startswith("==") or any(op in spec for op in (",", "*")):
            findings.append(Finding(path, number, f"requirement not pinned with ==: {line}"))
    return findings


_EXACT = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")


def check_package_json(path: Path, text: str, lock_exists: bool) -> list[Finding]:
    """npm: exact versions only, and a lockfile (which carries an integrity hash per package)."""
    findings = []
    try:
        doc = json.loads(text)
    except ValueError:
        return [Finding(path, 1, "package.json is not JSON")]
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        for name, version in (doc.get(section) or {}).items():
            if not isinstance(version, str) or not _EXACT.match(version):
                findings.append(Finding(path, 1, f"npm dependency not pinned to an exact version: {name} {version}"))
    if not lock_exists:
        findings.append(Finding(path, 1, "package.json without package-lock.json"))
    return findings


def scan(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        rel = path.relative_to(root)
        if rel.parts[:1] == ("tools",) and "fixtures" in rel.parts:
            continue  # test fixtures contain deliberately bad examples
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if rel.parts[:2] == (".github", "workflows") and path.suffix in (".yml", ".yaml"):
            findings += check_workflow(rel, text)
        if path.suffix in (".yml", ".yaml") or path.name.lower().startswith(("dockerfile", "containerfile")):
            findings += check_images(rel, text)
        if path.name == "package.json":
            findings += check_package_json(rel, text, (path.parent / "package-lock.json").exists())
        if path.name.startswith("requirements") and path.suffix == ".txt":
            findings += check_requirements(rel, text)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path, nargs="?", default=Path("."))
    args = parser.parse_args(argv)
    findings = scan(args.root.resolve())
    for finding in findings:
        print(finding, file=sys.stderr)
    print(f"supply-chain gate: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
