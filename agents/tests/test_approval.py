"""Human approval of irreversible actions (backlog E7.4)."""

import os

import pytest
from crfr_agents.approval import ActionPolicy, ApprovalGate, ToolCall, arguments_digest

POLICY = ActionPolicy.from_dict(
    {
        "tools": {
            "lire_dossier": {"effect": "read"},
            "envoyer_courriel": {"effect": "irreversible"},
            "virement": {"effect": "irreversible"},
        }
    }
)


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def gate(clock: Clock | None = None) -> ApprovalGate:
    return ApprovalGate(POLICY, key=os.urandom(32), clock=clock or Clock())


VIREMENT = ToolCall(agent="agent-back-office", tool="virement", arguments={"iban": "FR76...", "montant": 1200})


def test_read_tool_runs_without_approval():
    decision = gate().check(ToolCall("agent-back-office", "lire_dossier", {"id": "D-1"}))
    assert decision.allowed and decision.reason == "not-irreversible"


def test_irreversible_tool_needs_approval():
    decision = gate().check(VIREMENT)
    assert not decision.allowed and decision.reason == "approval-required"


def test_unknown_tool_is_treated_as_irreversible():
    assert POLICY.effect("supprimer_compte") == "irreversible"
    assert gate().check(ToolCall("a", "supprimer_compte", {})).reason == "approval-required"


def test_approved_call_runs_once():
    g = gate()
    token = g.approve(VIREMENT, approver="superviseur.dupont", ttl_s=300)
    assert g.check(VIREMENT, token).allowed
    assert g.check(VIREMENT, token).reason == "approval-replayed"


def test_approval_is_bound_to_the_arguments():
    g = gate()
    token = g.approve(VIREMENT, approver="superviseur.dupont", ttl_s=300)
    changed = ToolCall(VIREMENT.agent, VIREMENT.tool, {**VIREMENT.arguments, "montant": 120000})
    assert g.check(changed, token).reason == "approval-mismatch"


def test_approval_is_bound_to_the_agent_and_tool():
    g = gate()
    token = g.approve(VIREMENT, approver="superviseur.dupont", ttl_s=300)
    assert g.check(ToolCall("autre-agent", "virement", VIREMENT.arguments), token).reason == "approval-mismatch"
    other_tool = ToolCall(VIREMENT.agent, "envoyer_courriel", VIREMENT.arguments)
    assert g.check(other_tool, token).reason == "approval-mismatch"


def test_approval_expires():
    clock = Clock()
    g = gate(clock)
    token = g.approve(VIREMENT, approver="superviseur.dupont", ttl_s=60)
    clock.now += 61
    assert g.check(VIREMENT, token).reason == "approval-expired"


def test_forged_or_foreign_token_is_refused():
    g = gate()
    token = g.approve(VIREMENT, approver="superviseur.dupont", ttl_s=300)
    payload, signature = token.split(".")
    assert g.check(VIREMENT, payload + "." + signature[::-1]).reason == "approval-invalid"
    assert g.check(VIREMENT, "garbage").reason == "approval-invalid"
    assert gate().check(VIREMENT, token).reason == "approval-invalid"  # another key


def test_agent_cannot_approve_its_own_action():
    with pytest.raises(ValueError, match="self-approval"):
        gate().approve(VIREMENT, approver=VIREMENT.agent, ttl_s=300)
    with pytest.raises(ValueError, match="approver"):
        gate().approve(VIREMENT, approver="", ttl_s=300)


def test_ttl_is_bounded():
    with pytest.raises(ValueError, match="ttl"):
        gate().approve(VIREMENT, approver="superviseur.dupont", ttl_s=86_400)
    with pytest.raises(ValueError, match="ttl"):
        gate().approve(VIREMENT, approver="superviseur.dupont", ttl_s=0)


def test_short_key_is_refused():
    with pytest.raises(ValueError, match="key"):
        ApprovalGate(POLICY, key=b"short")


def test_digest_ignores_key_order_but_not_values():
    assert arguments_digest({"a": 1, "b": "é"}) == arguments_digest({"b": "é", "a": 1})
    assert arguments_digest({"a": 1}) != arguments_digest({"a": "1"})


def test_pending_request_shows_the_human_what_runs():
    pending = gate().request(VIREMENT)
    assert pending.tool == "virement" and pending.agent == "agent-back-office"
    assert pending.digest == arguments_digest(VIREMENT.arguments)
    assert '"montant": 1200' in pending.summary


def test_every_call_mode_requires_approval_for_read_tools():
    g = gate()
    read = ToolCall("agent-back-office", "lire_dossier", {"id": "D-1"})
    assert g.check(read, every_call=True).reason == "approval-required"
    token = g.approve(read, approver="superviseur.dupont", ttl_s=60)
    assert g.check(read, token, every_call=True).allowed
