"""Private registry of MCP servers (backlog E8.1).

Only the servers listed here can be reached through the MCP proxy, and only the tools listed for each
of them. Each tool is pinned by the SHA-256 of its canonical definition (name, description, input
schema): a server that changes a description after review (a "rug pull", or a poisoned description)
no longer matches and is blocked until someone reviews the change and pins the new fingerprint.
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path

from crfr_agents.approval import EFFECTS, canonical


def tool_fingerprint(tool: dict) -> str:
    """SHA-256 of what the model reads about a tool: its name, description and input schema."""
    pinned = {
        "name": tool.get("name"),
        "description": tool.get("description", ""),
        "inputSchema": tool.get("inputSchema", {}),
    }
    return hashlib.sha256(canonical(pinned)).hexdigest()


@dataclass(frozen=True)
class PinnedTool:
    name: str
    sha256: str
    effect: str
    destination: dict | None = None
    sensitive: tuple[str, ...] = ()  # argument or result fields logged as a digest only


@dataclass(frozen=True)
class Server:
    id: str
    url: str  # canonical URI of the server: the audience of the tokens the proxy mints for it
    tools: dict[str, PinnedTool]


@dataclass(frozen=True)
class Mismatch:
    tool: str
    reason: str  # "description-changed" | "tool-not-registered" | "tool-missing"


class Registry:
    def __init__(self, servers: dict[str, Server]):
        self.servers = servers

    @classmethod
    def load(cls, path: Path) -> Registry:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        servers = {}
        for sid, raw in (data.get("server") or {}).items():
            url = raw.get("url", "")
            if not url.startswith("https://") and not url.startswith("http://127.0.0.1"):
                raise ValueError(f"server {sid}: url must be https (or loopback for tests)")
            tools = {}
            for name, spec in (raw.get("tools") or {}).items():
                if spec.get("effect") not in EFFECTS:
                    raise ValueError(f"server {sid}, tool {name}: effect must be one of {EFFECTS}")
                digest = spec.get("sha256", "")
                if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                    raise ValueError(f"server {sid}, tool {name}: sha256 must be 64 lowercase hex digits")
                tools[name] = PinnedTool(
                    name, digest, spec["effect"], spec.get("destination"), tuple(spec.get("sensitive", ()))
                )
            servers[sid] = Server(sid, url, tools)
        return cls(servers)

    def server(self, server_id: str) -> Server | None:
        return self.servers.get(server_id)

    def verify(self, server: Server, served_tools: list[dict]) -> list[Mismatch]:
        """Differences between the tools a server serves and the pinned ones (empty list: all match)."""
        problems = []
        served = {t.get("name"): t for t in served_tools if isinstance(t, dict)}
        for name, tool in served.items():
            pinned = server.tools.get(name)
            if pinned is None:
                problems.append(Mismatch(str(name), "tool-not-registered"))
            elif tool_fingerprint(tool) != pinned.sha256:
                problems.append(Mismatch(name, "description-changed"))
        for name in server.tools:
            if name not in served:
                problems.append(Mismatch(name, "tool-missing"))
        return problems

    def tool_policy(self) -> dict:
        """Effects and destinations in the format of ActionPolicy and DestinationPolicy, keyed by
        `<server>.<tool>` so that two servers may each have a tool of the same name."""
        out = {}
        for server in self.servers.values():
            for tool in server.tools.values():
                spec = {"effect": tool.effect}
                if tool.destination:
                    spec["destination"] = tool.destination
                out[f"{server.id}.{tool.name}"] = spec
        return {"tools": out}


def pin(server_id: str, tools: list[dict], effects: dict[str, str] | None = None) -> str:
    """TOML block to review and paste into the registry for the tools a server serves today."""
    lines = []
    for tool in sorted(tools, key=lambda t: t["name"]):
        lines.append(f"[server.{server_id}.tools.{tool['name']}]")
        lines.append(f'sha256 = "{tool_fingerprint(tool)}"')
        lines.append(f'effect = "{(effects or {}).get(tool["name"], "irreversible")}"')
        lines.append("")
    return "\n".join(lines)
