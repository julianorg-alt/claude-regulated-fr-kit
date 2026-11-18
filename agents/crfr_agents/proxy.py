"""MCP proxy: the one door between agents and MCP servers (backlog E8.2, E8.3, E8.5, E7.4).

For every JSON-RPC message an agent sends to `/mcp/<server>` the proxy:

1. checks the agent's access token: signature, issuer, expiry, and an audience equal to the proxy's
   own resource URI (RFC 8707). Otherwise 401 with the RFC 9728 challenge;
2. checks that the server is in the registry and in the agent's Rule of Two sheet;
3. on `tools/list`, compares what the server serves with the pinned fingerprints. A changed
   description, an extra tool or a missing tool blocks the server until the change is reviewed;
4. on `tools/call`, re-verifies the tool list if the last check is older than `list_ttl_s`, then
   applies the destination allowlist and the human approval gate (every call when the sheet holds
   [A], [B] and [C]);
5. forwards with a credential it mints for this agent and this server only. The agent's token is
   never forwarded (no token passthrough);
6. logs the call, its arguments and its result in a chained log, with sensitive fields digested.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

from crfr_agents.approval import ApprovalGate, ToolCall
from crfr_agents.calllog import CallLog, redact
from crfr_agents.destinations import DestinationPolicy
from crfr_agents.registry import Registry, Server
from crfr_agents.rule_of_two import Workflow
from crfr_agents.tokens import TokenError, TokenMinter, TokenVerifier, protected_resource_metadata, www_authenticate

# JSON-RPC error codes of the proxy (implementation-defined range of JSON-RPC 2.0).
BLOCKED = -32001
UPSTREAM = -32002
FORWARDED_HEADERS = ("mcp-session-id", "mcp-protocol-version")

Send = Callable[[str, dict[str, str], dict], tuple[int, dict | None, dict[str, str]]]


@dataclass
class Response:
    status: int
    body: dict | None
    headers: dict[str, str] = field(default_factory=dict)


def http_send(url: str, headers: dict[str, str], message: dict) -> tuple[int, dict | None, dict[str, str]]:
    """POST a JSON-RPC message; JSON responses only (servers must not answer with an SSE stream here)."""
    request = urllib.request.Request(url, json.dumps(message).encode(), headers, method="POST")  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (registry URLs only)
            raw, status, got = response.read(), response.status, dict(response.headers)
    except urllib.error.HTTPError as error:
        raw, status, got = error.read(), error.code, dict(error.headers)
    lowered = {k.lower(): v for k, v in got.items()}
    if not raw:
        return status, None, lowered
    if "application/json" not in lowered.get("content-type", ""):
        return 502, {"error": "upstream answered with a non-JSON body"}, lowered
    return status, json.loads(raw), lowered


def _error(message: dict, status: int, code: int, reason: str, detail: str = "") -> Response:
    text = f"{reason}: {detail}" if detail else reason
    return Response(status, {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": code, "message": text}})


class McpProxy:
    def __init__(
        self,
        *,
        resource: str,
        authorization_servers: list[str],
        registry: Registry,
        workflows: dict[str, Workflow],
        verifier: TokenVerifier,
        minter: TokenMinter,
        gate: ApprovalGate,
        log: CallLog,
        send: Send = http_send,
        list_ttl_s: float = 60.0,
        clock: Callable[[], float] = time.time,
    ):
        self.resource = resource
        self.authorization_servers = authorization_servers
        self.registry, self.workflows = registry, workflows
        self.verifier, self.minter, self.gate, self.log = verifier, minter, gate, log
        self.destinations = DestinationPolicy.from_dict(registry.tool_policy())
        self._send, self.list_ttl_s, self._clock = send, list_ttl_s, clock
        self._verified: dict[str, float] = {}  # server id -> time of the last matching tools/list
        self._blocked: dict[str, str] = {}  # server id -> why, until a reviewed registry is loaded

    def metadata(self) -> dict:
        return protected_resource_metadata(self.resource, self.authorization_servers, ["mcp:tools"])

    # Entry point ------------------------------------------------------------------------------
    def handle(self, server_id: str, headers: dict[str, str], message: dict) -> Response:
        headers = {k.lower(): v for k, v in headers.items()}
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(message if isinstance(message, dict) else {}, 400, -32600, "invalid-request")
        try:
            caller = self.verifier.verify(headers.get("authorization"))
        except TokenError as error:
            self.log.write(event="refused", server=server_id, method=message.get("method"), reason=error.reason)
            challenge = www_authenticate(self.resource, "invalid_token" if error.reason != "token-missing" else None)
            response = _error(message, 401, BLOCKED, error.reason)
            response.headers["WWW-Authenticate"] = challenge
            return response
        refusal = self._admit(caller.agent, server_id, message)
        if refusal is not None:
            return refusal
        server = self.registry.server(server_id)
        method = message.get("method")
        if method == "tools/list":
            return self._tools_list(caller, server, headers, message)
        if method == "tools/call":
            return self._tools_call(caller, server, headers, message)
        return self._forward(caller, server, headers, message)

    def _admit(self, agent: str, server_id: str, message: dict) -> Response | None:
        reason = None
        workflow = self.workflows.get(agent)
        if self.registry.server(server_id) is None:
            reason = "server-not-registered"
        elif workflow is None:
            reason = "agent-without-workflow"
        elif server_id not in workflow.servers:
            reason = "server-not-in-workflow"
        elif server_id in self._blocked:
            reason = "server-blocked"
        if reason is None:
            return None
        self.log.write(event="refused", agent=agent, server=server_id, method=message.get("method"), reason=reason)
        return _error(message, 403, BLOCKED, reason, self._blocked.get(server_id, ""))

    # Methods ----------------------------------------------------------------------------------
    def _tools_list(self, caller, server: Server, headers: dict, message: dict) -> Response:
        response = self._forward(caller, server, headers, message, log=False)
        if response.status != 200 or not isinstance(response.body, dict) or "result" not in response.body:
            return response
        blocked = self._check_tools(caller.agent, server, response.body["result"].get("tools", []))
        return _error(message, 403, BLOCKED, "server-blocked", blocked) if blocked else response

    def _check_tools(self, agent: str, server: Server, tools: list) -> str | None:
        mismatches = self.registry.verify(server, tools if isinstance(tools, list) else [])
        if not mismatches:
            self._verified[server.id] = self._clock()
            return None
        why = ", ".join(f"{m.tool} {m.reason}" for m in mismatches)
        self._blocked[server.id] = why
        self._verified.pop(server.id, None)
        self.log.write(event="registry-mismatch", agent=agent, server=server.id, detail=why)
        return why

    def _tools_call(self, caller, server: Server, headers: dict, message: dict) -> Response:
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        name, arguments = params.get("name"), params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _error(message, 400, -32602, "invalid-arguments")
        pinned = server.tools.get(name) if isinstance(name, str) else None
        if pinned is None:
            return self._refuse_call(caller, server, name, arguments, message, "tool-not-registered")
        if self._clock() - self._verified.get(server.id, float("-inf")) > self.list_ttl_s:
            listing = self._forward(caller, server, headers, {"jsonrpc": "2.0", "id": "crfr-verify",
                                                               "method": "tools/list"}, log=False)  # fmt: skip
            tools = (listing.body or {}).get("result", {}).get("tools") if listing.status == 200 else None
            if tools is None:
                return _error(message, 502, UPSTREAM, "tools-list-unavailable")
            blocked = self._check_tools(caller.agent, server, tools)
            if blocked:
                return _error(message, 403, BLOCKED, "server-blocked", blocked)
        call = ToolCall(caller.agent, f"{server.id}.{name}", arguments)
        destination = self.destinations.check(call)
        if not destination.allowed:
            return self._refuse_call(caller, server, name, arguments, message, destination.reason)
        workflow = self.workflows[caller.agent]
        approval = self.gate.check(call, headers.get("x-crfr-approval"), every_call=workflow.approval_on_every_call)
        if not approval.allowed:
            return self._refuse_call(caller, server, name, arguments, message, approval.reason)
        response = self._forward(caller, server, headers, message, log=False)
        self.log.write(
            event="tool-call", agent=caller.agent, subject=caller.subject, workflow=workflow.id, server=server.id,
            tool=name, effect=pinned.effect, approval=approval.reason, status=response.status,
            arguments=redact(arguments, pinned.sensitive),
            result=redact((response.body or {}).get("result", (response.body or {}).get("error")), pinned.sensitive),
        )  # fmt: skip
        return response

    def _refuse_call(self, caller, server: Server, name, arguments: dict, message: dict, reason: str) -> Response:
        pinned = server.tools.get(name) if isinstance(name, str) else None
        self.log.write(
            event="tool-call-refused", agent=caller.agent, server=server.id, tool=name, reason=reason,
            arguments=redact(arguments, pinned.sensitive if pinned else ()),
        )  # fmt: skip
        return _error(message, 403, BLOCKED, reason)

    def _forward(self, caller, server: Server, headers: dict, message: dict, log: bool = True) -> Response:
        out = {
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
            # A credential for this agent and this server only; the agent's own token stays here.
            "authorization": "Bearer "
            + self.minter.mint(agent=caller.agent, subject=caller.subject, audience=server.url),  # fmt: skip
        }
        out.update({h: headers[h] for h in FORWARDED_HEADERS if h in headers})
        try:
            status, body, got = self._send(server.url, out, message)
        except (OSError, ValueError) as error:
            return _error(message, 502, UPSTREAM, "upstream-unreachable", type(error).__name__)
        if log:
            self.log.write(event="forward", agent=caller.agent, server=server.id, method=message.get("method"),
                           status=status)  # fmt: skip
        return Response(status, body, {h: got[h] for h in FORWARDED_HEADERS if h in got})
