"""python -m crfr_eval {report,compare,kappa,passk,seal,record} ..."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import cassettes, report
from .metrics import cohen_kappa, dataset_pass_hat_k
from .results import load

ROOT = Path(__file__).resolve().parent.parent
KAPPA_THRESHOLD = 0.6  # backlog E6.4


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="crfr_eval")
    sub = parser.add_subparsers(dest="command", required=True)
    rep = sub.add_parser("report", help="markdown report and gate of a promptfoo run")
    rep.add_argument("run", type=Path)
    rep.add_argument("--out", type=Path)
    rep.add_argument("--title", default="Evaluation")
    rep.add_argument("--k", type=int, help="pass^k, for runs made with --repeat")
    rep.add_argument("--min-pass-rate", type=float, default=1.0)
    cmp_ = sub.add_parser("compare", help="model migration: the new run must not regress (E6.5)")
    cmp_.add_argument("old", type=Path)
    cmp_.add_argument("new", type=Path)
    kap = sub.add_parser("kappa", help="agreement judge/human and human/human (E6.4)")
    kap.add_argument("labels", type=Path)
    kap.add_argument("--threshold", type=float, default=KAPPA_THRESHOLD)
    pk = sub.add_parser("passk", help="pass^k of a run made with --repeat n (n >= k)")
    pk.add_argument("run", type=Path)
    pk.add_argument("--k", type=int, required=True)
    neg = sub.add_parser("negative", help="negative control: every task must fail")
    neg.add_argument("run", type=Path)
    for name in ("seal", "record"):
        cmd = sub.add_parser(name, help=cassettes.__doc__.splitlines()[0] if name == "seal" else "record a live run")
        cmd.add_argument("run", type=Path)
        if name == "record":
            cmd.add_argument("--model", required=True)
    args = parser.parse_args(argv)

    if args.command == "report":
        outcomes = load(args.run)
        text = report.markdown(outcomes, args.title, args.k, args.min_pass_rate)
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        print(text)
        problems = report.gate_all(outcomes, args.min_pass_rate)
        for p in problems:
            print(f"GATE: {p}", file=sys.stderr)
        return 1 if problems else 0
    if args.command == "compare":
        result = report.compare(load(args.old), load(args.new))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["problems"] else 0
    if args.command == "kappa":
        with args.labels.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        judge_human = cohen_kappa([r["judge"] for r in rows], [r["human_a"] for r in rows])
        human_human = cohen_kappa([r["human_a"] for r in rows], [r["human_b"] for r in rows])
        ok = judge_human >= args.threshold and human_human >= args.threshold
        print(json.dumps({"items": len(rows), "judge_vs_human": round(judge_human, 3),
                          "human_vs_human": round(human_human, 3), "threshold": args.threshold, "ok": ok}))  # fmt: skip
        return 0 if ok else 1
    if args.command == "passk":
        outcomes = load(args.run)
        print(json.dumps({"k": args.k, "all": round(dataset_pass_hat_k(outcomes, args.k), 4),
                          "critical": round(dataset_pass_hat_k(outcomes, args.k, critical_only=True), 4)}))  # fmt: skip
        return 0
    if args.command == "negative":
        outcomes = load(args.run)
        passed = sorted({o.task_id for o in outcomes if o.outcome != "fail"})
        print(json.dumps({"tasks": len({o.task_id for o in outcomes}), "not_failed": passed}))
        return 1 if passed or not outcomes else 0
    if args.command == "seal":
        print("\n".join(cassettes.seal(args.run, ROOT)) or "nothing to seal")
        return 0
    print("\n".join(cassettes.record(args.run, ROOT, args.model)) or "nothing recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
