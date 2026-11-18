import json
from pathlib import Path

import pytest

from crfr import gateway_config as gc

ROOT = Path(__file__).resolve().parents[2]
ROUTES_FILE = ROOT / "infra/inventory/routes-eu.json"
ROUTES = json.loads(ROUTES_FILE.read_text())["routes"]


def real_backend():
    return gc.Backend.for_region("eu-west-3")


def kind(docs, name):
    return next(d for d in docs if d["kind"] == name)


def test_alias():
    assert gc.alias_of("Claude Haiku 4.5") == "claude-haiku-4-5"
    with pytest.raises(gc.ConfigError):
        gc.alias_of("Mistral Large")


def test_only_inventory_models_become_routes():
    docs = gc.build(ROUTES, ["claude-sonnet-5", "Claude Opus 5.5"], "eu-west-3", real_backend())
    rules = kind(docs, "AIGatewayRoute")["spec"]["rules"]
    overrides = {r["backendRefs"][0]["modelNameOverride"] for r in rules}
    assert overrides == {"eu.anthropic.claude-sonnet-5", "eu.anthropic.claude-opus-5-5"}


@pytest.mark.parametrize("model", ["claude-fable-5-2", "claude-mythos-5", "claude-3-haiku", "gpt-5"])
def test_models_without_eu_route_are_refused(model):
    with pytest.raises(gc.ConfigError):
        gc.build(ROUTES, [model], "eu-west-3", real_backend())


def test_london_source_has_no_route_in_strict_inventory():
    with pytest.raises(gc.ConfigError):
        gc.build(ROUTES, ["claude-sonnet-5"], "eu-west-2", gc.Backend.for_region("eu-west-2"))


def test_signing_region_and_tls_for_real_bedrock():
    docs = gc.build(ROUTES, ["claude-sonnet-5"], "eu-west-3", real_backend())
    assert kind(docs, "BackendSecurityPolicy")["spec"]["awsCredentials"]["region"] == "eu-west-3"
    host = kind(docs, "Backend")["spec"]["endpoints"][0]["fqdn"]["hostname"]
    assert host == "bedrock-runtime.eu-west-3.amazonaws.com"
    assert kind(docs, "BackendTLSPolicy")["spec"]["validation"]["hostname"] == host


def test_client_address_is_never_forwarded():
    docs = gc.build(ROUTES, ["claude-sonnet-5"], "eu-west-3", real_backend())
    xff = kind(docs, "ClientTrafficPolicy")["spec"]["clientIPDetection"]["xForwardedFor"]
    assert xff["disableXForwardedForAppend"] is True
    assert "x-forwarded-for" in kind(docs, "AIServiceBackend")["spec"]["headerMutation"]["remove"]


def test_jwt_and_group_authorisation():
    auth = gc.Auth("https://idp.example/realms/x", "https://idp.example/certs", ("claude-gateway",), "groups")
    docs = gc.build(ROUTES, ["claude-sonnet-5"], "eu-west-3", real_backend(), auth=auth)
    policy = kind(docs, "SecurityPolicy")
    assert policy["spec"]["authorization"]["defaultAction"] == "Deny"
    provider = policy["spec"]["jwt"]["providers"][0]
    assert provider["audiences"] == ["claude-gateway"]
    assert "claimToHeaders" not in provider


def test_no_credentials_in_rendered_config():
    text = gc.render(gc.build(ROUTES, ["claude-sonnet-5"], "eu-west-3", real_backend()))
    assert "${AWS_SECRET_ACCESS_KEY}" in text
    assert "AKIA" not in text


def test_cli_refuses_plaintext_to_real_bedrock(tmp_path):
    with pytest.raises(SystemExit):
        gc.main(
            [
                "--routes",
                str(ROUTES_FILE),
                "--models",
                "claude-sonnet-5",
                "--backend-plaintext",
                "--out",
                str(tmp_path / "x.yaml"),
            ]
        )


@pytest.mark.parametrize(("mode", "name"), [("standby", "aigw.yaml"), ("switch", "aigw-switch.yaml")])
def test_committed_local_config_is_up_to_date(mode, name):
    expected = gc.render(
        gc.build(
            ROUTES,
            ["claude-sonnet-5", "claude-opus-5-5", "claude-haiku-4-5"],
            "eu-west-3",
            gc.Backend("fake-bedrock", 8080, False),
            auth=gc.Auth(
                "http://keycloak:8080/realms/crfr",
                "http://keycloak:8080/realms/crfr/protocol/openid-connect/certs",
                ("claude-gateway",),
                "groups",
            ),
            guard=gc.GuardEndpoint("guard"),
            exit_provider=gc.ExitProvider(
                "local",
                gc.Backend("fake-bedrock", 8080, False),
                {"claude-sonnet-5": "exit-model-fr", "claude-haiku-4-5": "exit-model-fr-small"},
            ),
            exit_mode=mode,
        )
    )
    assert (ROOT / "gateway/config" / name).read_text() == expected, "run: make gateway-config"


def guarded():
    return gc.build(ROUTES, ["claude-sonnet-5"], "eu-west-3", real_backend(), guard=gc.GuardEndpoint("guard"))


def test_guard_runs_on_an_edge_listener_in_front_of_ai_gateway():
    docs = guarded()
    listeners = {li["name"]: li["port"] for li in kind(docs, "Gateway")["spec"]["listeners"]}
    assert listeners == {"edge": 1975, "ai": 1976}
    assert kind(docs, "AIGatewayRoute")["spec"]["parentRefs"][0]["sectionName"] == "ai"
    edge = kind(docs, "HTTPRoute")
    assert edge["spec"]["parentRefs"][0]["sectionName"] == "edge"
    policy = kind(docs, "EnvoyExtensionPolicy")
    assert policy["spec"]["targetRefs"][0] == {
        "group": "gateway.networking.k8s.io",
        "kind": "HTTPRoute",
        "name": "edge",
    }
    ext = policy["spec"]["extProc"][0]
    assert ext["failOpen"] is False, "the guard must fail closed"
    assert ext["processingMode"]["request"]["body"] == "Buffered"


def test_fallback_region_uses_eu_profiles_and_eu_endpoints():
    docs = gc.build(
        ROUTES,
        ["claude-sonnet-5"],
        "eu-west-3",
        real_backend(),
        fallback=("eu-central-1", gc.Backend.for_region("eu-central-1")),
    )
    refs = kind(docs, "AIGatewayRoute")["spec"]["rules"][0]["backendRefs"]
    assert [(r["name"], r["priority"]) for r in refs] == [("bedrock-eu", 0), ("bedrock-eu-fallback", 1)]
    assert all(r["modelNameOverride"].startswith("eu.") for r in refs)
    regions = {
        d["metadata"]["name"]: d["spec"]["awsCredentials"]["region"]
        for d in docs
        if d["kind"] == "BackendSecurityPolicy"
    }
    assert regions == {"bedrock-eu": "eu-west-3", "bedrock-eu-fallback": "eu-central-1"}
    with pytest.raises(gc.ConfigError):
        gc.build(ROUTES, ["claude-sonnet-5"], "eu-west-3", real_backend(), fallback=("eu-west-3", real_backend()))


EU_BEDROCK = {
    f"bedrock-runtime.{r}.amazonaws.com"
    for r in ("eu-central-1", "eu-north-1", "eu-south-1", "eu-south-2", "eu-west-1", "eu-west-3")
}


def test_egress_allowlist():
    """E2.7: the gateway can only open connections to EU Bedrock endpoints, the guard and itself."""
    docs = gc.build(
        ROUTES,
        ["claude-sonnet-5", "claude-haiku-4-5"],
        "eu-west-3",
        real_backend(),
        guard=gc.GuardEndpoint("guard"),
        fallback=("eu-central-1", gc.Backend.for_region("eu-central-1")),
    )
    hosts = {e["fqdn"]["hostname"] for d in docs if d["kind"] == "Backend" for e in d["spec"]["endpoints"]}
    assert hosts - {"guard", "aigw"} <= EU_BEDROCK
    assert all(
        "ip" not in e and "unix" not in e for d in docs if d["kind"] == "Backend" for e in d["spec"]["endpoints"]
    )
    rendered = gc.render(docs)
    for forbidden in ("dynamic_forward_proxy", "DynamicResolver", '"type": "Dynamic'):
        assert forbidden not in rendered
    # every external backend is TLS-verified with the expected host name
    tls = {d["spec"]["validation"]["hostname"] for d in docs if d["kind"] == "BackendTLSPolicy"}
    assert tls == hosts - {"guard", "aigw"}
