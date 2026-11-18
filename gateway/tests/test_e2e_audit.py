"""End-to-end tests of the audit trail (backlog E5), against the running stack.

The guard writes one line per decision, with an HMAC fingerprint of the request body and a MAC chain; the
shipper copies closed segments to the S3-compatible store (RustFS locally) under Object Lock in compliance
mode. Standard library only: the MAC is recomputed here independently of the guard's code.
"""

import hashlib
import hmac
import json
import re
import time
import unittest
import urllib.request

from test_e2e import GATEWAY, token
from test_e2e_controls import compose

# Local demo key, as set in compose.yaml for the guard (never a real key).
AUDIT_KEY = bytes.fromhex("6c6f63616c2d64656d6f2d6f6e6c792d6c6f63616c2d64656d6f2d6f6e6c7921")
SHIPPED = re.compile(r"shipped (audit/\S+\.jsonl)")


def shipper(*args: str, check: bool = False) -> str:
    return compose("exec", "-T", "audit-shipper", "python", "-s", "-E", "-m", "crfr_guard.shipper", *args, check=check)


def shipped_keys() -> list[str]:
    return SHIPPED.findall(compose("logs", "--no-color", "audit-shipper", check=False))


def stored_audit_objects() -> str:
    return "\n".join(shipper("--get", key) for key in shipped_keys())


def line_mac(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "mac"}
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(AUDIT_KEY, hashlib.sha256(canonical).digest(), hashlib.sha256).hexdigest()


def send(raw: bytes, bearer: str) -> None:
    request = urllib.request.Request(
        f"{GATEWAY}/anthropic/v1/messages", raw,
        {"content-type": "application/json", "anthropic-version": "2023-06-01", "authorization": f"Bearer {bearer}"},
    )  # fmt: skip
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()


class AuditTrail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.dumps(
            {"model": "claude-sonnet-5", "max_tokens": 32,
             "messages": [{"role": "user", "content": f"audit e2e {time.time_ns()}"}]}
        ).encode()  # fmt: skip
        cls.fingerprint = hmac.new(AUDIT_KEY, hashlib.sha256(cls.raw).digest(), hashlib.sha256).hexdigest()
        send(cls.raw, token("alice"))
        cls.stored = cls.wait_for_line(cls.fingerprint)

    @staticmethod
    def wait_for_line(fingerprint: str, timeout_s: float = 60) -> tuple[str, list[dict]]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for key in shipped_keys():
                text = shipper("--get", key)
                if fingerprint in text:
                    return key, [json.loads(line) for line in text.splitlines() if line.strip()]
            time.sleep(2)
        raise AssertionError("audit line not found in the store within the time limit")

    def test_request_line_holds_the_fingerprint_and_no_content(self):
        _, entries = self.stored
        (line,) = [e for e in entries if e.get("prompt_hmac") == self.fingerprint]
        self.assertEqual((line["event"], line["user"], line["decision"]), ("request", "alice", "admitted"))
        self.assertNotIn("audit e2e", json.dumps(entries))

    def test_stored_segment_verifies(self):
        _, entries = self.stored
        for previous, entry in zip(entries, entries[1:], strict=False):
            self.assertEqual(entry["prev"], previous["mac"], "chain broken")
        for entry in entries:
            self.assertEqual(entry["mac"], line_mac(entry), "line edited or wrong key")

    def test_stored_segment_cannot_be_deleted(self):
        key, _ = self.stored
        result = json.loads(shipper("--try-delete", key, check=True))
        self.assertTrue(result["version"], result)
        self.assertGreaterEqual(result["delete"], 400, result)
        self.assertEqual(result["head_after"], 200, result)

    def test_segments_leave_the_guard_once_stored(self):
        local = compose("exec", "-T", "guard", "ls", "/data/audit", check=False).split()
        self.assertNotIn(self.stored[0].rsplit("/", 1)[1], local)

    def test_siem_receives_a_genai_span_without_content(self):
        _, entries = self.stored
        (line,) = [e for e in entries if e.get("prompt_hmac") == self.fingerprint]
        deadline, spans = time.monotonic() + 30, ""
        while time.monotonic() < deadline and line["request_id"] not in spans:
            time.sleep(1)
            spans = compose("logs", "--no-color", "otel-collector", check=False)
        self.assertIn(f"crfr.request_id: Str({line['request_id']})", spans)
        expected = (
            "gen_ai.operation.name: Str(chat)",
            "gen_ai.provider.name: Str(aws.bedrock)",
            "gen_ai.request.model: Str(claude-sonnet-5)",
            "gen_ai.usage.output_tokens: Int(",
        )
        for attribute in expected:
            self.assertIn(attribute, spans)
        self.assertNotIn("audit e2e", spans)


if __name__ == "__main__":
    unittest.main()
