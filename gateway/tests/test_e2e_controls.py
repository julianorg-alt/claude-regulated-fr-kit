"""End-to-end tests of the gateway controls (backlog E2.4 to E2.8), against the running stack.

Quotas, budgets, OPA policy, kill switches, egress and prompt caching. The guard keeps its ledger in
a Docker volume, so the quota and budget tests loop until the limit is hit instead of assuming an
empty ledger. Standard library only.
"""

import json
import os
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
import portcheck  # noqa: E402
from test_e2e import COMPOSE, GATEWAY, KEYCLOAK, bedrock_log, call, token

# Values computed with the published check-digit algorithms; nobody's real identifiers.
VALID_IBAN = "FR76 0000 0012 3412 3456 7890 151"
KILL_SWITCH_TARGET_S = 300  # backlog E2: "coupure effective en moins de 5 minutes"


def compose(*args: str, check: bool = True) -> str:
    result = subprocess.run([*COMPOSE, *args], check=check, capture_output=True, text=True, timeout=120)
    return result.stdout


def admin(*args: str) -> str:
    return compose("exec", "-T", "guard", "python", "-s", "-E", "-m", "crfr_guard.admin", *args)


def decisions() -> list[dict]:
    """Audit lines as the guard prints them (the stream a SIEM collects)."""
    out = compose("logs", "--no-color", "--no-log-prefix", "guard", check=False)
    return [json.loads(line) for line in out.splitlines() if line.startswith("{")]


def reason(body: dict) -> str:
    return body.get("error", {}).get("message", "")


def until_refused(model, bearer, limit=40) -> tuple[int, dict, int]:
    for attempt in range(1, limit + 1):
        status, body = call(model, bearer, "un deux trois quatre cinq")
        if status != 200:
            return status, body, attempt
    raise AssertionError(f"still admitted after {limit} calls")


def wait_for(predicate, timeout_s=KILL_SWITCH_TARGET_S) -> float:
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        if predicate():
            return time.monotonic() - start
        time.sleep(0.2)
    raise AssertionError(f"not effective within {timeout_s} s")


class Policy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.alice, cls.carol = token("alice"), token("carol")

    def test_model_allowed_by_group(self):
        status, body = call("claude-opus-5-5", self.carol)
        self.assertEqual(status, 403)
        self.assertIn("model-not-allowed-for-groups", reason(body))
        self.assertEqual(call("claude-opus-5-5", self.alice)[0], 200, "alice is in claude-power-users")

    def test_identifier_reaches_bedrock_only_as_a_pseudonym(self):
        # The pseudonymisation stage replaces it before the policy's residual check (E2.5 + E3.5).
        status, body = call("claude-sonnet-5", self.alice, f"virement depuis {VALID_IBAN}")
        self.assertEqual(status, 200)
        self.assertNotIn("0000 0012 3412", json.dumps(bedrock_log()))

    def test_size_limits(self):
        status, body = call("claude-sonnet-5", self.alice, max_tokens=100_000)
        self.assertEqual(status, 403)
        self.assertIn("max-tokens-too-high", reason(body))
        status, body = call("claude-sonnet-5", self.alice, "x " * 600_000)
        self.assertIn(status, (403, 413))

    def test_policy_engine_down_fails_closed(self):
        compose("stop", "opa")
        try:
            status, body = call("claude-sonnet-5", self.alice, "opa-down")
            self.assertEqual(status, 503)
            self.assertIn("policy-unavailable", reason(body))
        finally:
            compose("start", "opa")
            wait_for(lambda: call("claude-sonnet-5", self.alice)[0] == 200, 60)


class QuotasAndBudgets(unittest.TestCase):
    def test_user_quota_exceeded_is_refused_and_traced(self):
        status, body, attempts = until_refused("claude-sonnet-5", token("carol"))  # carol: 30 tokens a day
        self.assertEqual(status, 429)
        self.assertEqual(body["error"]["type"], "rate_limit_error")
        self.assertIn("quota-user", reason(body))
        self.assertLessEqual(attempts, 6)
        traced = [d for d in decisions() if d.get("user") == "carol" and d.get("reason") == "quota-user"]
        self.assertTrue(traced, "the refusal must be in the decision log")

    def test_monthly_budget_exceeded_is_refused_and_traced(self):
        status, body, _ = until_refused("claude-sonnet-5", token("alice", client="budget-demo"))
        self.assertEqual(status, 429)
        self.assertIn("budget-app", reason(body))
        self.assertTrue([d for d in decisions() if d.get("app") == "budget-demo" and d.get("reason") == "budget-app"])

    def test_usage_is_charged_to_user_team_and_app(self):
        alice = token("alice")
        before = {s: json.loads(admin("usage", s, k))["tokens_today"] for s, k in
                  (("user", "alice"), ("team", "team-risk"), ("app", "demo-app"))}  # fmt: skip
        status, body = call("claude-haiku-4-5", alice, "compte les jetons")
        self.assertEqual(status, 200)
        spent = sum(body["usage"].values())
        for (scope, key), old in zip(
            (("user", "alice"), ("team", "team-risk"), ("app", "demo-app")), before.values(), strict=True
        ):
            self.assertEqual(json.loads(admin("usage", scope, key))["tokens_today"], old + spent)
        log = json.dumps(decisions())
        self.assertNotIn("compte les jetons", log, "the decision log must not contain prompts")


class PromptCaching(unittest.TestCase):
    def test_cache_control_passes_through_and_usage_comes_back(self):
        alice = token("alice")
        system = [
            {"type": "text", "text": f"contexte long {time.time()} " * 50, "cache_control": {"type": "ephemeral"}}
        ]
        first = call("claude-sonnet-5", alice, "question", system=system)
        second = call("claude-sonnet-5", alice, "autre question", system=system)
        self.assertEqual((first[0], second[0]), (200, 200))
        self.assertGreater(first[1]["usage"]["cache_creation_input_tokens"], 0)
        self.assertGreater(second[1]["usage"]["cache_read_input_tokens"], 0)
        sent = next(e for e in reversed(bedrock_log()) if "autre question" in json.dumps(e["body"]))
        self.assertEqual(sent["body"]["system"], system, "the gateway must forward cache_control unchanged")


class KillSwitch(unittest.TestCase):
    """Exercise E2.6: each level is timed from the command to the first refused call."""

    timings: dict[str, float] = {}

    @classmethod
    def tearDownClass(cls):
        admin("resume")
        compose(
            "exec",
            "-T",
            "guard",
            "python",
            "-s",
            "-E",
            "-m",
            "crfr_guard.admin",
            "restore",
            "app",
            "demo-app",
            check=False,
        )
        compose("exec", "-T", "fake-bedrock", "rm", "-f", "/data/iam-kill-switch", check=False)
        print("\nkill switch drill (seconds from command to refusal):", json.dumps(cls.timings))

    def setUp(self):
        self.alice = token("alice")
        self.assertEqual(call("claude-sonnet-5", self.alice)[0], 200)

    def test_level1_revoked_application_key(self):
        start = time.monotonic()
        admin("revoke", "app", "demo-app", "--reason", "e2e drill")
        try:
            elapsed = wait_for(lambda: call("claude-sonnet-5", self.alice)[0] == 403)
            self.timings["level1_app_key"] = round(time.monotonic() - start, 2)
            self.assertLess(elapsed, KILL_SWITCH_TARGET_S)
            other = token("alice", client="budget-demo")
            self.assertNotEqual(call("claude-sonnet-5", other)[0], 403, "only the revoked key is cut")
        finally:
            admin("restore", "app", "demo-app")

    def test_level2_global_stop(self):
        start = time.monotonic()
        admin("stop", "--reason", "e2e drill")
        try:
            wait_for(lambda: call("claude-sonnet-5", self.alice)[0] == 503)
            self.timings["level2_global"] = round(time.monotonic() - start, 2)
            before = len(bedrock_log())
            status, body = call("claude-sonnet-5", self.alice)
            self.assertEqual(status, 503)
            self.assertIn("kill-switch-global", reason(body))
            self.assertEqual(len(bedrock_log()), before, "nothing reaches Bedrock while stopped")
        finally:
            admin("resume")

    def test_level3_iam_deny(self):
        start = time.monotonic()
        compose("exec", "-T", "fake-bedrock", "touch", "/data/iam-kill-switch")
        try:
            wait_for(lambda: call("claude-sonnet-5", self.alice)[0] >= 400)
            self.timings["level3_iam_simulated"] = round(time.monotonic() - start, 2)
            self.assertEqual(bedrock_log()[-1]["decision"], "iam-kill-switch")
        finally:
            compose("exec", "-T", "fake-bedrock", "rm", "-f", "/data/iam-kill-switch")


class Egress(unittest.TestCase):
    def test_only_gateway_and_keycloak_ports_are_published_on_loopback(self):
        published = set()
        for line in compose("ps", "--format", "json").splitlines():
            service = json.loads(line)
            for port in service.get("Publishers") or []:
                if port.get("PublishedPort"):
                    published.add((service["Service"], port["URL"], port["PublishedPort"]))
        self.assertEqual(
            {(s, p) for s, _, p in published},
            {
                ("aigw", int(os.environ.get("CRFR_GATEWAY_PORT", "1975"))),
                ("keycloak", int(os.environ.get("CRFR_KEYCLOAK_PORT", "8081"))),
            },
        )
        self.assertTrue(all(url in ("127.0.0.1", "") for _, url, _ in published), published)

    def test_backend_services_cannot_reach_the_internet(self):
        probe = (
            "import socket\n"
            "try:\n socket.create_connection(('1.1.1.1', 443), timeout=3); print('OPEN')\n"
            "except OSError: print('BLOCKED')\n"
        )
        for service in ("guard", "fake-bedrock"):
            with self.subTest(service=service):
                out = compose("exec", "-T", service, "python", "-c", probe).strip()
                self.assertEqual(out, "BLOCKED")

    def test_keycloak_admin_interfaces_are_disabled(self):
        for path in ("/admin/master/console/", "/admin/realms/crfr/users"):
            with self.subTest(path=path):
                try:
                    with urllib.request.urlopen(KEYCLOAK + path, timeout=10) as response:
                        status = response.status
                except urllib.error.HTTPError as error:
                    status = error.code
                self.assertIn(status, (401, 403, 404))
                self.assertNotEqual(status, 401, "an admin API that asks for credentials is still exposed")

    def test_gateway_admin_ports_are_not_published_by_the_kit(self):
        # The decision rests on what the kit publishes (docker compose ps), not on a bare TCP connect: a
        # port that another process already held before `make up` is not the kit's doing. The TCP probe
        # counts only where the kit owns the host side, that is when a kit container shares the host network.
        published = portcheck.published_ports(compose("ps", "--format", "json"))
        findings = portcheck.admin_findings(published, portcheck.is_listening, portcheck.uses_host_network())
        self.assertEqual(findings, [], f"the kit exposes administration ports on the host: {findings}")
        foreign = [p for p in portcheck.ADMIN_PORTS if portcheck.is_listening(p)]
        if foreign:
            print(f"note: {foreign} answer on 127.0.0.1 but the kit publishes nothing there (another process)")

    def test_unknown_paths_are_not_proxied(self):
        request = urllib.request.Request(
            GATEWAY + "/v1/proxy?target=http://example.com", headers={"host": "example.com"}
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=10)
        self.assertIn(caught.exception.code, (401, 404))


if __name__ == "__main__":
    unittest.main()
