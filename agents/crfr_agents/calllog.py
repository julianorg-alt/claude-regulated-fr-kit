"""Log of MCP tool calls, arguments and results included (backlog E8.2).

Claude's own logging of MCP traffic is not established (backlog E8.2), so the proxy keeps its own
record. One JSON line per event, chained: each line carries the MAC of the previous one and its own
HMAC-SHA256, so that an edited, removed or reordered line is detected by `verify`. Fields that the
registry marks as sensitive are replaced by their SHA-256: the log proves what was sent without
holding it in clear. The file is opened in append mode with permissions 0600.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from pathlib import Path

from crfr_agents.approval import MIN_KEY_BYTES, canonical

GENESIS = "0" * 64


def redact(value, sensitive: tuple[str, ...]):
    """Copy of value where every dict key listed in `sensitive` holds {"sha256": digest} instead."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            out[k] = {"sha256": hashlib.sha256(canonical(v)).hexdigest()} if k in sensitive else redact(v, sensitive)
        return out
    if isinstance(value, list):
        return [redact(v, sensitive) for v in value]
    return value


class CallLog:
    def __init__(self, path: Path, key: bytes):
        if len(key) < MIN_KEY_BYTES:
            raise ValueError(f"log key must be at least {MIN_KEY_BYTES} bytes")
        self.path, self._key = path, key
        self._lock = threading.Lock()
        self._prev = GENESIS
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
            if lines:
                self._prev = json.loads(lines[-1])["mac"]

    def write(self, **event) -> dict:
        with self._lock:
            line = {"ts": round(time.time(), 3), **event, "prev": self._prev}
            line["mac"] = hmac.new(self._key, canonical(line), hashlib.sha256).hexdigest()
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")
            self._prev = line["mac"]
            return line


def verify(path: Path, key: bytes) -> list[str]:
    """Problems in the chain (empty list: intact)."""
    problems, prev = [], GENESIS
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            line = json.loads(raw)
        except ValueError:
            problems.append(f"line {number}: not JSON")
            continue
        mac = line.pop("mac", None)
        if line.get("prev") != prev:
            problems.append(f"line {number}: chain broken")
        expected = hmac.new(key, canonical(line), hashlib.sha256).hexdigest()
        if not isinstance(mac, str) or not hmac.compare_digest(mac, expected):
            problems.append(f"line {number}: MAC does not match")
        prev = mac or ""
    return problems
