"""Human approval of irreversible agent actions (backlog E7.4).

An agent may run a read or a reversible tool on its own. A tool whose effect is irreversible (payment,
outgoing message, deletion, filing) runs only with an approval issued by a named person after they saw
the exact call. The approval is a token signed with a key the agent never holds, bound to the agent,
the tool and a SHA-256 digest of the arguments, valid for a short time and usable once. A tool missing
from the policy is treated as irreversible: a new tool fails closed until someone classifies it.

The gate is meant to run where tool calls execute (the MCP proxy of E8.2), not in the model: a prompt
injection that convinces the model still cannot produce a valid approval.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field

EFFECTS = ("read", "write", "irreversible")
MIN_KEY_BYTES = 32
MAX_TTL_S = 3600


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def arguments_digest(arguments: dict) -> str:
    return hashlib.sha256(canonical(arguments)).hexdigest()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass(frozen=True)
class ToolCall:
    agent: str
    tool: str
    arguments: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class Pending:
    """What the approver sees before signing: who asks, which tool, the exact arguments."""

    agent: str
    tool: str
    digest: str
    summary: str


@dataclass(frozen=True)
class ActionPolicy:
    effects: dict[str, str]

    @classmethod
    def from_dict(cls, data: dict) -> ActionPolicy:
        effects = {}
        for name, spec in (data.get("tools") or {}).items():
            effect = spec.get("effect")
            if effect not in EFFECTS:
                raise ValueError(f"tool {name}: effect must be one of {EFFECTS}, got {effect!r}")
            effects[name] = effect
        return cls(effects)

    def effect(self, tool: str) -> str:
        return self.effects.get(tool, "irreversible")


class ApprovalGate:
    def __init__(self, policy: ActionPolicy, key: bytes, clock: Callable[[], float] = time.time):
        if len(key) < MIN_KEY_BYTES:
            raise ValueError(f"approval key must be at least {MIN_KEY_BYTES} bytes")
        self.policy = policy
        self._key = key
        self._clock = clock
        self._used: dict[str, float] = {}  # nonce -> expiry, kept until the token would expire anyway

    def request(self, call: ToolCall) -> Pending:
        summary = json.dumps(call.arguments, sort_keys=True, ensure_ascii=False, indent=1)
        return Pending(call.agent, call.tool, arguments_digest(call.arguments), summary)

    def approve(self, call: ToolCall, approver: str, ttl_s: int) -> str:
        """Token for one run of this exact call. Called by the approval service after human review."""
        if not approver:
            raise ValueError("an approver is required")
        if approver == call.agent:
            raise ValueError("self-approval: the agent cannot approve its own action")
        if not 0 < ttl_s <= MAX_TTL_S:
            raise ValueError(f"ttl must be between 1 and {MAX_TTL_S} seconds")
        claims = {
            "agent": call.agent,
            "tool": call.tool,
            "digest": arguments_digest(call.arguments),
            "approver": approver,
            "exp": self._clock() + ttl_s,
            "nonce": secrets.token_urlsafe(16),
        }
        payload = _b64(canonical(claims))
        return payload + "." + _b64(self._sign(payload))

    def check(self, call: ToolCall, token: str | None = None, *, every_call: bool = False) -> Decision:
        """`every_call` asks for an approval whatever the effect (Rule of Two workflow holding A, B, C)."""
        if not every_call and self.policy.effect(call.tool) != "irreversible":
            return Decision(True, "not-irreversible")
        if not token:
            return Decision(False, "approval-required")
        claims = self._verify(token)
        if claims is None:
            return Decision(False, "approval-invalid")
        now = self._clock()
        if not isinstance(claims.get("exp"), int | float) or claims["exp"] <= now:
            return Decision(False, "approval-expired")
        bound = (claims.get("agent"), claims.get("tool"), claims.get("digest"))
        if bound != (call.agent, call.tool, arguments_digest(call.arguments)):
            return Decision(False, "approval-mismatch")
        self._used = {n: exp for n, exp in self._used.items() if exp > now}
        nonce = claims.get("nonce")
        if not isinstance(nonce, str) or nonce in self._used:
            return Decision(False, "approval-replayed")
        self._used[nonce] = claims["exp"]
        return Decision(True, "approved")

    def _sign(self, payload: str) -> bytes:
        return hmac.new(self._key, payload.encode(), hashlib.sha256).digest()

    def _verify(self, token: str) -> dict | None:
        payload, _, signature = token.partition(".")
        try:
            expected = self._sign(payload)
            if not hmac.compare_digest(expected, _unb64(signature)):
                return None
            claims = json.loads(_unb64(payload))
        except (ValueError, UnicodeDecodeError):
            return None
        return claims if isinstance(claims, dict) else None
