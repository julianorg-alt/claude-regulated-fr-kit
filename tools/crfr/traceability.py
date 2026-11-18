"""Traceability matrix of the kit's controls (backlog E9.1).

Reads compliance/controls.toml and compliance/texts.toml, checks that every control cites at least one text
and one test, that every reference resolves (the text exists; the test file exists and defines the test),
that no text is left unused, and writes docs/compliance/matrix.md. The templates of compliance/templates.toml
(backlog E9.2) are checked too: the file exists, its level-2 headings contain the required sections in order,
and every control and text it cites exists. ``check`` fails when the committed matrix
differs from what the data gives.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

MATRIX = Path("docs/compliance/matrix.md")
KINDS = ("pytest", "unittest", "tftest", "rego", "make")


@dataclass(frozen=True)
class Problem:
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.where}: {self.message}"


def load_templates(root: Path) -> list[dict]:
    path = root / "compliance" / "templates.toml"
    if not path.is_file():
        return []
    return tomllib.loads(path.read_text(encoding="utf-8")).get("template", [])


def check_template(root: Path, template: dict, controls: set[str], texts: dict) -> list[Problem]:
    mid = template.get("id", "?")
    problems = [Problem(mid, f"unknown text {tid}") for tid in template.get("texts", []) if tid not in texts]
    file = root / template.get("path", "")
    if not file.is_file():
        return [*problems, Problem(mid, f"no file {template.get('path')}")]
    content = file.read_text(encoding="utf-8")
    headings = [h.strip() for h in re.findall(r"^## (.+)$", content, re.M)]
    position = 0
    for section in template.get("sections", []):
        try:
            position = headings.index(section, position) + 1
        except ValueError:
            problems.append(Problem(mid, f"section {section!r} missing or out of order"))
    for cid in sorted(set(re.findall(r"\bC\d{1,3}\b", content)) - controls):
        problems.append(Problem(mid, f"cites unknown control {cid}"))
    return problems


def load(root: Path) -> tuple[list[dict], dict[str, dict]]:
    controls = tomllib.loads((root / "compliance" / "controls.toml").read_text(encoding="utf-8"))["control"]
    texts = tomllib.loads((root / "compliance" / "texts.toml").read_text(encoding="utf-8"))["text"]
    return controls, {t["id"]: t for t in texts}


def resolve(root: Path, ref: str) -> str | None:
    """None when the test reference exists, else why not."""
    kind, _, rest = ref.partition(":")
    if kind not in KINDS:
        return f"unknown test kind {kind!r}"
    if kind == "make":
        makefile = (root / "Makefile").read_text(encoding="utf-8")
        return None if re.search(rf"^{re.escape(rest)}:", makefile, re.M) else f"no make target {rest}"
    path, _, name = rest.partition("::")
    file = root / path
    if not name or not file.is_file():
        return f"no file {path}" if not file.is_file() else "missing ::name"
    text = file.read_text(encoding="utf-8")
    if kind == "pytest":
        pattern = rf"^\s*def {re.escape(name)}\("
    elif kind == "unittest":
        cls, _, method = name.partition(".")
        if not re.search(rf"^class {re.escape(cls)}\b", text, re.M):
            return f"no class {cls} in {path}"
        pattern = rf"^\s+def {re.escape(method)}\("
    elif kind == "tftest":
        pattern = rf'^run "{re.escape(name)}"'
    else:
        pattern = rf"^{re.escape(name)} if\b"
    return None if re.search(pattern, text, re.M) else f"{name} not found in {path}"


def check(root: Path) -> list[Problem]:
    controls, texts = load(root)
    problems, used, seen = [], set(), set()
    for control in controls:
        cid = control.get("id", "?")
        if cid in seen:
            problems.append(Problem(cid, "duplicate control id"))
        seen.add(cid)
        if not control.get("texts"):
            problems.append(Problem(cid, "orphan control: no text"))
        if not control.get("tests"):
            problems.append(Problem(cid, "orphan control: no test"))
        for tid in control.get("texts", []):
            used.add(tid)
            if tid not in texts:
                problems.append(Problem(cid, f"unknown text {tid}"))
        for ref in control.get("tests", []):
            why = resolve(root, ref)
            if why:
                problems.append(Problem(cid, why))
    for template in load_templates(root):
        used.update(template.get("texts", []))
        problems += check_template(root, template, seen, texts)
    for tid in sorted(set(texts) - used):
        problems.append(Problem(tid, "text cited by no control"))
    verifications = (root / "docs" / "sources" / "verifications.md").read_text(encoding="utf-8")
    for tid, text in texts.items():
        ref = text.get("verification")
        if ref and not re.search(rf"^\| {re.escape(ref)} \|", verifications, re.M):
            problems.append(Problem(tid, f"verification {ref} not in verifications.md"))
    return problems


def _test_label(ref: str) -> str:
    kind, _, rest = ref.partition(":")
    path, _, name = rest.partition("::")
    return f"`{rest}` ({kind})" if kind == "make" else f"`{name}` ({kind}, `{path}`)"


def render(root: Path) -> str:
    controls, texts = load(root)
    lines = [
        "# Matrice de traçabilité",
        "",
        "Générée par `make traceability` depuis `compliance/controls.toml` et `compliance/texts.toml` ; "
        "ne pas modifier à la main. Chaque contrôle est relié à au moins un texte et à au moins un test "
        "automatisé ; la CI échoue sinon (backlog E9.1).",
        "",
        "Un texte « à vérifier » n'a pas encore été lu sur sa source primaire depuis la session de "
        "développement : le rattachement est proposé, pas établi.",
        "",
        "## Contrôles",
        "",
        "| Contrôle | Textes | Tests |",
        "|---|---|---|",
    ]
    for c in controls:
        cited = ", ".join(c["texts"])
        tests = "<br>".join(_test_label(t) for t in c["tests"])
        lines.append(f"| {c['id']} : {c['title']} | {cited} | {tests} |")
    templates = load_templates(root)
    if templates:
        lines += ["", "## Modèles", "", "| Modèle | Fichier | Textes |", "|---|---|---|"]
        for m in templates:
            name = m["path"].rsplit("/", 1)[-1]
            link = m["path"].removeprefix("docs/compliance/")
            lines.append(f"| {m['id']} : {m['title']} | [{name}]({link}) | {', '.join(m['texts'])} |")
    lines += ["", "## Textes", "", "| Texte | Référence | Statut | Contrôles et modèles |", "|---|---|---|---|"]
    for tid, t in texts.items():
        status = f"vérifié ({t['verification']})" if t.get("verification") else "à vérifier"
        users = [c["id"] for c in controls if tid in c["texts"]] + [m["id"] for m in templates if tid in m["texts"]]
        lines.append(f"| {tid} : {t['title']} | [{t['reference']}]({t['url']}) | {status} | {', '.join(users)} |")
    unverified = sum(1 for t in texts.values() if not t.get("verification"))
    summary = f"{len(controls)} contrôles, {len(templates)} modèles, {len(texts)} textes dont {unverified} à vérifier."
    lines += ["", summary, ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("check", "write"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    problems = check(args.root)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    matrix = args.root / MATRIX
    text = render(args.root)
    if args.command == "write":
        matrix.parent.mkdir(parents=True, exist_ok=True)
        matrix.write_text(text, encoding="utf-8")
        print(f"wrote {MATRIX}")
        return 0
    if not matrix.exists() or matrix.read_text(encoding="utf-8") != text:
        print(f"{MATRIX} is stale: run make traceability", file=sys.stderr)
        return 1
    print("traceability: every control has a text and a test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
