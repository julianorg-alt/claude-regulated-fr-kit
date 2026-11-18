import json

from crfr_eval import cassettes, report
from crfr_eval.results import ERROR, FAIL, HUMAN, PASS, load, outcome_of


def row(task="banque-01", critical=False, components=(), success=None, error=None, output="ok"):
    comps = [
        {"pass": p, "reason": r, "assertion": {"type": t, "metric": m, "value": v}} for t, m, p, r, v in components
    ]
    return {
        "vars": {"id": task, "sector": task.split("-")[0], "critical": critical},
        "success": all(c["pass"] for c in comps) if success is None else success,
        "error": error,
        "failureReason": 2 if error else (0 if all(c["pass"] for c in comps) else 1),
        "prompt": {"raw": f"prompt of {task}"},
        "response": {"output": output},
        "gradingResult": {"componentResults": comps},
    }


CODE_OK = ("icontains", "", True, "ok", "x")
CODE_KO = ("icontains", "", False, "missing x", "x")
JUDGE_OK = ("llm-rubric", "exactitude", True, "bien", "[grille banque-01/exactitude] crit")
JUDGE_UNKNOWN = ("llm-rubric", "ton", False, "INCONNU : registre non évaluable", "[grille banque-01/ton] crit")
JUDGE_KO = ("llm-rubric", "ton", False, "trop familier", "[grille banque-01/ton] crit")


def test_outcomes_follow_code_then_judge_then_human():
    assert outcome_of(row(components=[CODE_OK, JUDGE_OK])).outcome == PASS
    assert outcome_of(row(components=[CODE_KO, JUDGE_OK])).outcome == FAIL
    assert outcome_of(row(components=[CODE_OK, JUDGE_UNKNOWN])).outcome == HUMAN
    assert outcome_of(row(components=[CODE_KO, JUDGE_UNKNOWN])).outcome == FAIL  # code failure is decided
    assert outcome_of(row(components=[CODE_OK, JUDGE_KO])).outcome == FAIL
    assert outcome_of(row(error="no cassette")).outcome == ERROR


def write_run(tmp_path, rows, name="run.json"):
    path = tmp_path / name
    path.write_text(json.dumps({"results": {"results": rows}}))
    return path


def test_gate_blocks_critical_failures_and_errors(tmp_path):
    outcomes = load(write_run(tmp_path, [row(), row("sante-01", True, [CODE_KO]), row("public-01", True, error="x")]))
    s = report.summary(outcomes)
    assert s["critical_failures"] == ["public-01", "sante-01"] and s["errors"] == ["public-01"]
    assert len(report.gate(s, 0.5)) == 2
    ok = load(write_run(tmp_path, [row(components=[CODE_OK]), row("banque-02", components=[JUDGE_UNKNOWN])]))
    assert report.gate(report.summary(ok), 1.0) == []
    assert "banque-02" in report.markdown(ok, "t")


def test_compare_flags_regressions(tmp_path):
    old = load(
        write_run(tmp_path, [row(critical=True, components=[CODE_OK]), row("banque-02", components=[CODE_OK])], "o")
    )
    new = load(
        write_run(tmp_path, [row(critical=True, components=[CODE_KO]), row("banque-02", components=[CODE_OK])], "n")
    )
    result = report.compare(old, new)
    assert result["regressions"] == ["banque-01"] and len(result["problems"]) == 2
    assert report.compare(old, old)["problems"] == []


def test_seal_fills_only_empty_hashes_and_record_writes_cassettes(tmp_path):
    for d in ("answers", "judge"):
        (tmp_path / "cassettes" / d).mkdir(parents=True)
    answer = tmp_path / "cassettes" / "answers" / "banque-01.json"
    answer.write_text(json.dumps({"id": "banque-01", "prompt_sha256": "", "output": "ok"}))
    judge = tmp_path / "cassettes" / "judge" / "banque-01.exactitude.json"
    judge.write_text(json.dumps({"answer_sha256": "", "pass": True, "score": 1, "reason": "r"}))
    run = write_run(tmp_path, [row(components=[JUDGE_OK])])
    assert len(cassettes.seal(run, tmp_path)) == 2
    assert json.loads(answer.read_text())["prompt_sha256"] == cassettes.prompt_sha256("prompt of banque-01")
    assert json.loads(judge.read_text())["answer_sha256"] == cassettes.sha256("ok")
    assert cassettes.seal(run, tmp_path) == []
    cassettes.record(write_run(tmp_path, [row(components=[JUDGE_KO], output="nouvelle")], "live"), tmp_path, "m")
    assert json.loads(answer.read_text())["source"] == "recorded"
    assert json.loads((tmp_path / "cassettes" / "judge" / "banque-01.ton.json").read_text())["pass"] is False
