"""Exit route to a second provider (backlog E10.1): standby aliases and the switch of the same aliases."""

import json
from pathlib import Path

import pytest

from crfr import gateway_config as gc

ROOT = Path(__file__).resolve().parents[2]
ROUTES = json.loads((ROOT / "infra/inventory/routes-eu.json").read_text())["routes"]
INVENTORY = ROOT / "infra/inventory/exit-providers.json"
MODELS = ["claude-sonnet-5", "claude-haiku-4-5"]


def provider(models=None):
    return gc.ExitProvider("mistral", gc.Backend("api.mistral.ai", 443, True), models or {"claude-sonnet-5": "m-large"})


def build(**kw):
    return gc.build(ROUTES, MODELS, "eu-west-3", gc.Backend.for_region("eu-west-3"), **kw)


def kind(docs, name):
    return [d for d in docs if d["kind"] == name]


def rules(docs):
    return {
        r["matches"][0]["headers"][0]["value"]: r["backendRefs"]
        for r in kind(docs, "AIGatewayRoute")[0]["spec"]["rules"]
    }


def test_no_exit_provider_by_default():
    docs = build()
    assert "exit-mistral" not in json.dumps(docs)


def test_standby_adds_separate_aliases_and_keeps_the_primary_route():
    r = rules(build(exit_provider=provider(), exit_mode="standby"))
    assert r["claude-sonnet-5"][0]["name"] == "bedrock-eu"
    assert r["exit-claude-sonnet-5"] == [{"name": "exit-mistral", "modelNameOverride": "m-large"}]
    assert "exit-claude-haiku-4-5" not in r


def test_switch_moves_the_same_alias_and_leaves_no_bedrock_ref():
    r = rules(build(exit_provider=provider(), exit_mode="switch"))
    assert r["claude-sonnet-5"] == [{"name": "exit-mistral", "modelNameOverride": "m-large"}]
    assert r["claude-haiku-4-5"][0]["name"] == "bedrock-eu"
    assert "exit-claude-sonnet-5" not in r


def test_exit_backend_openai_schema_tls_api_key_and_no_client_address():
    docs = build(exit_provider=provider())
    svc = next(d for d in kind(docs, "AIServiceBackend") if d["metadata"]["name"] == "exit-mistral")
    assert svc["spec"]["schema"] == {"name": "OpenAI", "prefix": "/v1"}
    assert "x-forwarded-for" in svc["spec"]["headerMutation"]["remove"]
    policy = next(d for d in kind(docs, "BackendSecurityPolicy") if d["metadata"]["name"] == "exit-mistral")
    assert policy["spec"]["type"] == "APIKey"
    tls = next(d for d in kind(docs, "BackendTLSPolicy") if d["metadata"]["name"] == "exit-mistral-tls")
    assert tls["spec"]["validation"]["hostname"] == "api.mistral.ai"


def test_api_key_comes_from_the_environment_not_the_file():
    text = gc.render(build(exit_provider=provider()))
    assert "${EXIT_PROVIDER_API_KEY}" in text


def test_exit_never_adds_a_model_without_a_bedrock_route():
    with pytest.raises(gc.ConfigError):
        build(exit_provider=provider({"claude-fable-5-2": "x"}))


def test_exit_mode_is_validated():
    with pytest.raises(gc.ConfigError):
        build(exit_provider=provider(), exit_mode="auto")


def test_no_automatic_failover_to_another_provider():
    """A silent change of processor is a decision (register, DPA, transfers), never a retry."""
    docs = build(exit_provider=provider(), exit_mode="standby")
    assert not [d for d in kind(docs, "BackendTrafficPolicy")]
    assert all("priority" not in ref for refs in rules(docs).values() for ref in refs if ref["name"] == "exit-mistral")


def test_inventory_hosts_are_dns_names_and_unverified_facts_are_flagged():
    inventory = json.loads(INVENTORY.read_text())
    for entry in inventory["providers"]:
        assert entry["host"] is None or "/" not in entry["host"]
        assert entry["hosting_verified"] is False  # V66: no region named in the provider's DPA
        assert entry["verification"]


def test_cli_refuses_an_unknown_provider_and_a_host_outside_the_inventory(tmp_path):
    common = ["--routes", str(ROOT / "infra/inventory/routes-eu.json"), "--models", "claude-sonnet-5",
              "--out", str(tmp_path / "x.yaml"), "--exit-model", "claude-sonnet-5=m"]  # fmt: skip
    assert gc.main([*common, "--exit-provider", "acme"]) == 1
    assert gc.main([*common, "--exit-provider", "mistral", "--exit-host", "evil.example"]) == 1
    assert gc.main([*common, "--exit-provider", "mistral"]) == 0
    assert "api.mistral.ai" in (tmp_path / "x.yaml").read_text()
