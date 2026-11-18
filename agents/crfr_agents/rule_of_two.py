"""Rule of Two sheets of agentic workflows (backlog E8.4, verifications.md V51).

In one session an agent should hold at most two of three properties: [A] it processes untrusted
input, [B] it reaches sensitive systems or private data, [C] it changes state or communicates
outside. A workflow holding all three runs only under human supervision: the MCP proxy then asks for
an approval on every tool call, read tools included.

Each workflow has a sheet (agents/workflows/*.toml). The sheet cannot under-declare [C]: if one of
the workflow's tools writes, is irreversible or reaches a destination, [C] must be true.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from crfr_agents.registry import Registry

OVERSIGHT = ("none", "human-approval-irreversible", "human-approval-all-actions")


@dataclass(frozen=True)
class Workflow:
    id: str
    agent: str
    servers: tuple[str, ...]
    untrusted_input: bool  # [A]
    sensitive_access: bool  # [B]
    state_change: bool  # [C]
    oversight: str
    owner: str
    justification: str

    @property
    def properties(self) -> int:
        return sum((self.untrusted_input, self.sensitive_access, self.state_change))

    @property
    def approval_on_every_call(self) -> bool:
        return self.properties == 3


def load(directory: Path) -> dict[str, Workflow]:
    """Sheets by agent id. An agent belongs to one workflow, so that its sheet decides alone."""
    out = {}
    for path in sorted(directory.glob("*.toml")):
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        wf = Workflow(
            id=raw["id"], agent=raw["agent"], servers=tuple(raw["servers"]),
            untrusted_input=bool(raw["untrusted_input"]), sensitive_access=bool(raw["sensitive_access"]),
            state_change=bool(raw["state_change"]), oversight=raw["oversight"], owner=raw["owner"],
            justification=raw["justification"],
        )  # fmt: skip
        if wf.agent in out:
            raise ValueError(f"{path.name}: agent {wf.agent} already has the sheet {out[wf.agent].id}")
        out[wf.agent] = wf
    return out


def check(workflows: dict[str, Workflow], registry: Registry) -> list[str]:
    """Problems in the sheets (empty list: every sheet is consistent)."""
    problems = []
    for wf in workflows.values():
        if wf.oversight not in OVERSIGHT:
            problems.append(f"{wf.id}: oversight must be one of {OVERSIGHT}")
        if wf.approval_on_every_call and wf.oversight != "human-approval-all-actions":
            problems.append(f"{wf.id}: holds [A], [B] and [C]; oversight must be human-approval-all-actions")
        if not wf.owner or not wf.justification.strip():
            problems.append(f"{wf.id}: owner and justification are required")
        acts = False
        for sid in wf.servers:
            server = registry.server(sid)
            if server is None:
                problems.append(f"{wf.id}: server {sid} is not in the registry")
                continue
            acts = acts or any(t.effect != "read" or t.destination for t in server.tools.values())
        if acts and not wf.state_change:
            problems.append(f"{wf.id}: a tool of its servers writes or reaches out, so [C] must be true")
    return problems
