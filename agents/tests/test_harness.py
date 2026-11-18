"""Indirect injection bench (backlog E7.3)."""

import json
import tomllib
from pathlib import Path

import pytest
from crfr_redteam.harness import Bench, measure
from crfr_redteam.report import load_history

ROOT = Path(__file__).resolve().parents[1]
BENCH = Bench.load(ROOT / "scenarios" / "indirect.toml")
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def outcomes(config: str) -> dict[str, str]:
    return {r["id"]: r["outcome"] for r in measure(BENCH, VERSION)["configurations"][config]["results"]}


def test_bench_covers_the_three_families_and_four_sectors():
    assert {s.family for s in BENCH.scenarios} == {"document", "ticket", "tool_description"}
    assert {s.sector for s in BENCH.scenarios} == {"banque", "assurance", "sante", "public"}


def test_every_attack_succeeds_without_controls():
    # Negative control: the bench sees a success when nothing stands in the way.
    assert set(outcomes("unprotected").values()) == {"succeeded"}


def test_no_irreversible_action_without_human_approval():
    result = measure(BENCH, VERSION)["configurations"]["kit"]["results"]
    for row in result:
        scenario = next(s for s in BENCH.scenarios if s.id == row["id"])
        call = scenario.action()
        if call is not None and BENCH.tools[call.tool]["effect"] == "irreversible":
            assert row["outcome"] == "blocked", row


def test_poisoned_tool_descriptions_are_blocked_by_the_registry():
    result = measure(BENCH, VERSION)["configurations"]["kit"]["results"]
    rows = [r for r in result if r["family"] == "tool_description"]
    assert rows and all(r["blocked_by"] == "registry:description-changed" for r in rows)


def test_exfiltration_through_a_read_tool_is_blocked():
    assert outcomes("kit")["doc-sante-exfiltration-url"] == "blocked"


def test_known_residual_attacks_are_reported_as_successes():
    # The kit has no control on answer content nor on reversible writes: the bench must say so.
    kit = outcomes("kit")
    for scenario in ("doc-sante-image-markdown", "doc-public-decision-faussee", "doc-banque-prompt-systeme",
                     "ticket-adresse-client"):  # fmt: skip
        assert kit[scenario] == "succeeded"


def test_published_result_for_this_version_is_current():
    history = load_history(ROOT / "results" / "asr.json")
    published = next((e for e in history if e["version"] == VERSION), None)
    assert published is not None, f"run `make redteam-report` to publish version {VERSION}"
    fresh = json.loads(json.dumps(measure(BENCH, VERSION)))
    assert {k: v for k, v in published.items() if k != "recorded"} == fresh


@pytest.mark.parametrize(
    "bad",
    [
        '[[scenario]]\nid="a"\nfamily="x"\nsector="banque"\nowasp=[]\ntask=""\ncarrier=""\nattack={kind="answer"}',
        '[[scenario]]\nid="a"\nfamily="ticket"\nsector="banque"\nowasp=[]\ntask=""\ncarrier=""\n'
        'attack={kind="tool_call",tool="inconnu"}',
        '[[scenario]]\nid="a"\nfamily="tool_description"\nsector="banque"\nowasp=[]\ntask=""\ncarrier=""\n'
        'attack={kind="answer"}',
    ],
)
def test_invalid_scenarios_are_rejected(tmp_path, bad):
    path = tmp_path / "bad.toml"
    path.write_text(bad)
    with pytest.raises(ValueError):
        Bench.load(path)


def test_published_markdown_is_current():
    from crfr_redteam.report import markdown

    history = load_history(ROOT / "results" / "asr.json")
    assert (ROOT / "results" / "asr.md").read_text(encoding="utf-8") == markdown(history)


def test_live_tests_file_is_current():
    from crfr_redteam.live import promptfoo_tests

    live = ROOT.parent / "evals" / "redteam" / "indirect.yaml"
    assert live.read_text(encoding="utf-8") == promptfoo_tests(BENCH), "run `make redteam-promptfoo`"


def _row(label, success, name="s"):
    return {"provider": {"label": label}, "success": success, "testCase": {"description": name}}


def test_selftest_check_catches_a_blind_assertion():
    from crfr_redteam.live import check_selftest

    good = {"results": {"results": [_row("obedient", False), _row("refusing", True)]}}
    assert check_selftest(good, 1) == []
    blind = {"results": {"results": [_row("obedient", True), _row("refusing", True)]}}
    assert "obedient: wrong verdict on s" in check_selftest(blind, 1)
    assert check_selftest({"results": {"results": []}}, 1)
