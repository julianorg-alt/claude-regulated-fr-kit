"""Pick SIREN numbers with a valid Luhn key that the public company search does not know.

Method (recorded in docs/sources/verifications.md): for each candidate, ask
https://recherche-entreprises.api.gouv.fr/search?q=<siren> (no key). A candidate is kept only when the API answers
HTTP 200 with ``total_results`` equal to 0. The accepted list is written to ``datasets/reserved-siren.json`` and is
the only source of SIREN values for ``datasets/generate.py``.

    python3 datasets/verify_siren.py --seed 1 --count 40 --out datasets/reserved-siren.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import random
import string
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://recherche-entreprises.api.gouv.fr/search"


def luhn_valid(number: str) -> bool:
    total = 0
    for i, c in enumerate(reversed(number)):
        x = int(c) * (2 if i % 2 else 1)
        total += x - 9 if x > 9 else x
    return total % 10 == 0


def candidate(r: random.Random) -> str:
    while True:
        value = r.choice("123456789") + "".join(r.choice(string.digits) for _ in range(8))
        if luhn_valid(value):
            return value


def total_results(siren: str, retries: int = 4) -> int:
    url = f"{API}?{urllib.parse.urlencode({'q': siren, 'per_page': 1})}"
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return int(json.load(response)["total_results"])
        except Exception as error:  # network or 429: wait and retry
            print(f"retry {siren}: {error}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    raise SystemExit(f"API unreachable for {siren}: stop, leave an open question")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    r = random.Random(args.seed)
    kept, tried, assigned = [], 0, 0
    while len(kept) < args.count:
        value = candidate(r)
        tried += 1
        if total_results(value) == 0:
            kept.append(value)
        else:
            assigned += 1
        time.sleep(0.2)
    record = {"method": "recherche-entreprises.api.gouv.fr /search?q=<siren>, total_results == 0",
              "checked_on": datetime.date.today().isoformat(), "seed": args.seed,
              "candidates_tried": tried, "candidates_found_assigned": assigned, "siren": sorted(kept)}
    args.out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"kept {len(kept)} of {tried}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
