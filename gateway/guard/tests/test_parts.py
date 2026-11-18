import json

import pytest
from conftest import RAW_CONFIG, bearer, jwt

from crfr_guard import config as config_module
from crfr_guard import residual, usage
from crfr_guard.identity import IdentityError, from_authorization
from crfr_guard.ledger import Ledger


def test_identity_reads_user_app_team():
    ident = from_authorization(bearer()["authorization"], "preferred_username", "azp", "team-")
    assert (ident.user, ident.app, ident.team) == ("alice", "demo-app", "team-risk")
    assert ident.keys() == {"user": "alice", "app": "demo-app", "team": "team-risk"}


def test_identity_first_team_alphabetically_and_no_team():
    two = bearer(groups=["team-b", "team-a"])["authorization"]
    assert from_authorization(two, "preferred_username", "azp", "team-").team == "team-a"
    none = bearer(groups=["claude-users"])["authorization"]
    assert "team" not in from_authorization(none, "preferred_username", "azp", "team-").keys()


@pytest.mark.parametrize(
    "header",
    [
        None,
        "Basic abc",
        "Bearer notajwt",
        "Bearer a.!!!.c",
        "Bearer " + jwt(azp="x"),
        "Bearer " + jwt(preferred_username="u", azp="a", groups="g"),
    ],
)
def test_identity_rejects_bad_tokens(header):
    with pytest.raises(IdentityError):
        from_authorization(header, "preferred_username", "azp", "team-")


def test_usage_from_json_and_sse():
    doc = {
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_input_tokens": 7,
            "cache_creation_input_tokens": 3,
        }
    }
    assert usage.parse(json.dumps(doc).encode()).total == 25
    sse = (
        b'event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":12,'
        b'"cache_read_input_tokens":4,"output_tokens":1}}}\n\n'
        b'event: content_block_delta\ndata: {"type":"content_block_delta"}\n\n'
        b'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":30}}\n\n'
    )
    got = usage.parse(sse, "text/event-stream")
    assert (got.input_tokens, got.output_tokens, got.cache_read_input_tokens) == (12, 30, 4)


@pytest.mark.parametrize("raw", [b"", b"not json", b"[]", b'{"usage": "x"}', b"data: nothing\n"])
def test_usage_absent(raw):
    assert usage.parse(raw) is None


def test_usage_ignores_negative_and_boolean_counts():
    assert usage.parse(b'{"usage": {"input_tokens": -5, "output_tokens": true}}').total == 0


# Check digits: values computed from the published algorithms, never real people.
VALID_NIR = "1 85 05 78 006 084 91"  # 97 - (1850578006084 mod 97) = 91
CORSICA_NIR = "2 90 01 2A 123 456 " + f"{97 - int('2900119123456') % 97:02d}"


def test_residual_detects_valid_keys_only():
    assert residual.find(f"assuré {VALID_NIR}") == ["NIR"]
    assert residual.find("assuré 1 85 05 78 006 084 92") == []
    assert residual.find(f"né en Corse {CORSICA_NIR}") == ["NIR"]
    assert residual.find("IBAN FR76 0000 0012 3412 3456 7890 151") == ["IBAN_FR"]
    assert residual.find("IBAN FR76 0000 0012 3412 3456 7890 150") == []
    assert residual.find("carte 4970 1000 0000 0063") == ["CARD"]
    assert residual.find("carte 4970 1000 0000 0064") == []
    assert residual.find("rendez-vous le 12/03/2026 à 14h") == []


def test_residual_walks_system_messages_and_tool_results():
    doc = {
        "system": [{"type": "text", "text": "x"}],
        "messages": [
            {"role": "user", "content": [{"type": "tool_result", "content": [{"type": "text", "text": VALID_NIR}]}]}
        ],
    }
    assert any("85 05" in t for t in residual.texts(doc))


def test_config_rejects_bad_values():
    for broken in (
        {**RAW_CONFIG, "prices": {"m": {"input_tokens": 1}}},
        {**RAW_CONFIG, "quotas": {"daily_tokens": {"default": {"planet": 1}}}},
        {**RAW_CONFIG, "budgets": {"currency": "EUR", "monthly": {"default": {"app": -1}}}},
        {k: v for k, v in RAW_CONFIG.items() if k != "opa"},
    ):
        with pytest.raises(config_module.ConfigError):
            config_module.parse(broken)


def test_shipped_config_is_valid_and_prices_every_routable_model():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    cfg = config_module.load(root / "gateway/config/guard.json")
    rendered = (root / "gateway/config/aigw.yaml").read_text()
    aliases = set()
    for doc in rendered.split("---\n")[1:]:
        doc = json.loads(doc)
        if doc["kind"] == "AIGatewayRoute":
            aliases |= {r["matches"][0]["headers"][0]["value"] for r in doc["spec"]["rules"]}
    assert aliases and aliases <= set(cfg.prices)


def test_ledger_sums_per_day_and_month(tmp_path, clock):
    ledger = Ledger(tmp_path / "l.sqlite", clock=clock)
    keys = {"user": "alice", "app": "demo-app", "team": "team-risk"}
    ledger.charge(keys, "m", usage.Usage(10, 5), 0.5)
    assert ledger.tokens_today("user", "alice") == 15
    assert ledger.tokens_today("team", "team-risk") == 15
    assert ledger.cost_this_month("app", "demo-app") == 0.5
    clock.now += 86_400  # next day, same month
    assert ledger.tokens_today("user", "alice") == 0
    assert ledger.cost_this_month("app", "demo-app") == 0.5
    clock.now += 40 * 86_400
    assert ledger.cost_this_month("app", "demo-app") == 0
    with pytest.raises(ValueError):
        ledger.tokens_today("user; DROP TABLE usage", "x")


def test_ledger_switches(tmp_path):
    ledger = Ledger(tmp_path / "s.sqlite")
    keys = {"user": "alice", "app": "demo-app"}
    assert ledger.active_switch(keys) is None
    ledger.set_switch("app", "demo-app", "leaked key")
    ledger.set_switch("global", "ignored", "incident")
    assert ledger.active_switch(keys)[0] == "global"
    assert ledger.clear_switch("global", "*")
    assert ledger.active_switch(keys) == ("app", "demo-app", "leaked key")
    assert not ledger.clear_switch("user", "nobody")
    with pytest.raises(ValueError):
        ledger.set_switch("planet", "x", "y")


def test_switch_is_seen_by_another_connection(tmp_path):
    """The admin command and the guard are two processes sharing the SQLite file."""
    path = tmp_path / "shared.sqlite"
    guard_side, admin_side = Ledger(path), Ledger(path)
    admin_side.set_switch("global", "*", "drill")
    assert guard_side.active_switch({"user": "u", "app": "a"})[0] == "global"
