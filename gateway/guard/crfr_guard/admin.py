"""Operator commands, run inside the guard container (never exposed on the network, E2.7).

python -m crfr_guard.admin stop --reason "incident 42"          # level 2: every call gets 503
python -m crfr_guard.admin resume
python -m crfr_guard.admin revoke app demo-app --reason leaked  # level 1: one key gets 403
python -m crfr_guard.admin restore app demo-app
python -m crfr_guard.admin status
python -m crfr_guard.admin usage user alice
python -m crfr_guard.admin verify-audit /data/audit/audit-*.jsonl   # MAC chain (key in CRFR_AUDIT_KEY)
python -m crfr_guard.admin fingerprint request.json                 # prompt_hmac of a request body
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .audit import LocalMac, fingerprint, key_from_env, verify
from .ledger import Ledger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="crfr guard administration")
    parser.add_argument("--state", type=Path, default=Path(os.environ.get("GUARD_STATE", "/data/guard.sqlite")))
    sub = parser.add_subparsers(dest="command", required=True)
    stop = sub.add_parser("stop", help="global kill switch: refuse every call with 503")
    stop.add_argument("--reason", required=True)
    sub.add_parser("resume", help="lift the global kill switch")
    for name in ("revoke", "restore"):
        cmd = sub.add_parser(name, help=f"{name} one user, team or application")
        cmd.add_argument("scope", choices=("user", "team", "app"))
        cmd.add_argument("key")
        if name == "revoke":
            cmd.add_argument("--reason", required=True)
    sub.add_parser("status", help="list active kill switches")
    use = sub.add_parser("usage", help="tokens today and cost this month")
    use.add_argument("scope", choices=("user", "team", "app"))
    use.add_argument("key")
    check = sub.add_parser("verify-audit", help="check the MAC chain of audit segments, in time order")
    check.add_argument("files", nargs="+", type=Path)
    check.add_argument("--prev", help="MAC of the line before the first one (chain across shipped segments)")
    mark = sub.add_parser("fingerprint", help="prompt_hmac of a request body, to find its audit line")
    mark.add_argument("body", type=Path)
    args = parser.parse_args(argv)

    if args.command in ("verify-audit", "fingerprint"):
        key = key_from_env()
        if key is None:
            print("CRFR_AUDIT_KEY is not set")
            return 2
        mac = LocalMac(key)
        if args.command == "fingerprint":
            print(fingerprint(mac, args.body.read_bytes()))
            return 0
        lines = [line for f in sorted(args.files) for line in f.read_text(encoding="utf-8").splitlines() if line]
        ok, count, error = verify(lines, mac, args.prev)
        print(json.dumps({"ok": ok, "lines": count, "error": error}))
        return 0 if ok else 1

    ledger = Ledger(args.state)
    if args.command == "stop":
        ledger.set_switch("global", "*", args.reason)
    elif args.command == "resume":
        ledger.clear_switch("global", "*")
    elif args.command == "revoke":
        ledger.set_switch(args.scope, args.key, args.reason)
    elif args.command == "restore":
        if not ledger.clear_switch(args.scope, args.key):
            print(f"no switch on {args.scope} {args.key}")
            return 1
    elif args.command == "status":
        for scope, key, reason, ts in ledger.switches():
            print(json.dumps({"scope": scope, "key": key, "reason": reason, "since": ts}))
    elif args.command == "usage":
        print(json.dumps({"tokens_today": ledger.tokens_today(args.scope, args.key),
                          "cost_this_month": round(ledger.cost_this_month(args.scope, args.key), 6)}))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
