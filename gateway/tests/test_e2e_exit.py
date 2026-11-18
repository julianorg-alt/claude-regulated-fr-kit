"""End-to-end tests of the exit route (backlog E10.1), against the running stack.

The local stack runs the exit provider in standby: ``exit-<alias>`` aliases reach a fake second provider
(an OpenAI-compatible endpoint inside fake-bedrock). What matters for a regulated deployment: the same
controls apply on that path (pseudonymisation, quotas through prices, policy), the answer comes back in the
Anthropic format whether buffered or streamed, nothing goes to Bedrock, and the client identity is not
forwarded. Standard library only.
"""

import json
import subprocess
import unittest
import urllib.request

from test_e2e import COMPOSE, GATEWAY, IDENTITY_HEADERS, bedrock_log, call, token
from test_e2e_controls import decisions
from test_e2e_pseudo import CANARIES, NEEDLES, PROMPT, streamed_text

EXIT_ALIAS = "exit-claude-sonnet-5"
EXIT_MODEL = "exit-model-fr"


def exit_log() -> list[dict]:
    out = subprocess.run(
        [*COMPOSE, "exec", "-T", "fake-bedrock", "cat", "/data/exit-requests.jsonl"],
        check=False,
        capture_output=True,
        text=True,
    ).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


class ExitRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.alice = token("alice")  # claude-power-users

    def test_exit_alias_reaches_the_second_provider_not_bedrock(self):
        marker = "canari-exit-route"
        before = len(bedrock_log())
        status, body = call(EXIT_ALIAS, self.alice, marker)
        self.assertEqual(status, 200, body)
        self.assertEqual(body["type"], "message")
        self.assertIn(marker, body["content"][0]["text"])
        self.assertEqual(len(bedrock_log()), before, "the exit route must not touch Bedrock")
        entry = next(e for e in reversed(exit_log()) if marker in json.dumps(e["body"]))
        self.assertTrue(entry["authorised"], "the gateway must send the API key of the exit provider")
        self.assertEqual(entry["model"], EXIT_MODEL)

    def test_client_identity_is_not_forwarded_to_the_second_provider(self):
        marker = "canari-exit-headers"
        call(EXIT_ALIAS, self.alice, marker)
        entry = next(e for e in reversed(exit_log()) if marker in json.dumps(e["body"]))
        self.assertEqual([h for h in entry["headers"] if h.startswith(IDENTITY_HEADERS)], [])

    def test_personal_data_is_pseudonymised_before_the_second_provider_and_restored_for_the_client(self):
        request = urllib.request.Request(
            f"{GATEWAY}/anthropic/v1/messages",
            json.dumps({"model": EXIT_ALIAS, "max_tokens": 256, "stream": True,
                        "messages": [{"role": "user", "content": PROMPT}]}).encode(),
            {"content-type": "application/json", "anthropic-version": "2023-06-01",
             "authorization": f"Bearer {self.alice}", "x-crfr-session": "exit-pseudo"},
        )  # fmt: skip
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (local stack)
            text = streamed_text(response.read())
        for label in ("PERSONNE", "EMAIL"):
            self.assertIn(CANARIES[label], text, f"{label} must be restored for the client")
        seen = json.dumps(
            [e for e in exit_log() if "exit-pseudo" in json.dumps(e) or "Bonjour, je suis" in json.dumps(e)]
        )
        for needle in NEEDLES:
            self.assertNotIn(needle, seen, f"{needle!r} reached the second provider in clear text")

    def test_streamed_exit_answers_are_counted_against_quotas_and_budgets(self):
        """The guard reads usage from the translated stream: a zero here would let streams escape the limits."""
        request = urllib.request.Request(
            f"{GATEWAY}/anthropic/v1/messages",
            json.dumps({"model": EXIT_ALIAS, "max_tokens": 64, "stream": True,
                        "messages": [{"role": "user", "content": "un deux trois quatre cinq six"}]}).encode(),
            {"content-type": "application/json", "anthropic-version": "2023-06-01",
             "authorization": f"Bearer {self.alice}"},
        )  # fmt: skip
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (local stack)
            response.read()
        last = [d for d in decisions() if d.get("event") == "response" and d.get("model") == EXIT_ALIAS][-1]
        self.assertGreater(last["usage"]["output_tokens"], 0)
        self.assertGreater(last["cost"], 0)

    def test_standard_users_cannot_use_exit_aliases(self):
        self.assertEqual(call(EXIT_ALIAS, token("carol"))[0], 403)

    def test_primary_aliases_still_go_to_bedrock(self):
        before = len(exit_log())
        self.assertEqual(call("claude-sonnet-5", self.alice, "toujours bedrock")[0], 200)
        self.assertEqual(len(exit_log()), before)


if __name__ == "__main__":
    unittest.main()
