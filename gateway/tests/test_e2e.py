"""End-to-end tests of the local stack (make up && make e2e). Standard library only.

They prove the acceptance criteria of E2.1 to E2.3 against the running containers:
authentication, group authorisation, model allowlist from the inventory, SigV4 signature for
the EU source Region, and nothing of the client's identity forwarded to Bedrock.
"""

import json
import os
import subprocess
import unittest
import urllib.error
import urllib.parse
import urllib.request

GATEWAY = os.environ.get("CRFR_GATEWAY", f"http://127.0.0.1:{os.environ.get('CRFR_GATEWAY_PORT', '1975')}")
KEYCLOAK = os.environ.get("CRFR_KEYCLOAK", f"http://127.0.0.1:{os.environ.get('CRFR_KEYCLOAK_PORT', '8081')}")
KNOWN_GATEWAY_HEADERS = {
    "x-ai-eg-internal-req-id",
    "x-ai-eg-model",
    "x-ai-eg-original-path",
    "x-request-id",
    "x-forwarded-proto",
    "x-envoy-expected-rq-timeout-ms",
    "x-forwarded-host",  # the gateway's own host name, as called by the client
}
NOT_ROUTABLE = (
    "claude-fable-5-2",
    "claude-mythos-5-2",
    "global.anthropic.claude-sonnet-5",
    "eu.anthropic.claude-sonnet-5",
)
IDENTITY_HEADERS = (
    "x-crfr",
    "x-jwt",
    "cookie",
    "x-forwarded-user",
    "x-user",
    "x-forwarded-for",
    "x-envoy-external-address",
    "x-real-ip",
    "forwarded",
)
COMPOSE = ["docker", "compose", "-f", os.path.join(os.path.dirname(__file__), "..", "compose.yaml")]


def token(user: str, client: str = "demo-app") -> str:
    data = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "client_id": client,
            "client_secret": "local-demo-only-not-a-secret",
            "username": user,
            "password": "local-demo-only",
        }
    ).encode()
    with urllib.request.urlopen(f"{KEYCLOAK}/realms/crfr/protocol/openid-connect/token", data, timeout=20) as r:
        return json.load(r)["access_token"]


def call(model: str, bearer: str | None, text: str = "test", **extra) -> tuple[int, dict]:
    payload = {"model": model, "max_tokens": 32, "messages": [{"role": "user", "content": text}], **extra}
    body = json.dumps(payload).encode()
    headers = {"content-type": "application/json", "anthropic-version": "2023-06-01"}
    if bearer:
        headers["authorization"] = f"Bearer {bearer}"
    request = urllib.request.Request(f"{GATEWAY}/anthropic/v1/messages", body, headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read() or b"{}")
        except ValueError:
            return error.code, {}


def bedrock_log() -> list[dict]:
    out = subprocess.run(
        [*COMPOSE, "exec", "-T", "fake-bedrock", "cat", "/data/requests.jsonl"],
        check=False,
        capture_output=True,
        text=True,
    ).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


class Gateway(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.alice = token("alice")
        cls.mallory = token("mallory")

    def test_rejects_missing_token(self):
        self.assertEqual(call("claude-sonnet-5", None)[0], 401)

    def test_rejects_tampered_token(self):
        self.assertEqual(call("claude-sonnet-5", self.alice[:-4] + "AAAA")[0], 401)

    def test_rejects_user_outside_group(self):
        self.assertEqual(call("claude-sonnet-5", self.mallory)[0], 403)

    def test_models_outside_inventory_are_not_routable(self):
        # The OPA policy refuses them first (403); without it, the gateway has no route for them (404).
        before = len(bedrock_log())
        for model in NOT_ROUTABLE:
            with self.subTest(model=model):
                self.assertIn(call(model, self.alice)[0], (403, 404))
        self.assertEqual(len(bedrock_log()), before, "nothing may reach Bedrock")

    def test_allowed_model_is_signed_for_paris_and_uses_eu_profile(self):
        marker = "canary-e2e-signature"
        status, body = call("claude-sonnet-5", self.alice, marker)
        self.assertEqual(status, 200)
        self.assertEqual(body["model"], "eu.anthropic.claude-sonnet-5")
        entry = next(e for e in reversed(bedrock_log()) if marker in json.dumps(e["body"]))
        self.assertEqual(entry["decision"], "allowed")
        self.assertEqual(entry["region"], "eu-west-3")
        self.assertEqual(entry["auth_scheme"], "AWS4-HMAC-SHA256")
        # No client identity may reach Bedrock. The gateway's own routing headers (x-ai-eg-*,
        # no personal data) are forwarded by Envoy AI Gateway v1.2.1: documented in gateway/README.md.
        identity = [h for h in entry["headers"] if h.startswith(IDENTITY_HEADERS)]
        self.assertEqual(identity, [], "client identity headers leaked to Bedrock")
        unexpected = sorted(
            h
            for h in entry["headers"]
            if h.startswith("x-") and h not in KNOWN_GATEWAY_HEADERS and not h.startswith("x-amz-")
        )
        self.assertEqual(unexpected, [], "new headers reach Bedrock: review them before accepting")
        self.assertEqual(entry["body"]["anthropic_version"], "bedrock-2023-05-31")

    def test_every_request_reaching_bedrock_is_eu(self):
        call("claude-haiku-4-5", self.alice)
        for entry in bedrock_log():
            self.assertTrue(entry["model"].startswith("eu."), entry["model"])
            self.assertEqual(entry["region"], "eu-west-3")


if __name__ == "__main__":
    unittest.main()
