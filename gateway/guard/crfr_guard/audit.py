"""Audit trail of the gateway (backlog E5.1): three flows, kept apart.

1. Audit log: one JSON line per decision, without prompt, answer or client address. Each line carries an
   HMAC fingerprint of the request body, so that a body produced later can be matched to its line, and a MAC
   chain (``prev``, ``mac``), so that an edited, removed or reordered line is detected. Lines go to time
   segments that the shipper copies to Object Lock storage.
2. Content log: optional, the pseudonymised request and answer as Bedrock saw them, kept a few days.
3. Pseudonym mappings: only in the encrypted vault, never in either log.

The MAC key never leaves its holder: ``LocalMac`` keeps it in memory (local stack), ``KmsMac`` asks an AWS KMS
HMAC key (``GenerateMac``) and only ever sends a 32-byte digest.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

HEAD = ".head"


class LocalMac:
    key_id = "local"

    def __init__(self, key: bytes):
        if len(key) < 32:
            raise ValueError("audit MAC key must be at least 32 bytes")
        self._key = key

    def mac(self, digest: bytes) -> str:
        return hmac.new(self._key, digest, hashlib.sha256).hexdigest()


class KmsMac:
    """HMAC computed by an AWS KMS key of spec HMAC_256; ``client`` is a boto3 KMS client or compatible."""

    def __init__(self, client, key_id: str):
        self.client, self.key_id = client, key_id

    def mac(self, digest: bytes) -> str:
        answer = self.client.generate_mac(KeyId=self.key_id, Message=digest, MacAlgorithm="HMAC_SHA_256")
        return bytes(answer["Mac"]).hex()


def key_from_env(name: str = "CRFR_AUDIT_KEY") -> bytes | None:
    value = os.environ.get(name)
    return bytes.fromhex(value) if value else None


def fingerprint(mac, body: bytes) -> str:
    """HMAC of the SHA-256 of a body: proves a given body was sent, reveals nothing without the key."""
    return mac.mac(hashlib.sha256(body).digest())


def _canonical(entry: dict) -> bytes:
    return json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _line_mac(mac, entry: dict) -> str:
    return mac.mac(hashlib.sha256(_canonical({k: v for k, v in entry.items() if k != "mac"})).digest())


def _segment_name(prefix: str, start: float) -> str:
    return f"{prefix}-{datetime.fromtimestamp(start, UTC):%Y%m%dT%H%M%SZ}.jsonl"


class AuditLog:
    def __init__(self, directory: Path | None, mac, segment_s: int = 300, stream=sys.stdout, clock=time.time):
        if segment_s < 1:
            raise ValueError("segment_s must be positive")
        self.directory, self.mac, self.segment_s, self.stream, self.clock = directory, mac, segment_s, stream, clock
        self._lock = threading.Lock()
        self._prev = ""
        if directory:
            directory.mkdir(parents=True, exist_ok=True)
            head = directory / HEAD
            if head.exists():
                self._prev = head.read_text(encoding="utf-8").strip()

    def write(self, **entry) -> dict:
        with self._lock:
            now = self.clock()
            entry = {"ts": round(now, 3), **{k: v for k, v in entry.items() if v is not None}, "prev": self._prev}
            entry["mac"] = _line_mac(self.mac, entry)
            line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
            if self.directory:
                start = now - now % self.segment_s
                with (self.directory / _segment_name("audit", start)).open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
                tmp = self.directory / (HEAD + ".tmp")
                tmp.write_text(entry["mac"], encoding="utf-8")
                os.replace(tmp, self.directory / HEAD)
            self._prev = entry["mac"]
            if self.stream:
                print(line, file=self.stream, flush=True)
        return entry


def read_segments(directory: Path, prefix: str = "audit") -> list[str]:
    lines: list[str] = []
    for path in sorted(directory.glob(f"{prefix}-*.jsonl")):
        lines += [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return lines


def verify(lines: Iterable[str], mac, prev: str | None = None) -> tuple[bool, int, str | None]:
    """Check the MAC of every line and the links between them. ``prev`` defaults to the first line's."""
    count = 0
    for number, line in enumerate(lines, 1):
        try:
            entry = json.loads(line)
        except ValueError:
            return False, count, f"line {number}: not JSON"
        if prev is not None and entry.get("prev") != prev:
            return False, count, f"line {number}: chain broken (line missing, added or moved)"
        if not hmac.compare_digest(str(entry.get("mac", "")), _line_mac(mac, entry)):
            return False, count, f"line {number}: MAC mismatch (line edited or wrong key)"
        prev, count = entry["mac"], count + 1
    return True, count, None


class ContentLog:
    """Pseudonymised request and answer of each call, in daily files deleted after ``retention_days``."""

    def __init__(self, directory: Path, retention_days: int, clock=time.time):
        if not 1 <= retention_days <= 30:
            raise ValueError("content retention must be between 1 and 30 days")
        self.directory, self.retention_days, self.clock = directory, retention_days, clock
        self._lock = threading.Lock()
        directory.mkdir(parents=True, exist_ok=True)

    def write(self, request_id: str | None, request: bytes, response: bytes) -> None:
        now = self.clock()
        entry = {
            "ts": round(now, 3),
            "request_id": request_id,
            "request": request.decode("utf-8", "replace"),
            "response": response.decode("utf-8", "replace"),
        }
        with self._lock:
            self.purge(now)
            name = _segment_name("content", now - now % 86400)
            with (self.directory / name).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

    def purge(self, now: float) -> None:
        cutoff = now - now % 86400 - (self.retention_days - 1) * 86400
        for path in self.directory.glob("content-*.jsonl"):
            stamp = datetime.strptime(path.name[len("content-") : -len(".jsonl")], "%Y%m%dT%H%M%SZ")
            if stamp.replace(tzinfo=UTC).timestamp() < cutoff:
                path.unlink(missing_ok=True)
