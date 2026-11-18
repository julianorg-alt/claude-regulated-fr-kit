"""python -m crfr_agents pin | check | verify-log (backlog E8)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from crfr_agents import calllog, rule_of_two
from crfr_agents.registry import Registry, pin

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="crfr_agents")
    sub = parser.add_subparsers(dest="command", required=True)
    p_pin = sub.add_parser("pin", help="TOML block for the tools of a tools/list result (JSON file)")
    p_pin.add_argument("server")
    p_pin.add_argument("tools_json", type=Path)
    p_check = sub.add_parser("check", help="registry loads and every Rule of Two sheet is consistent")
    p_check.add_argument("--registry", type=Path, default=ROOT / "registry" / "servers.toml")
    p_check.add_argument("--workflows", type=Path, default=ROOT / "workflows")
    p_log = sub.add_parser("verify-log", help="check the MAC chain of a call log (key in CRFR_MCP_LOG_KEY, hex)")
    p_log.add_argument("log", type=Path)
    args = parser.parse_args(argv)
    if args.command == "pin":
        doc = json.loads(args.tools_json.read_text(encoding="utf-8"))
        tools = doc.get("result", doc).get("tools", doc) if isinstance(doc, dict) else doc
        print(pin(args.server, tools))
        return 0
    if args.command == "check":
        registry = Registry.load(args.registry)
        problems = rule_of_two.check(rule_of_two.load(args.workflows), registry)
        for problem in problems:
            print(problem, file=sys.stderr)
        print(f"{len(registry.servers)} server(s), {len(problems)} problem(s) in the Rule of Two sheets")
        return 1 if problems else 0
    problems = calllog.verify(args.log, bytes.fromhex(os.environ["CRFR_MCP_LOG_KEY"]))
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"{args.log}: {'intact' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
