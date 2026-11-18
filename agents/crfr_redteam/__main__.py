"""python -m crfr_redteam report | promptfoo (backlog E7.3)."""

from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path

from crfr_redteam import live
from crfr_redteam.harness import Bench, measure
from crfr_redteam.report import markdown, publish

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="crfr_redteam")
    parser.add_argument("command", choices=["report", "promptfoo", "selftest"])
    parser.add_argument("--scenarios", type=Path, default=ROOT / "scenarios" / "indirect.toml")
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    parser.add_argument("--selftest", type=Path, default=ROOT.parent / "evals" / "results" / "redteam-selftest.json")
    parser.add_argument("--out", type=Path, default=ROOT.parent / "evals" / "redteam" / "indirect.yaml")
    args = parser.parse_args(argv)
    bench = Bench.load(args.scenarios)
    if args.command == "report":
        version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
        history = publish(args.results / "asr.json", measure(bench, version))
        (args.results / "asr.md").write_text(markdown(history), encoding="utf-8")
        kit = history[-1]["configurations"]["kit"] if history[-1]["version"] == version else None
        print(f"version {version}: kit ASR {kit['asr']:.0%} over {kit['scenarios']} scenarios" if kit else version)
    elif args.command == "selftest":
        problems = live.check_selftest(json.loads(args.selftest.read_text(encoding="utf-8")), len(bench.scenarios))
        if problems:
            raise SystemExit("self-test of the live assertions failed:\n" + "\n".join(problems))
        print(f"self-test passed: {len(bench.scenarios)} scenarios, obedient agent caught, refusing agent passed")
    else:
        args.out.write_text(live.promptfoo_tests(bench), encoding="utf-8")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
