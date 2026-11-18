"""Read a promptfoo JSON output into one outcome per (task, repeat).

Outcome order of the graders (backlog E6.3): code assertions, then the LLM judge, then a human. A result
whose only failing assertions are judge verdicts starting with "INCONNU" goes to a human, not to failures.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PASS, FAIL, HUMAN, ERROR = "pass", "fail", "human", "error"
HOLDOUT = "holdout"
JUDGE_TYPES = {"llm-rubric", "g-eval", "model-graded-closedqa"}


@dataclass(frozen=True)
class Outcome:
    task_id: str
    sector: str
    critical: bool
    outcome: str
    failed: tuple[str, ...]  # "type:metric" of failing assertions, for the report
    reason: str = ""
    group: str = "main"  # "holdout" for tasks of the hold-out set (var `set`), reported and gated separately


def _flag(value) -> bool:
    return value is True or str(value).lower() in ("true", "1", "yes", "oui")


def outcome_of(result: dict) -> Outcome:
    outcome = _outcome_of(result)
    group = str((result.get("vars") or {}).get("set", "main"))
    return Outcome(**{**outcome.__dict__, "group": group})


def _outcome_of(result: dict) -> Outcome:
    vars_ = result.get("vars") or {}
    task_id, sector, critical = str(vars_.get("id", "?")), str(vars_.get("sector", "?")), _flag(vars_.get("critical"))
    # promptfoo fills "error" for failed assertions too; failureReason 2 marks a real error (provider,
    # grader or invalid assertion), 1 an assertion failure.
    error = (result.get("response") or {}).get("error") or (result.get("failureReason") == 2 and result.get("error"))
    if error:
        return Outcome(task_id, sector, critical, ERROR, (), str(error)[:300])
    components = (result.get("gradingResult") or {}).get("componentResults") or []
    failing = [c for c in components if not c.get("pass")]
    labels = tuple(
        f"{(c.get('assertion') or {}).get('type', '?')}:{(c.get('assertion') or {}).get('metric', '')}" for c in failing
    )
    if not failing and result.get("success", True):
        return Outcome(task_id, sector, critical, PASS, ())
    judged_unknown = [
        c for c in failing
        if (c.get("assertion") or {}).get("type") in JUDGE_TYPES and str(c.get("reason", "")).startswith("INCONNU")
    ]  # fmt: skip
    if failing and len(judged_unknown) == len(failing):
        return Outcome(task_id, sector, critical, HUMAN, labels, judged_unknown[0].get("reason", "")[:300])
    reason = "; ".join(str(c.get("reason", ""))[:150] for c in failing) or str(result.get("failureReason", ""))
    return Outcome(task_id, sector, critical, FAIL, labels, reason)


def load(path: Path) -> list[Outcome]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data["results"]["results"] if "results" in data and isinstance(data["results"], dict) else data["results"]
    return [outcome_of(r) for r in rows]


def split(outcomes: list[Outcome]) -> tuple[list[Outcome], list[Outcome]]:
    """Main tasks and hold-out tasks. The hold-out is never mixed into the main figures."""
    return [o for o in outcomes if o.group != HOLDOUT], [o for o in outcomes if o.group == HOLDOUT]


def by_task(outcomes: list[Outcome]) -> dict[str, list[Outcome]]:
    grouped: dict[str, list[Outcome]] = {}
    for o in outcomes:
        grouped.setdefault(o.task_id, []).append(o)
    return grouped
