"""Guard configuration: identity claims, token quotas, monthly budgets, prices, OPA endpoint.

Prices are operator input (per million tokens, in the budget currency). The kit ships placeholder
values only: copy them from your AWS price list or contract, the kit never invents a price.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .usage import FIELDS, Usage

SCOPES = ("user", "team", "app")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Price:
    input_tokens: float
    output_tokens: float
    cache_read_input_tokens: float
    cache_creation_input_tokens: float

    def cost(self, usage: Usage) -> float:
        return sum(getattr(usage, f) * getattr(self, f) for f in FIELDS) / 1_000_000


@dataclass(frozen=True)
class Limits:
    """Default limit per scope, plus per-key overrides. None means no limit for that scope."""

    default: dict[str, float | None]
    overrides: dict[str, dict[str, float]] = field(default_factory=dict)

    def limit(self, scope: str, key: str) -> float | None:
        if key in self.overrides.get(scope, {}):
            return self.overrides[scope][key]
        return self.default.get(scope)


@dataclass(frozen=True)
class Config:
    user_claim: str
    app_claim: str
    team_prefix: str
    daily_tokens: Limits
    monthly_budget: Limits
    currency: str
    prices: dict[str, Price]
    opa_url: str
    opa_timeout_s: float
    max_buffer_bytes: int
    pseudonymisation: bool = False
    vault_ttl_s: float = 3600
    pseudonym_types: tuple[str, ...] | None = None
    audit_segment_s: int = 300
    content_log: bool = False
    content_retention_days: int = 7


def _limits(raw: dict, name: str) -> Limits:
    default = raw.get("default", {})
    overrides = raw.get("overrides", {})
    for scope in list(default) + list(overrides):
        if scope not in SCOPES:
            raise ConfigError(f"{name}: unknown scope {scope!r}")
    values = list(default.values()) + [v for o in overrides.values() for v in o.values()]
    for value in values:
        if value is not None and (not isinstance(value, int | float) or isinstance(value, bool) or value < 0):
            raise ConfigError(f"{name}: limits must be non-negative numbers or null")
    return Limits(dict(default), {s: dict(o) for s, o in overrides.items()})


def parse(raw: dict) -> Config:
    try:
        identity = raw["identity"]
        prices = {}
        for model, price in raw["prices"].items():
            missing = [f for f in FIELDS if f not in price]
            if missing:
                raise ConfigError(f"price of {model} lacks {', '.join(missing)}")
            if any(not isinstance(price[f], int | float) or price[f] < 0 for f in FIELDS):
                raise ConfigError(f"price of {model} must be non-negative numbers")
            prices[model] = Price(**{f: float(price[f]) for f in FIELDS})
        audit = raw.get("audit", {})
        content = audit.get("content", {})
        if content.get("enabled") and not raw.get("pseudonymisation", {}).get("enabled"):
            raise ConfigError("audit.content needs pseudonymisation.enabled: it would otherwise keep personal data")
        retention = int(content.get("retention_days", 7))
        if not 1 <= retention <= 30:
            raise ConfigError("audit.content.retention_days must be between 1 and 30")
        segment = int(audit.get("segment_s", 300))
        if not 1 <= segment <= 86400:
            raise ConfigError("audit.segment_s must be between 1 and 86400")
        return Config(
            user_claim=identity.get("user_claim", "preferred_username"),
            app_claim=identity.get("app_claim", "azp"),
            team_prefix=identity.get("team_prefix", "team-"),
            daily_tokens=_limits(raw["quotas"]["daily_tokens"], "quotas.daily_tokens"),
            monthly_budget=_limits(raw["budgets"]["monthly"], "budgets.monthly"),
            currency=raw["budgets"]["currency"],
            prices=prices,
            opa_url=raw["opa"]["url"],
            opa_timeout_s=float(raw["opa"].get("timeout_s", 2)),
            max_buffer_bytes=int(raw.get("max_buffer_bytes", 8 * 1024 * 1024)),
            pseudonymisation=bool(raw.get("pseudonymisation", {}).get("enabled", False)),
            vault_ttl_s=float(raw.get("pseudonymisation", {}).get("ttl_s", 3600)),
            pseudonym_types=tuple(raw["pseudonymisation"]["types"])
            if raw.get("pseudonymisation", {}).get("types")
            else None,
            audit_segment_s=segment,
            content_log=bool(content.get("enabled", False)),
            content_retention_days=retention,
        )
    except KeyError as error:
        raise ConfigError(f"missing configuration key {error}") from error


def load(path: Path) -> Config:
    return parse(json.loads(path.read_text(encoding="utf-8")))
