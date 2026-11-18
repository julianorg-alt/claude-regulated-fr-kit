"""Caller identity, read from the bearer token that Envoy's jwt_authn filter has already verified.

The guard sits after ``jwt_authn`` in the filter chain (checked by the end-to-end tests: a missing or
tampered token is refused with 401 before the guard is called), so it only decodes the payload. It never
sends the token or any claim upstream.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass


class IdentityError(ValueError):
    pass


@dataclass(frozen=True)
class Identity:
    user: str
    app: str
    groups: tuple[str, ...]
    team: str | None

    def keys(self) -> dict[str, str]:
        """Scope -> key, for quotas, budgets and kill switches."""
        out = {"user": self.user, "app": self.app}
        if self.team:
            out["team"] = self.team
        return out


def _payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise IdentityError("bearer token is not a JWT")
    raw = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw))
    except (ValueError, json.JSONDecodeError) as error:
        raise IdentityError("unreadable JWT payload") from error
    if not isinstance(payload, dict):
        raise IdentityError("JWT payload is not an object")
    return payload


def from_authorization(header: str | None, user_claim: str, app_claim: str, team_prefix: str) -> Identity:
    if not header or not header.lower().startswith("bearer "):
        raise IdentityError("missing bearer token")
    claims = _payload(header.split(" ", 1)[1].strip())
    user, app = claims.get(user_claim), claims.get(app_claim)
    if not isinstance(user, str) or not user or not isinstance(app, str) or not app:
        raise IdentityError(f"token lacks {user_claim!r} or {app_claim!r}")
    groups = claims.get("groups") or []
    if not isinstance(groups, list) or not all(isinstance(g, str) for g in groups):
        raise IdentityError("groups claim must be a list of strings")
    teams = sorted(g for g in groups if g.startswith(team_prefix))
    # A user in several teams is charged to the first one in alphabetical order: deterministic, documented.
    return Identity(user=user, app=app, groups=tuple(sorted(groups)), team=teams[0] if teams else None)
