"""Record `make demo` as an asciicast v2 file (docs/demo/demo.cast), from the real output and real timings.

Play it with `asciinema play docs/demo/demo.cast` or on https://asciinema.org/ (not uploaded by this script).
Run from the repository root with the stack stopped: python3 -I scripts/record_demo.py
"""

import json
import os
import subprocess
import time
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "demo" / "demo.cast"
COMMAND = ["make", "demo", "UP_FLAGS="]


def main() -> None:
    subprocess.run(["make", "down"], check=True, capture_output=True)
    env = {**os.environ, "COLUMNS": "100", "NO_COLOR": "1", "TERM": "dumb"}
    start = time.monotonic()
    events = [[0.0, "o", "$ make demo\r\n"]]
    proc = subprocess.Popen(COMMAND, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True)  # noqa: S603
    for line in proc.stdout:
        events.append([round(time.monotonic() - start, 3), "o", line.rstrip("\n") + "\r\n"])
    code = proc.wait()
    header = {"version": 2, "width": 100, "height": 30, "timestamp": int(time.time()),
              "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"}, "title": "claude-regulated-fr: make demo"}  # fmt: skip
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join([json.dumps(header), *(json.dumps(e, ensure_ascii=False) for e in events)]) + "\n")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
