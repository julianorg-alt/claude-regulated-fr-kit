"""Generate the Envoy AI Gateway configuration from the residency inventory (backlog E2).

Only models that have an allowed route in ``infra/inventory/routes-*.json`` become routable,
so the gateway cannot expose a model that would leave the EU: the inventory is the single source
of truth for Terraform (IAM) and for the gateway. Output is a multi-document YAML file where each
document is written as JSON (valid YAML, no PyYAML dependency).

Clients call ``POST /anthropic/v1/messages`` with a short model alias such as ``claude-sonnet-5``;
the gateway rewrites it to the ``eu.`` inference profile and signs the request with SigV4 for the
source Region.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

NAMESPACE = "default"
GATEWAY = "crfr"
LISTENER_PORT = 1975
AI_LISTENER_PORT = 1976
# Headers that would tell Bedrock who called or from where (the client IP is personal data).
# The x-ai-eg-* headers are the gateway's own routing state: required internally, no personal data.
STRIPPED_UPSTREAM_HEADERS = (
    "x-forwarded-for",
    "x-envoy-external-address",
    "x-forwarded-host",
    "x-real-ip",
    "forwarded",
)


class ConfigError(ValueError):
    pass


def alias_of(model_name: str) -> str:
    """'Claude Haiku 4.5' -> 'claude-haiku-4-5'."""
    alias = re.sub(r"[^a-z0-9]+", "-", model_name.lower()).strip("-")
    if not alias.startswith("claude-"):
        raise ConfigError(f"unexpected model name {model_name!r}")
    return alias


@dataclass(frozen=True)
class Backend:
    host: str
    port: int
    tls: bool

    @classmethod
    def for_region(cls, region: str) -> Backend:
        return cls(f"bedrock-runtime.{region}.amazonaws.com", 443, True)


@dataclass(frozen=True)
class Auth:
    issuer: str
    jwks_uri: str
    audiences: tuple[str, ...]
    required_claim: str | None = None  # claim name that must be present, for example "groups"


@dataclass(frozen=True)
class GuardEndpoint:
    """The policy sidecar (gateway/guard), called as an Envoy external processor (E2.4 to E2.6)."""

    host: str
    port: int = 9002
    self_host: str = "aigw"  # how the edge listener reaches the inner AI listener of the same Envoy


@dataclass(frozen=True)
class ExitProvider:
    """Second provider reached through an OpenAI-compatible API (backlog E10.1, DORA article 28(8) exit plan).

    ``models`` maps a gateway alias (which must already have an EU Bedrock route) to the provider's model id.
    """

    name: str
    backend: Backend
    models: dict[str, str]
    prefix: str = "/v1"
    credentials_secret: str = "exit-provider-credentials"  # noqa: S105 (name of a Secret object, not a value)

    @property
    def backend_name(self) -> str:
        return f"exit-{self.name}"


EXIT_MODES = ("standby", "switch")


def select_routes(routes: list[dict], models: list[str], source_region: str) -> list[dict]:
    wanted = {m.lower() for m in models}
    chosen = {}
    for route in routes:
        if route["mode"] != "geo" or route["source_region"] != source_region:
            continue
        name = route["model"]
        if name.lower() in wanted or alias_of(name) in wanted:
            chosen[name] = route
    missing = sorted(wanted - {n.lower() for n in chosen} - {alias_of(n) for n in chosen})
    if missing:
        raise ConfigError(f"no EU geo route from {source_region} for: {', '.join(missing)}")
    return [chosen[n] for n in sorted(chosen)]


def build(
    routes: list[dict],
    models: list[str],
    source_region: str,
    backend: Backend,
    credentials_secret: str = "bedrock-eu-credentials",  # noqa: S107 (name of a Secret object, not a value)
    auth: Auth | None = None,
    guard: GuardEndpoint | None = None,
    fallback: tuple[str, Backend] | None = None,
    exit_provider: ExitProvider | None = None,
    exit_mode: str = "standby",
) -> list[dict]:
    """``exit_mode``: "standby" adds ``exit-<alias>`` routes next to the Bedrock ones (drills, regression replay);
    "switch" sends the aliases themselves to the exit provider (the exit itself). Never an automatic failover:
    changing processor is a decision recorded in the DORA register, not a retry."""
    if exit_mode not in EXIT_MODES:
        raise ConfigError(f"exit mode must be one of {', '.join(EXIT_MODES)}")
    selected = select_routes(routes, models, source_region)
    exit_aliases: dict[str, str] = {}
    if exit_provider:
        known = {alias_of(r["model"]) for r in selected}
        unknown = sorted(set(exit_provider.models) - known)
        if unknown:
            raise ConfigError(f"exit provider models without an EU Bedrock route: {', '.join(unknown)}")
        exit_aliases = dict(exit_provider.models)
    fallback_routes = {}
    if fallback:
        fallback_region, _ = fallback
        if fallback_region == source_region:
            raise ConfigError("the fallback Region must differ from the source Region")
        fallback_routes = {r["model"]: r for r in select_routes(routes, models, fallback_region)}
    # With a guard, Envoy runs two listeners: "edge" (clients, guard ext_proc) forwards to "ai" (AI Gateway).
    # Envoy AI Gateway inserts its own ext_proc first in the chain of its listener and reads the request
    # body before any other filter, so a filter that rewrites the body (pseudonymisation, E3.5) must run on
    # a listener in front of it. Both listeners require the corporate JWT.
    listeners = [{"name": "http", "protocol": "HTTP", "port": LISTENER_PORT}]
    ai_parent = {"name": GATEWAY, "kind": "Gateway", "group": "gateway.networking.k8s.io"}
    if guard:
        listeners = [
            {"name": "edge", "protocol": "HTTP", "port": LISTENER_PORT},
            {"name": "ai", "protocol": "HTTP", "port": AI_LISTENER_PORT},
        ]
        ai_parent = {**ai_parent, "sectionName": "ai"}

    def refs(route: dict) -> list[dict]:
        alias = alias_of(route["model"])
        if exit_provider and exit_mode == "switch" and alias in exit_aliases:
            return [{"name": exit_provider.backend_name, "modelNameOverride": exit_aliases[alias]}]
        out = [{"name": "bedrock-eu", "modelNameOverride": route["profile"]}]
        if fallback:
            out[0]["priority"] = 0
            out.append(
                {"name": "bedrock-eu-fallback", "modelNameOverride": fallback_routes[route["model"]]["profile"],
                 "priority": 1}
            )  # fmt: skip
        return out

    docs: list[dict] = [
        {
            "apiVersion": "gateway.networking.k8s.io/v1",
            "kind": "GatewayClass",
            "metadata": {"name": GATEWAY},
            "spec": {"controllerName": "gateway.envoyproxy.io/gatewayclass-controller"},
        },
        {
            "apiVersion": "gateway.networking.k8s.io/v1",
            "kind": "Gateway",
            "metadata": {"name": GATEWAY, "namespace": NAMESPACE},
            "spec": {
                "gatewayClassName": GATEWAY,
                "listeners": listeners,
            },
        },
        {
            "apiVersion": "aigateway.envoyproxy.io/v1beta1",
            "kind": "AIGatewayRoute",
            "metadata": {"name": GATEWAY, "namespace": NAMESPACE},
            "spec": {
                "parentRefs": [ai_parent],
                "rules": [
                    {
                        "matches": [
                            {"headers": [{"type": "Exact", "name": "x-ai-eg-model", "value": alias_of(r["model"])}]}
                        ],
                        "backendRefs": refs(r),
                    }
                    for r in selected
                ]
                + [
                    {
                        "matches": [{"headers": [{"type": "Exact", "name": "x-ai-eg-model", "value": f"exit-{a}"}]}],
                        "backendRefs": [{"name": exit_provider.backend_name, "modelNameOverride": m}],
                    }
                    for a, m in sorted(exit_aliases.items())
                    if exit_mode == "standby"
                ],
            },
        },
        {
            # Credentials are injected from the environment at start-up, never stored in the repo.
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": credentials_secret, "namespace": NAMESPACE},
            "type": "Opaque",
            "stringData": {
                "credentials": "[default]\n"
                "aws_access_key_id = ${AWS_ACCESS_KEY_ID}\n"
                "aws_secret_access_key = ${AWS_SECRET_ACCESS_KEY}\n"
            },
        },
    ]
    docs += bedrock_backend("bedrock-eu", source_region, backend, credentials_secret)
    if fallback:
        docs += bedrock_backend("bedrock-eu-fallback", fallback[0], fallback[1], credentials_secret)
        docs.append(
            {
                # One attempt per priority: on a 5xx or a connection failure, the next call goes to the
                # fallback Region (still an eu. profile, still EU destinations).
                "apiVersion": "gateway.envoyproxy.io/v1alpha1",
                "kind": "BackendTrafficPolicy",
                "metadata": {"name": "bedrock-eu-fallback", "namespace": NAMESPACE},
                "spec": {
                    "targetRefs": [{"group": "gateway.networking.k8s.io", "kind": "HTTPRoute", "name": GATEWAY}],
                    "retry": {
                        "numAttemptsPerPriority": 1,
                        "numRetries": 1,
                        "retryOn": {"httpStatusCodes": [500, 502, 503], "triggers": ["connect-failure",
                                                                                     "retriable-status-codes"]},
                    },
                },
            }
        )  # fmt: skip
    if exit_provider:
        docs += exit_backend(exit_provider)
    docs.append(
        {
            # Envoy derives x-envoy-external-address (the client IP, personal data under the GDPR)
            # from the connection. Reading the client address from a header the edge never sends
            # leaves Envoy without an external address to forward, and XFF is not appended.
            "apiVersion": "gateway.envoyproxy.io/v1alpha1",
            "kind": "ClientTrafficPolicy",
            "metadata": {"name": "no-client-address-upstream", "namespace": NAMESPACE},
            "spec": {
                "targetRefs": [{"group": "gateway.networking.k8s.io", "kind": "Gateway", "name": GATEWAY}],
                "clientIPDetection": {"xForwardedFor": {"numTrustedHops": 0, "disableXForwardedForAppend": True}},
                "headers": {"earlyRequestHeaders": {"remove": list(STRIPPED_UPSTREAM_HEADERS)}},
            },
        }
    )
    if auth:
        provider = {
            "name": "corporate-idp",
            "issuer": auth.issuer,
            "audiences": list(auth.audiences),
            "remoteJWKS": {"uri": auth.jwks_uri},
            # No claimToHeaders: identity claims must not travel to Bedrock. The audit log (E5)
            # reads them from the gateway side.
        }
        security = {
            "apiVersion": "gateway.envoyproxy.io/v1alpha1",
            "kind": "SecurityPolicy",
            "metadata": {"name": "require-corporate-jwt", "namespace": NAMESPACE},
            "spec": {
                "targetRefs": [{"group": "gateway.networking.k8s.io", "kind": "Gateway", "name": GATEWAY}],
                "jwt": {"providers": [provider]},
            },
        }
        if auth.required_claim:
            security["spec"]["authorization"] = {
                "defaultAction": "Deny",
                "rules": [
                    {
                        "name": f"require-{auth.required_claim}",
                        "action": "Allow",
                        "principal": {
                            "jwt": {
                                "provider": "corporate-idp",
                                "claims": [
                                    {
                                        "name": auth.required_claim,
                                        "valueType": "StringArray",
                                        "values": ["claude-users"],
                                    }
                                ],
                            }
                        },
                    }
                ],
            }
        docs.append(security)
    if guard:
        docs += guard_docs(guard)
    return docs


def bedrock_backend(name: str, region: str, backend: Backend, credentials_secret: str) -> list[dict]:
    docs = [
        {
            "apiVersion": "aigateway.envoyproxy.io/v1beta1",
            "kind": "AIServiceBackend",
            "metadata": {"name": name, "namespace": NAMESPACE},
            "spec": {
                "schema": {"name": "AWSAnthropic", "version": "bedrock-2023-05-31"},
                # The client IP is personal data (GDPR): never send it to the model provider.
                "headerMutation": {"remove": list(STRIPPED_UPSTREAM_HEADERS)},
                "backendRef": {"name": name, "kind": "Backend", "group": "gateway.envoyproxy.io"},
            },
        },
        {
            "apiVersion": "aigateway.envoyproxy.io/v1beta1",
            "kind": "BackendSecurityPolicy",
            "metadata": {"name": name, "namespace": NAMESPACE},
            "spec": {
                "targetRefs": [{"group": "aigateway.envoyproxy.io", "kind": "AIServiceBackend", "name": name}],
                "type": "AWSCredentials",
                "awsCredentials": {"region": region, "credentialsFile": {"secretRef": {"name": credentials_secret}}},
            },
        },
        {
            "apiVersion": "gateway.envoyproxy.io/v1alpha1",
            "kind": "Backend",
            "metadata": {"name": name, "namespace": NAMESPACE},
            "spec": {"endpoints": [{"fqdn": {"hostname": backend.host, "port": backend.port}}]},
        },
    ]
    if backend.tls:
        docs.append(
            {
                "apiVersion": "gateway.networking.k8s.io/v1",
                "kind": "BackendTLSPolicy",
                "metadata": {"name": f"{name}-tls", "namespace": NAMESPACE},
                "spec": {
                    "targetRefs": [{"group": "gateway.envoyproxy.io", "kind": "Backend", "name": name}],
                    "validation": {"wellKnownCACertificates": "System", "hostname": backend.host},
                },
            }
        )
    return docs


def exit_backend(exit_provider: ExitProvider) -> list[dict]:
    name, backend = exit_provider.backend_name, exit_provider.backend
    docs = [
        {
            "apiVersion": "aigateway.envoyproxy.io/v1beta1",
            "kind": "AIServiceBackend",
            "metadata": {"name": name, "namespace": NAMESPACE},
            "spec": {
                # Envoy AI Gateway translates the Anthropic Messages request to this schema (V65).
                "schema": {"name": "OpenAI", "prefix": exit_provider.prefix},
                "headerMutation": {"remove": list(STRIPPED_UPSTREAM_HEADERS)},
                "backendRef": {"name": name, "kind": "Backend", "group": "gateway.envoyproxy.io"},
            },
        },
        {
            "apiVersion": "aigateway.envoyproxy.io/v1beta1",
            "kind": "BackendSecurityPolicy",
            "metadata": {"name": name, "namespace": NAMESPACE},
            "spec": {
                "targetRefs": [{"group": "aigateway.envoyproxy.io", "kind": "AIServiceBackend", "name": name}],
                "type": "APIKey",
                "apiKey": {"secretRef": {"name": exit_provider.credentials_secret}},
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": exit_provider.credentials_secret, "namespace": NAMESPACE},
            "type": "Opaque",
            "stringData": {"apiKey": "${EXIT_PROVIDER_API_KEY}"},
        },
        {
            "apiVersion": "gateway.envoyproxy.io/v1alpha1",
            "kind": "Backend",
            "metadata": {"name": name, "namespace": NAMESPACE},
            "spec": {"endpoints": [{"fqdn": {"hostname": backend.host, "port": backend.port}}]},
        },
    ]
    if backend.tls:
        docs.append(
            {
                "apiVersion": "gateway.networking.k8s.io/v1",
                "kind": "BackendTLSPolicy",
                "metadata": {"name": f"{name}-tls", "namespace": NAMESPACE},
                "spec": {
                    "targetRefs": [{"group": "gateway.envoyproxy.io", "kind": "Backend", "name": name}],
                    "validation": {"wellKnownCACertificates": "System", "hostname": backend.host},
                },
            }
        )
    return docs


def load_exit_provider(path: Path, provider_id: str, host: str | None, models: dict[str, str]) -> ExitProvider:
    """Only providers listed in the inventory are accepted, and only on the host the inventory names."""
    entries = {e["id"]: e for e in json.loads(path.read_text(encoding="utf-8"))["providers"]}
    if provider_id not in entries:
        raise ConfigError(f"exit provider {provider_id!r} is not in the inventory ({', '.join(sorted(entries))})")
    entry = entries[provider_id]
    if entry["host"] and host and host != entry["host"]:
        raise ConfigError(f"host {host!r} is not the inventory host of {provider_id} ({entry['host']})")
    chosen = entry["host"] or host
    if not chosen or not re.fullmatch(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?", chosen) or "." not in chosen:
        raise ConfigError(f"exit provider {provider_id} needs a DNS host name (--exit-host)")
    if not models:
        raise ConfigError("give at least one --exit-model alias=model")
    return ExitProvider(provider_id, Backend(chosen, entry["port"], entry["tls"]), models)


def guard_docs(guard: GuardEndpoint) -> list[dict]:
    return [
        {
            "apiVersion": "gateway.envoyproxy.io/v1alpha1",
            "kind": "Backend",
            "metadata": {"name": "guard", "namespace": NAMESPACE},
            "spec": {
                "appProtocols": ["gateway.envoyproxy.io/h2c"],
                "endpoints": [{"fqdn": {"hostname": guard.host, "port": guard.port}}],
            },
        },
        {
            "apiVersion": "gateway.envoyproxy.io/v1alpha1",
            "kind": "Backend",
            "metadata": {"name": "ai-listener", "namespace": NAMESPACE},
            "spec": {"endpoints": [{"fqdn": {"hostname": guard.self_host, "port": AI_LISTENER_PORT}}]},
        },
        {
            "apiVersion": "gateway.networking.k8s.io/v1",
            "kind": "HTTPRoute",
            "metadata": {"name": "edge", "namespace": NAMESPACE},
            "spec": {
                "parentRefs": [{"name": GATEWAY, "sectionName": "edge"}],
                "rules": [
                    {
                        "matches": [{"path": {"type": "PathPrefix", "value": "/anthropic/"}}],
                        "backendRefs": [
                            {
                                "group": "gateway.envoyproxy.io",
                                "kind": "Backend",
                                "name": "ai-listener",
                                "port": AI_LISTENER_PORT,
                            }
                        ],
                    }
                ],
            },
        },  # fmt: skip
        {
            "apiVersion": "gateway.envoyproxy.io/v1alpha1",
            "kind": "EnvoyExtensionPolicy",
            "metadata": {"name": "guard", "namespace": NAMESPACE},
            "spec": {
                "targetRefs": [{"group": "gateway.networking.k8s.io", "kind": "HTTPRoute", "name": "edge"}],
                "extProc": [
                    {
                        "backendRefs": [
                            {"group": "gateway.envoyproxy.io", "kind": "Backend", "name": "guard", "port": guard.port}
                        ],
                        # Buffered request: the guard needs the whole body to decide. Streamed response:
                        # answers flow to the client as they come, the guard counts tokens on the way.
                        "processingMode": {"request": {"body": "Buffered"}, "response": {"body": "Streamed"}},
                        # Fail closed: if the guard is down, no call reaches Bedrock.
                        "failOpen": False,
                        "messageTimeout": "5s",
                    }
                ],
            },
        },
    ]


def render(docs: list[dict]) -> str:
    header = "# Generated by tools/crfr/gateway_config.py from the residency inventory. Do not edit.\n"
    return header + "".join("---\n" + json.dumps(d, indent=2) + "\n" for d in docs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--routes", type=Path, required=True)
    parser.add_argument("--models", required=True, help="comma-separated aliases or names")
    parser.add_argument("--source-region", default="eu-west-3")
    parser.add_argument("--backend-host", help="override the Bedrock host (local fake Bedrock)")
    parser.add_argument("--backend-port", type=int, default=443)
    parser.add_argument("--backend-plaintext", action="store_true", help="no TLS to the backend (local demo only)")
    parser.add_argument("--jwt-issuer")
    parser.add_argument("--jwt-jwks-uri")
    parser.add_argument("--jwt-audience", action="append", default=[])
    parser.add_argument(
        "--jwt-required-group", action="store_true", help="require groups claim to contain claude-users"
    )
    parser.add_argument("--guard-host", help="host of the guard ext_proc service (enables the edge listener)")
    parser.add_argument("--guard-port", type=int, default=9002)
    parser.add_argument("--self-host", default="aigw", help="host name of this gateway, for the edge -> ai hop")
    parser.add_argument("--fallback-region", help="second EU source Region, used when the first one fails")
    parser.add_argument(
        "--exit-provider", help="second provider of the exit route, from infra/inventory/exit-providers.json"
    )
    parser.add_argument("--exit-host", help="host of a self-hosted exit provider (inventory entries without a host)")
    parser.add_argument("--exit-model", action="append", default=[], help="alias=provider-model, repeatable")
    parser.add_argument("--exit-mode", choices=EXIT_MODES, default="standby")
    parser.add_argument(
        "--exit-inventory",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "infra/inventory/exit-providers.json",
    )
    parser.add_argument(
        "--exit-plaintext", action="store_true", help="local fake exit provider only: needs --exit-host"
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    routes = json.loads(args.routes.read_text(encoding="utf-8"))["routes"]
    if args.backend_host:
        backend = Backend(args.backend_host, args.backend_port, not args.backend_plaintext)
    else:
        if args.backend_plaintext:
            parser.error("--backend-plaintext is only allowed with a local --backend-host")
        backend = Backend.for_region(args.source_region)
    auth = None
    if args.jwt_issuer or args.jwt_jwks_uri:
        if not (args.jwt_issuer and args.jwt_jwks_uri and args.jwt_audience):
            parser.error("--jwt-issuer, --jwt-jwks-uri and --jwt-audience go together")
        auth = Auth(
            args.jwt_issuer, args.jwt_jwks_uri, tuple(args.jwt_audience), "groups" if args.jwt_required_group else None
        )
    guard = GuardEndpoint(args.guard_host, args.guard_port, args.self_host) if args.guard_host else None
    fallback = None
    if args.fallback_region:
        if args.backend_host:
            parser.error("--fallback-region is for real Bedrock endpoints only")
        fallback = (args.fallback_region, Backend.for_region(args.fallback_region))
    exit_provider = None
    try:
        if args.exit_provider:
            pairs = dict(item.split("=", 1) for item in args.exit_model if "=" in item)
            if args.exit_plaintext:
                if not args.exit_host:
                    raise ConfigError("--exit-plaintext needs --exit-host (local fake provider)")
                exit_provider = ExitProvider(args.exit_provider, Backend(args.exit_host, 8080, False), pairs)
            else:
                exit_provider = load_exit_provider(args.exit_inventory, args.exit_provider, args.exit_host, pairs)
        docs = build(
            routes,
            [m.strip() for m in args.models.split(",") if m.strip()],
            args.source_region,
            backend,
            auth=auth,
            guard=guard,
            fallback=fallback,
            exit_provider=exit_provider,
            exit_mode=args.exit_mode,
        )
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1
    args.out.write_text(render(docs), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
