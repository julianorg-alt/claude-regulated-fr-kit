"""Markdown report and CI gate of an evaluation run."""

from __future__ import annotations

from .metrics import dataset_pass_hat_k
from .results import ERROR, FAIL, HUMAN, PASS, Outcome, by_task, split


def summary(outcomes: list[Outcome]) -> dict:
    sectors: dict[str, dict] = {}
    for o in outcomes:
        row = sectors.setdefault(o.sector, {PASS: 0, FAIL: 0, HUMAN: 0, ERROR: 0})
        row[o.outcome] += 1
    total = {k: sum(r[k] for r in sectors.values()) for k in (PASS, FAIL, HUMAN, ERROR)}
    decided = total[PASS] + total[FAIL]
    return {
        "sectors": sectors,
        "total": total,
        "pass_rate": round(total[PASS] / decided, 4) if decided else None,
        "critical_failures": sorted({o.task_id for o in outcomes if o.critical and o.outcome in (FAIL, ERROR)}),
        "human_review": sorted({o.task_id for o in outcomes if o.outcome == HUMAN}),
        "errors": sorted({o.task_id for o in outcomes if o.outcome == ERROR}),
    }


def gate(s: dict, min_pass_rate: float) -> list[str]:
    problems = []
    if s["errors"]:
        problems.append(f"errors on {', '.join(s['errors'])}")
    if s["critical_failures"]:
        problems.append(f"critical tasks failed: {', '.join(s['critical_failures'])}")
    if s["pass_rate"] is None or s["pass_rate"] < min_pass_rate:
        problems.append(f"pass rate {s['pass_rate']} below {min_pass_rate}")
    return problems


def gate_all(outcomes: list[Outcome], min_pass_rate: float) -> list[str]:
    """Gate of the main tasks, then the same gate on the hold-out set (lines prefixed "hold-out:")."""
    main, holdout = split(outcomes)
    problems = gate(summary(main), min_pass_rate)
    if holdout:
        problems += [f"hold-out: {p}" for p in gate(summary(holdout), min_pass_rate)]
    return problems


def markdown(outcomes: list[Outcome], title: str, k: int | None = None, min_pass_rate: float | None = None) -> str:
    main, holdout = split(outcomes)
    text = _section(main, f"# {title}", k, min_pass_rate)
    if holdout:
        text += "\n" + _section(holdout, "## Hold-out (never used to tune the prompt)", k, min_pass_rate)
    return text


def _section(outcomes: list[Outcome], heading: str, k: int | None, min_pass_rate: float | None) -> str:
    s = summary(outcomes)
    lines = [heading, "", "| Sector | Pass | Fail | Human review | Error |", "|---|---|---|---|---|"]
    for sector, row in sorted(s["sectors"].items()):
        lines.append(f"| {sector} | {row[PASS]} | {row[FAIL]} | {row[HUMAN]} | {row[ERROR]} |")
    t = s["total"]
    lines += [
        f"| all | {t[PASS]} | {t[FAIL]} | {t[HUMAN]} | {t[ERROR]} |",
        "",
        f"Pass rate (decided): {s['pass_rate']}",
    ]
    if k:
        lines.append(f"pass^{k}: {dataset_pass_hat_k(outcomes, k):.4f}; critical tasks: "
                     f"{dataset_pass_hat_k(outcomes, k, critical_only=True):.4f}")  # fmt: skip
    lines += ["", "Critical failures: " + (", ".join(s["critical_failures"]) or "none")]
    if min_pass_rate is not None:
        verdict = "closed: " + "; ".join(gate(s, min_pass_rate)) if gate(s, min_pass_rate) else "open"
        lines += ["", f"Gate (pass rate {min_pass_rate}, no critical failure, no error): {verdict}"]
    lines += ["", "Sent to a human (judge answered INCONNU):", ""]
    seen = set()
    for o in outcomes:
        if o.outcome == HUMAN and o.task_id not in seen:
            seen.add(o.task_id)
            lines.append(f"- {o.task_id}: {o.reason}")
    if not seen:
        lines.append("- none")
    failures = {o.task_id: o for o in outcomes if o.outcome in (FAIL, ERROR)}
    lines += ["", "Failures:", ""] + ([f"- {i}: {o.reason}" for i, o in sorted(failures.items())] or ["- none"])
    return "\n".join(lines) + "\n"


def compare(old: list[Outcome], new: list[Outcome]) -> dict:
    """Model migration check (E6.5): the new run must be at least as good as the old one."""
    before = {i: all(r.outcome == PASS for r in runs) for i, runs in by_task(old).items()}
    after = {i: all(r.outcome == PASS for r in runs) for i, runs in by_task(new).items()}
    critical = {o.task_id for o in new if o.critical} | {o.task_id for o in old if o.critical}
    regressions = sorted(i for i, ok in before.items() if ok and not after.get(i, False))
    missing = sorted(set(before) - set(after))
    s_old, s_new = summary(old), summary(new)
    problems = []
    if missing:
        problems.append(f"tasks missing from the new run: {', '.join(missing)}")
    if [i for i in regressions if i in critical]:
        problems.append(f"critical regressions: {', '.join(i for i in regressions if i in critical)}")
    if (s_new["pass_rate"] or 0) < (s_old["pass_rate"] or 0):
        problems.append(f"pass rate fell from {s_old['pass_rate']} to {s_new['pass_rate']}")
    return {"regressions": regressions, "pass_rate": [s_old["pass_rate"], s_new["pass_rate"]], "problems": problems}
