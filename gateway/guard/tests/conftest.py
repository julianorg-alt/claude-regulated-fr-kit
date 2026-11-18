import base64
import json

import pytest

from crfr_guard import config as config_module
from crfr_guard.audit import AuditLog, LocalMac
from crfr_guard.engine import Guard
from crfr_guard.ledger import Ledger
from crfr_guard.policy import PolicyDecision

RAW_CONFIG = {
    "identity": {"user_claim": "preferred_username", "app_claim": "azp", "team_prefix": "team-"},
    "quotas": {
        "daily_tokens": {"default": {"user": 100, "team": None, "app": 1000}, "overrides": {"user": {"vip": 5000}}}
    },
    "budgets": {"currency": "EUR", "monthly": {"default": {"app": 1.0}, "overrides": {"app": {"tiny": 0.0}}}},
    "prices": {
        "claude-sonnet-5": {
            "input_tokens": 3.0,
            "output_tokens": 15.0,
            "cache_read_input_tokens": 0.3,
            "cache_creation_input_tokens": 3.75,
        }
    },
    "opa": {"url": "http://opa:8181/v1/data/crfr/gateway/decision"},
}


def jwt(**claims) -> str:
    def part(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256'})}.{part(claims)}.c2ln"


def bearer(user="alice", app="demo-app", groups=("claude-users", "team-risk")) -> dict:
    return {"authorization": "Bearer " + jwt(preferred_username=user, azp=app, groups=list(groups))}


class FakeOpa:
    def __init__(self):
        self.inputs = []
        self.decision = PolicyDecision(True, ())
        self.error = None

    def decide(self, policy_input):
        self.inputs.append(policy_input)
        if self.error:
            raise self.error
        return self.decision


class Clock:
    def __init__(self, now=1_790_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def guard(tmp_path, clock):
    cfg = config_module.parse(RAW_CONFIG)
    audit = AuditLog(tmp_path / "audit", LocalMac(b"k" * 32), stream=None)
    return Guard(cfg, Ledger(tmp_path / "g.sqlite", clock=clock), FakeOpa(), audit)


def body(model="claude-sonnet-5", text="bonjour", **extra) -> bytes:
    return json.dumps(
        {"model": model, "max_tokens": 64, "messages": [{"role": "user", "content": text}], **extra}
    ).encode()
