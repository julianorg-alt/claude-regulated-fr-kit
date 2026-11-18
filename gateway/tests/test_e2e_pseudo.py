"""End-to-end tests of the pseudonymisation stage (backlog E3.5), against the running stack.

Canary values (synthetic, valid check digits) are sent through the gateway. They must come back to
the client, buffered and streamed, and must appear nowhere else: not in what reached Bedrock, not in
the audit trail (local segments, content log, Object Lock store), not in any container log.
"""

import json
import os
import subprocess
import unittest
import urllib.request

from test_e2e import COMPOSE, GATEWAY, bedrock_log, token
from test_e2e_audit import stored_audit_objects
from test_e2e_controls import compose

NIR = "2" + "991299" + "123456"
NIR += f"{97 - int(NIR) % 97:02d}"
CANARIES = {
    "NIR": f"{NIR[0]} {NIR[1:3]} {NIR[3:5]} {NIR[5:7]} {NIR[7:10]} {NIR[10:13]} {NIR[13:]}",
    "IBAN": "FR76 0000 0012 3412 3456 7890 151",
    "EMAIL": "canari.zx81@example.org",
    "TELEPHONE": "06 99 88 77 66",
    "PERSONNE": "Monsieur Hippolyte Zebrowskiquin",
}
PROMPT = (
    f"Bonjour, je suis {CANARIES['PERSONNE']}. Mon numéro de sécurité sociale est {CANARIES['NIR']}, "
    f"mon IBAN {CANARIES['IBAN']}, mon courriel {CANARIES['EMAIL']} et mon téléphone {CANARIES['TELEPHONE']}."
)
NEEDLES = ("Zebrowskiquin", NIR[7:13], CANARIES["NIR"][-9:], "0112 3456", "canari.zx81", "99 88 77")


def post(bearer: str, session: str, stream: bool) -> tuple[str, bytes]:
    payload = {
        "model": "claude-sonnet-5",
        "max_tokens": 256,
        "stream": stream,
        "messages": [{"role": "user", "content": PROMPT}],
    }
    request = urllib.request.Request(
        f"{GATEWAY}/anthropic/v1/messages",
        json.dumps(payload).encode(),
        {"content-type": "application/json", "anthropic-version": "2023-06-01", "authorization": f"Bearer {bearer}",
         "x-crfr-session": session},
    )  # fmt: skip
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.headers.get("content-type", ""), response.read()


def streamed_text(raw: bytes) -> str:
    text = ""
    for line in raw.decode().splitlines():
        if line.startswith("data:"):
            event = json.loads(line[5:])
            if event.get("type") == "content_block_delta":
                text += event["delta"].get("text", "")
    return text


class Pseudonymisation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.alice = token("alice")

    def assert_bedrock_saw_pseudonyms_only(self, marker: str):
        entry = next(e for e in reversed(bedrock_log()) if marker in json.dumps(e["body"]))
        sent = json.dumps(entry["body"], ensure_ascii=False)
        for needle in NEEDLES:
            self.assertNotIn(needle, sent)
        return sent

    def test_buffered_answer_gets_the_originals_back(self):
        content_type, raw = post(self.alice, "e2e-buffered", stream=False)
        answer = json.loads(raw)["content"][0]["text"]
        for value in CANARIES.values():
            self.assertIn(value, answer)  # the fake Bedrock echoes the prompt it received
        sent = self.assert_bedrock_saw_pseudonyms_only("<NIR_1>")
        for kind in ("PERSONNE", "NIR", "IBAN", "EMAIL", "TELEPHONE"):
            self.assertIn(f"<{kind}_1>", sent)

    def test_streamed_answer_gets_the_originals_back(self):
        content_type, raw = post(self.alice, "e2e-stream", stream=True)
        self.assertIn("text/event-stream", content_type)
        text = streamed_text(raw)
        for value in CANARIES.values():
            self.assertIn(value, text)
        self.assertNotIn("<NIR_", text, "split pseudonyms must be restored too")
        self.assert_bedrock_saw_pseudonyms_only("<NIR_1>")

    def test_no_canary_anywhere_else(self):
        post(self.alice, "e2e-leak", stream=False)
        post(self.alice, "e2e-leak", stream=True)
        logs = subprocess.run([*COMPOSE, "logs", "--no-color"], capture_output=True, text=True, timeout=60).stdout
        content = compose("exec", "-T", "guard", "sh", "-c", "cat /data/content/*.jsonl", check=False)
        stored = stored_audit_objects()
        ledger = compose(
            "exec", "-T", "guard", "python", "-c", "print(open('/data/guard.sqlite','rb').read())", check=False
        )
        bedrock = json.dumps(bedrock_log(), ensure_ascii=False)
        for name, haystack in (
            ("container logs", logs),
            ("content log", content),
            ("audit store", stored),
            ("ledger", ledger),
            ("Bedrock", bedrock),
        ):
            for needle in NEEDLES:
                with self.subTest(where=name, needle=needle):
                    self.assertNotIn(needle, haystack)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    unittest.main()
