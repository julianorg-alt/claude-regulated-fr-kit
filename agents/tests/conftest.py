"""Shared fixtures of the MCP governance tests: an authorization server key, the proxy, the demo server."""

import os
import time
from dataclasses import replace
from pathlib import Path

import jwt
import pytest
from crfr_agents import rule_of_two
from crfr_agents.approval import ActionPolicy, ApprovalGate
from crfr_agents.calllog import CallLog
from crfr_agents.demo import DemoServer
from crfr_agents.proxy import McpProxy
from crfr_agents.registry import Registry
from crfr_agents.tokens import TokenMinter, TokenVerifier
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
ISSUER = "https://auth.regionale.example/realms/agents"
PROXY = "https://mcp-proxy.regionale.example/mcp"
DEMO_URL = "https://mcp-dossiers.regionale.example/mcp"


class Env:
    def __init__(self, tmp_path: Path):
        self.as_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.registry = Registry.load(ROOT / "registry" / "servers.toml")
        self.workflows = rule_of_two.load(ROOT / "workflows")
        self.minter = TokenMinter(issuer=PROXY)
        self.demo = DemoServer(url=DEMO_URL, issuer=PROXY, public_key=self.minter.public_key())
        self.log_key = os.urandom(32)
        self.log_path = tmp_path / "calls.jsonl"
        self.gate = ApprovalGate(ActionPolicy.from_dict(self.registry.tool_policy()), key=os.urandom(32))
        self.proxy = McpProxy(
            resource=PROXY, authorization_servers=[ISSUER], registry=self.registry, workflows=self.workflows,
            verifier=TokenVerifier(issuer=ISSUER, audience=PROXY, key_for=lambda _: self.as_key.public_key()),
            minter=self.minter, gate=self.gate, log=CallLog(self.log_path, self.log_key), send=self.demo,
        )  # fmt: skip

    def token(self, agent="agent-synthese", audience=PROXY, issuer=ISSUER, ttl=300, key=None) -> str:
        now = int(time.time())
        claims = {"iss": issuer, "sub": "user-123", "azp": agent, "aud": audience, "iat": now, "exp": now + ttl}
        return jwt.encode(claims, key or self.as_key, algorithm="RS256")

    def send(self, method, params=None, *, server="dossiers", token=None, approval=None, agent="agent-synthese"):
        headers = {"Authorization": f"Bearer {token or self.token(agent=agent)}"}
        if approval:
            headers["X-Crfr-Approval"] = approval
        message = {"jsonrpc": "2.0", "id": 1, "method": method, **({"params": params} if params else {})}
        return self.proxy.handle(server, headers, message)

    def call(self, name, arguments, **kw):
        return self.send("tools/call", {"name": name, "arguments": arguments}, **kw)

    def with_workflow(self, agent, **changes):
        self.workflows[agent] = replace(self.workflows[agent], **changes)


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)
