"""Decisions of the guard, independent of gRPC so that they can be unit-tested.

Order of the checks on a request, first refusal wins:

1. identity (the token was verified by Envoy; the guard reads user, application, groups, team);
2. kill switches (E2.6): global switch -> 503, revoked user, team or application -> 403;
3. OPA policy (E2.5): model allowed for the caller's groups, request size, ``max_tokens``, no
   identifier left in clear text -> 403 with the policy's reasons; OPA unreachable -> 503;
   Before the policy, the pseudonymisation stage (E3.5) replaces personal data by pseudonyms in
   every text the model reads; the policy then checks that no identifier is left in clear text.
4. daily token quotas per user, team and application (E2.4) -> 429;
5. monthly budget per user, team and application (E2.4) -> 429.

Usage is charged when the response completes, as Envoy AI Gateway does for its own rate limits: a
request admitted under the limit may overshoot it, the next one is refused.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from . import residual, usage
from .audit import AuditLog, ContentLog, fingerprint
from .config import Config
from .identity import Identity, IdentityError, from_authorization
from .ledger import Ledger
from .policy import OpaClient, PolicyUnavailable


@dataclass(frozen=True)
class Refusal:
    status: int
    error_type: str  # Anthropic error type, so that SDKs surface it correctly
    reason: str
    message: str

    def body(self) -> bytes:
        return json.dumps(
            {"type": "error", "error": {"type": self.error_type, "message": f"{self.reason}: {self.message}"}}
        ).encode()


@dataclass
class Exchange:
    """State kept between the request and the response of one call."""

    request_id: str | None = None
    identity: Identity | None = None
    model: str | None = None
    response_status: int | None = None
    content_type: str = ""
    response_body: bytearray = field(default_factory=bytearray)
    partial_line: bytearray = field(default_factory=bytearray)
    truncated: bool = False
    new_body: bytes | None = None  # rewritten request body, when something was pseudonymised
    session: str | None = None  # vault session of this call, when the answer must be re-identified
    pseudonymised: dict | None = None  # counts by type, never values
    stream: object | None = None  # StreamReidentifier of a streamed answer
    answer: bytearray = field(default_factory=bytearray)  # buffered JSON answer to re-identify
    sent: bytes | None = None  # body forwarded to Bedrock, for the content log
    upstream: bytearray = field(default_factory=bytearray)  # answer as Bedrock sent it, for the content log
    started_ns: int | None = None  # start of the call, for its telemetry span


class Guard:
    def __init__(
        self,
        config: Config,
        ledger: Ledger,
        opa: OpaClient,
        log: AuditLog,
        pseudonymiser=None,
        content: ContentLog | None = None,
        telemetry=None,
    ):
        self.config, self.ledger, self.opa, self.log = config, ledger, opa, log
        self.pseudonymiser = pseudonymiser
        if content is not None and pseudonymiser is None:
            raise ValueError("the content log needs pseudonymisation: it would otherwise keep personal data")
        self.content = content
        self.telemetry = telemetry

    # Request --------------------------------------------------------------------------------
    def on_request(self, exchange: Exchange, headers: dict[str, str], raw_body: bytes) -> Refusal | None:
        exchange.request_id = headers.get("x-request-id")
        exchange.started_ns = time.time_ns()
        refusal = self._check(exchange, headers, raw_body)
        identity = exchange.identity
        if self.content is not None and refusal is None:
            exchange.sent = exchange.new_body if exchange.new_body is not None else raw_body
        self.log.write(
            event="request",
            request_id=exchange.request_id,
            prompt_hmac=fingerprint(self.log.mac, raw_body or b""),
            user=identity.user if identity else None,
            team=identity.team if identity else None,
            app=identity.app if identity else None,
            model=exchange.model,
            decision="refused" if refusal else "admitted",
            reason=refusal.reason if refusal else None,
            status=refusal.status if refusal else None,
            pseudonymised=exchange.pseudonymised or None,
        )
        if refusal is not None and self.telemetry is not None:
            self.telemetry.record(exchange, refusal)
        return refusal

    def _check(self, exchange: Exchange, headers: dict[str, str], raw_body: bytes) -> Refusal | None:
        cfg = self.config
        try:
            identity = from_authorization(headers.get("authorization"), cfg.user_claim, cfg.app_claim, cfg.team_prefix)
        except IdentityError as error:
            return Refusal(401, "authentication_error", "identity", str(error))
        exchange.identity = identity
        try:
            body = json.loads(raw_body or b"{}")
        except (ValueError, UnicodeDecodeError):
            return Refusal(400, "invalid_request_error", "invalid-json", "request body is not JSON")
        if not isinstance(body, dict):
            return Refusal(400, "invalid_request_error", "invalid-json", "request body must be an object")
        model = body.get("model")
        exchange.model = model if isinstance(model, str) else None

        switch = self.ledger.active_switch(identity.keys())
        if switch:
            scope, key, why = switch
            if scope == "global":
                return Refusal(503, "overloaded_error", "kill-switch-global", f"gateway stopped: {why}")
            return Refusal(403, "permission_error", f"kill-switch-{scope}", f"{scope} revoked: {why}")

        if self.pseudonymiser is not None:
            # The session groups the turns of one conversation; it is scoped to the caller, so that a
            # session id chosen by one user never opens another user's mapping.
            client_session = headers.get("x-crfr-session") or exchange.request_id or "no-session"
            exchange.session = f"{identity.app}\x1f{identity.user}\x1f{client_session}"
            body, report = self.pseudonymiser.request(body, exchange.session)
            exchange.pseudonymised = report.counts
            if report.counts:
                exchange.new_body = json.dumps(body, ensure_ascii=False).encode()
                raw_body = exchange.new_body

        policy_input = {
            "user": identity.user,
            "app": identity.app,
            "team": identity.team,
            "groups": list(identity.groups),
            "model": exchange.model,
            "request_bytes": len(raw_body),
            "max_tokens": body.get("max_tokens"),
            "stream": bool(body.get("stream", False)),
            "pii": {
                "residual": sorted({t for text in residual.texts(body) for t in residual.find(text)}),
                "pseudonymised": exchange.pseudonymised or {},
            },
        }
        try:
            decision = self.opa.decide(policy_input)
        except PolicyUnavailable as error:
            return Refusal(503, "api_error", "policy-unavailable", f"policy engine unreachable ({error})")
        if not decision.allow:
            reasons = ", ".join(decision.reasons) or "denied"
            return Refusal(403, "permission_error", "policy", reasons)

        for scope, key in identity.keys().items():
            limit = cfg.daily_tokens.limit(scope, key)
            if limit is not None and self.ledger.tokens_today(scope, key) >= limit:
                return Refusal(429, "rate_limit_error", f"quota-{scope}", f"daily token quota of {scope} reached")
        if exchange.model not in cfg.prices:
            return Refusal(403, "permission_error", "no-price", f"no price configured for {exchange.model}")
        for scope, key in identity.keys().items():
            budget = cfg.monthly_budget.limit(scope, key)
            if budget is not None and self.ledger.cost_this_month(scope, key) >= budget:
                return Refusal(429, "rate_limit_error", f"budget-{scope}", f"monthly budget of {scope} reached")
        return None

    # Response -------------------------------------------------------------------------------
    def rewrites_response(self, exchange: Exchange) -> bool:
        return self.pseudonymiser is not None and exchange.session is not None

    def response_out(self, exchange: Exchange, chunk: bytes, end: bool) -> bytes:
        """Bytes to send to the client for this upstream chunk, pseudonyms restored."""
        from crfr_pseudo.pseudonymiser import StreamReidentifier

        if "text/event-stream" in exchange.content_type:
            if exchange.stream is None:
                exchange.stream = StreamReidentifier(self.pseudonymiser, exchange.session)
            out = exchange.stream.feed(chunk)
            return out + exchange.stream.finish() if end else out
        exchange.answer.extend(chunk)
        if not end:
            return b""
        raw = bytes(exchange.answer)
        try:
            doc = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return raw
        if not isinstance(doc, dict):
            return raw
        return json.dumps(self.pseudonymiser.response(doc, exchange.session), ensure_ascii=False).encode()

    def on_response_chunk(self, exchange: Exchange, chunk: bytes) -> None:
        if exchange.sent is not None:
            room = self.config.max_buffer_bytes - len(exchange.upstream)
            exchange.upstream.extend(chunk[: max(room, 0)])
        if "text/event-stream" in exchange.content_type:
            # Keep only the events that carry usage, so that a long stream uses bounded memory.
            exchange.partial_line.extend(chunk)
            *lines, rest = bytes(exchange.partial_line).split(b"\n")
            exchange.partial_line = bytearray(rest[: self.config.max_buffer_bytes])
            for line in lines:
                if line.startswith(b"data:") and (b'"message_start"' in line or b'"message_delta"' in line):
                    self._keep(exchange, line + b"\n")
            return
        self._keep(exchange, chunk)

    def _keep(self, exchange: Exchange, chunk: bytes) -> None:
        room = self.config.max_buffer_bytes - len(exchange.response_body)
        if len(chunk) > room:
            exchange.truncated = True
        exchange.response_body.extend(chunk[: max(room, 0)])

    def on_response_end(self, exchange: Exchange) -> None:
        if exchange.identity is None or exchange.model is None:
            return
        if self.content is not None and exchange.sent is not None:
            self.content.write(exchange.request_id, exchange.sent, bytes(exchange.upstream))
        found = None
        if exchange.partial_line:
            self.on_response_chunk(exchange, b"\n")
        if exchange.response_status == 200:
            found = usage.parse(bytes(exchange.response_body), exchange.content_type)
        cost = None
        if found:
            cost = self.config.prices[exchange.model].cost(found)
            self.ledger.charge(exchange.identity.keys(), exchange.model, found, cost)
        self.log.write(
            event="response",
            request_id=exchange.request_id,
            user=exchange.identity.user,
            team=exchange.identity.team,
            app=exchange.identity.app,
            model=exchange.model,
            status=exchange.response_status,
            usage=found.__dict__ if found else None,
            cost=round(cost, 6) if cost is not None else None,
            usage_missing=True if exchange.response_status == 200 and not found else None,
            truncated=True if exchange.truncated else None,
        )
        if self.telemetry is not None:
            self.telemetry.record(exchange, None, found)
