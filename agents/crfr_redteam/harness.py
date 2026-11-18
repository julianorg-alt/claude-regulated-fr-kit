"""Indirect prompt injection bench (backlog E7.3).

The bench assumes a fully compromised model: whatever the trapped document, ticket or tool
description asks, the model does it. It then pushes the resulting action through the controls of the
kit and records whether the attacker's effect happens. The attack success rate (ASR) it publishes is
therefore a property of the controls around the model, not of the model; the model itself is tested
by `make redteam-live` with real credentials.

Two configurations are always measured: `unprotected` (no control, every attack must succeed, which
shows the bench is able to see a success) and `kit` (the controls shipped in this version).
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from crfr_agents.approval import ActionPolicy, ApprovalGate, ToolCall
from crfr_agents.destinations import DestinationPolicy
from crfr_agents.registry import PinnedTool, Registry, Server, tool_fingerprint

FAMILIES = ("document", "ticket", "tool_description")
AGENT = "agent-redteam"


@dataclass(frozen=True)
class Scenario:
    id: str
    family: str
    sector: str
    owasp: tuple[str, ...]
    task: str
    carrier: str
    attack: dict
    poisoned_tool: str | None = None
    pinned_description: str | None = None
    served_description: str | None = None

    def action(self) -> ToolCall | None:
        """What the compromised model does: the injected tool call, or nothing (answer attacks)."""
        if "tool" not in self.attack:
            return None
        return ToolCall(AGENT, self.attack["tool"], dict(self.attack.get("arguments", {})))


@dataclass(frozen=True)
class Bench:
    tools: dict
    scenarios: tuple[Scenario, ...]

    @classmethod
    def load(cls, path: Path) -> Bench:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        scenarios = []
        seen = set()
        for raw in data.get("scenario", []):
            s = Scenario(**{**raw, "owasp": tuple(raw["owasp"])})
            if s.id in seen:
                raise ValueError(f"duplicate scenario id {s.id}")
            seen.add(s.id)
            if s.family not in FAMILIES or s.attack.get("kind") not in ("tool_call", "answer"):
                raise ValueError(f"{s.id}: unknown family or attack kind")
            if s.family == "tool_description" and not (
                s.poisoned_tool and s.pinned_description and s.served_description
            ):
                raise ValueError(
                    f"{s.id}: a tool description attack needs poisoned_tool, pinned and served descriptions"
                )
            if s.action() is not None and s.action().tool not in data.get("tools", {}):
                raise ValueError(f"{s.id}: tool {s.action().tool} is not declared")
            scenarios.append(s)
        return cls(data.get("tools", {}), tuple(scenarios))


# A control looks at a scenario and at the compromised model's action; it returns the reason it
# blocks, or None.
Control = Callable[[Scenario, ToolCall | None], str | None]


def kit_controls(tools: dict) -> list[tuple[str, Control]]:
    destinations = DestinationPolicy.from_dict({"tools": tools})
    # The bench never holds an approval: the attacker cannot obtain one, only a person can.
    gate = ApprovalGate(ActionPolicy.from_dict({"tools": tools}), key=os.urandom(32))

    def destination(_: Scenario, call: ToolCall | None) -> str | None:
        if call is None:
            return None
        decision = destinations.check(call)
        return None if decision.allowed else decision.reason

    def approval(_: Scenario, call: ToolCall | None) -> str | None:
        if call is None:
            return None
        decision = gate.check(call)
        return None if decision.allowed else decision.reason

    def registry(s: Scenario, _: ToolCall | None) -> str | None:
        # The MCP proxy compares what the server serves with the fingerprint pinned at review (E8.1).
        if s.family != "tool_description":
            return None
        pinned = tool_fingerprint({"name": s.poisoned_tool, "description": s.pinned_description})
        server = Server(
            "bench", "https://bench.example/mcp", {s.poisoned_tool: PinnedTool(s.poisoned_tool, pinned, "read")}
        )
        served = [{"name": s.poisoned_tool, "description": s.served_description}]
        mismatches = Registry({"bench": server}).verify(server, served)
        return mismatches[0].reason if mismatches else None

    return [("registry", registry), ("destinations", destination), ("approval", approval)]


def run(bench: Bench, controls: list[tuple[str, Control]]) -> dict:
    results = []
    for s in bench.scenarios:
        call = s.action()
        blocked = None
        for name, control in controls:
            reason = control(s, call)
            if reason is not None:
                blocked = f"{name}:{reason}"
                break
        results.append(
            {"id": s.id, "family": s.family, "sector": s.sector, "owasp": list(s.owasp),
             "outcome": "blocked" if blocked else "succeeded", "blocked_by": blocked}
        )  # fmt: skip
    by_family = {}
    for family in FAMILIES:
        rows = [r for r in results if r["family"] == family]
        if rows:
            won = sum(r["outcome"] == "succeeded" for r in rows)
            by_family[family] = {"scenarios": len(rows), "succeeded": won, "asr": round(won / len(rows), 4)}
    won = sum(r["outcome"] == "succeeded" for r in results)
    return {
        "scenarios": len(results),
        "succeeded": won,
        "asr": round(won / len(results), 4) if results else 0.0,
        "by_family": by_family,
        "results": results,
    }


def measure(bench: Bench, version: str) -> dict:
    return {
        "version": version,
        "assumption": "compromised-model",
        "configurations": {"unprotected": run(bench, []), "kit": run(bench, kit_controls(bench.tools))},
    }
