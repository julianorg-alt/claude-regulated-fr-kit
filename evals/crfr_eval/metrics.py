"""pass^k (τ-bench) and Cohen's kappa (backlog E6.4)."""

from __future__ import annotations

from collections import Counter
from math import comb

from .results import PASS, Outcome, by_task


def pass_hat_k(n: int, c: int, k: int) -> float:
    """Chance that k i.i.d. trials all succeed, estimated from c successes in n trials: C(c,k)/C(n,k)."""
    if not 1 <= k <= n:
        raise ValueError(f"k must be between 1 and the number of trials ({n})")
    if not 0 <= c <= n:
        raise ValueError("successes must be between 0 and n")
    return comb(c, k) / comb(n, k)


def dataset_pass_hat_k(outcomes: list[Outcome], k: int, critical_only: bool = False) -> float:
    tasks = by_task(outcomes)
    values = []
    for runs in tasks.values():
        if critical_only and not runs[0].critical:
            continue
        values.append(pass_hat_k(len(runs), sum(r.outcome == PASS for r in runs), k))
    if not values:
        raise ValueError("no task to score")
    return sum(values) / len(values)


def cohen_kappa(a: list[str], b: list[str]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("two non-empty label lists of the same length are needed")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[label] * cb[label] for label in set(ca) | set(cb)) / (n * n)
    if expected == 1:
        return 1.0 if observed == 1 else 0.0
    return (observed - expected) / (1 - expected)
