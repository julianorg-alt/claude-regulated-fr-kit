"""The public README and the architecture page must stay true to the committed results."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")
SECTIONS = ["## Problem", "## Architecture", "## Quick start", "## Measured results", "## Limits"]


def test_required_sections_in_order():
    positions = [README.find(h) for h in SECTIONS]
    assert all(p >= 0 for p in positions), dict(zip(SECTIONS, positions, strict=True))
    assert positions == sorted(positions)


def test_quick_start_is_one_command():
    block = README.split("## Quick start", 1)[1].split("\n## ", 1)[0]
    assert "make demo" in block
    assert re.search(r"^demo:", (ROOT / "Makefile").read_text(), re.M)


def test_measured_results_match_committed_files():
    block = README.split("## Measured results", 1)[1].split("\n## ", 1)[0]
    pii = json.loads((ROOT / "datasets/pii-fr/results/v1-test-spacy.json").read_text())
    assert f"{pii['documents']} held-out documents" in block
    asr = json.loads((ROOT / "agents/results/asr.json").read_text())["versions"][-1]
    kit = asr["configurations"]["kit"]
    assert f"{round(kit['asr'] * 100)} %" in block
    assert f"{kit['succeeded']} of {kit['scenarios']}" in block
    tasks = sum(len(re.findall(r"^\s+id: ", p.read_text(), re.M)) for p in (ROOT / "evals/tasks").glob("*.yaml"))
    assert f"{tasks} tasks" in block
    assert "13 of 13" in block
    assert "pass^k" in block and "cassette" in block


def test_limits_are_stated():
    block = README.split("## Limits", 1)[1]
    for phrase in ("Paris", "HDS", "SecNumCloud"):
        assert phrase in block


def test_links_resolve():
    for target in re.findall(r"\]\((?!https?:|#)([^)#]+)", README):
        assert (ROOT / target).exists(), target


def test_architecture_page_matches_listeners_and_components():
    page = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    assert "```mermaid" in page
    for part in ("Envoy", "guard", "OPA", "Bedrock", "RustFS", "Keycloak", "MCP"):
        assert part in page, part
    assert "docs/architecture.md" in README


def test_limits_state_the_measured_quality_gap_of_the_exit_provider():
    block = README.split("## Limits", 1)[1]
    page = (ROOT / "docs/evals/exit-provider-2026-11-18.md").read_text(encoding="utf-8")
    main = re.search(r"\| Main set, decided pass rate \| ([0-9.]+) \| ([0-9.]+) ", page).groups()
    critical = re.search(r"\| Main set, critical tasks \| ([0-9.]+) \| ([0-9.]+) ", page).groups()
    assert "exit-provider-2026-11-18.md" in block
    for value in (*main, *critical):
        shown = f"{float(value):.4f}".rstrip("0")
        shown += "0" * max(0, 2 - len(shown.split(".")[1]))  # at least two decimals: 0.75, 1.00, 0.9356
        assert shown in block, shown
