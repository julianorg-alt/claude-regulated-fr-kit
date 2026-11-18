"""OAuth 2.1 tokens at the MCP proxy (backlog E8.3).

Inbound, the proxy is an OAuth protected resource: it accepts only access tokens whose audience is its
own canonical URI (RFC 8707 resource indicator; MCP authorization, verifications.md V50) and it
publishes its metadata at /.well-known/oauth-protected-resource (RFC 9728). A token issued for another
resource, a downstream MCP server for instance, is refused: accepting it is the "token passthrough"
anti-pattern.

Outbound, the proxy never forwards the agent's token. For each call it mints a short-lived credential
for the agent and for that one server (audience = the server's canonical URI), signed with the
proxy's own key; servers verify it against the proxy's JWKS.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

ALGORITHMS = ("RS256", "ES256")
MAX_DOWNSTREAM_TTL_S = 600


class TokenError(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass(frozen=True)
class Caller:
    agent: str
    subject: str
    claims: dict


class TokenVerifier:
    """Checks signature, issuer, expiry and that the audience is exactly this resource."""

    def __init__(self, *, issuer: str, audience: str, key_for: Callable[[str], object], agent_claim: str = "azp"):
        self.issuer, self.audience, self.agent_claim = issuer, audience, agent_claim
        self._key_for = key_for  # token -> verification key (a PyJWKClient's lookup, or a fixed key)

    def verify(self, authorization: str | None) -> Caller:
        if not authorization or not authorization.startswith("Bearer "):
            raise TokenError("token-missing")
        token = authorization[len("Bearer ") :].strip()
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in ALGORITHMS:
                raise TokenError("token-invalid", f"algorithm {header.get('alg')!r} not accepted")
            claims = jwt.decode(
                token,
                self._key_for(token),
                algorithms=list(ALGORITHMS),
                issuer=self.issuer,
                options={"require": ["exp", "iss", "aud", "sub"], "verify_aud": False},
            )
        except jwt.ExpiredSignatureError as error:
            raise TokenError("token-expired") from error
        except jwt.PyJWTError as error:
            raise TokenError("token-invalid", str(error)) from error
        aud = claims.get("aud")
        audiences = aud if isinstance(aud, list) else [aud]
        if audiences != [self.audience]:
            # Issued for another resource, or for several: not for this proxy alone.
            raise TokenError("token-audience", f"audience {aud!r} is not {self.audience!r}")
        agent = claims.get(self.agent_claim) or claims.get("client_id")
        if not isinstance(agent, str) or not agent:
            raise TokenError("token-invalid", f"no {self.agent_claim} claim naming the agent")
        return Caller(agent, claims["sub"], claims)


class TokenMinter:
    """Short-lived, per-agent, per-server credentials signed by the proxy (ES256)."""

    def __init__(self, *, issuer: str, ttl_s: int = 300, key: ec.EllipticCurvePrivateKey | None = None,
                 clock: Callable[[], float] = time.time):  # fmt: skip
        if not 0 < ttl_s <= MAX_DOWNSTREAM_TTL_S:
            raise ValueError(f"downstream token ttl must be between 1 and {MAX_DOWNSTREAM_TTL_S} s")
        self.issuer, self.ttl_s, self._clock = issuer, ttl_s, clock
        self._key = key or ec.generate_private_key(ec.SECP256R1())
        self.kid = secrets.token_hex(8)

    def mint(self, *, agent: str, subject: str, audience: str) -> str:
        now = int(self._clock())
        claims = {"iss": self.issuer, "sub": subject, "azp": agent, "aud": audience, "iat": now,
                  "exp": now + self.ttl_s, "jti": secrets.token_urlsafe(12)}  # fmt: skip
        return jwt.encode(claims, self._key, algorithm="ES256", headers={"kid": self.kid})

    def public_key(self):
        return self._key.public_key()

    def jwks(self) -> dict:
        jwk = jwt.algorithms.ECAlgorithm.to_jwk(self.public_key(), as_dict=True)
        return {"keys": [{**jwk, "kid": self.kid, "use": "sig", "alg": "ES256"}]}


def protected_resource_metadata(resource: str, authorization_servers: list[str], scopes: list[str]) -> dict:
    """RFC 9728 section 2 document served at /.well-known/oauth-protected-resource."""
    return {
        "resource": resource,
        "authorization_servers": authorization_servers,
        "bearer_methods_supported": ["header"],
        "scopes_supported": scopes,
        "resource_name": "crfr MCP proxy",
    }


def metadata_url(resource: str) -> str:
    """RFC 9728 section 3.1: the well-known segment goes between the host and the path of the resource."""
    parts = urlsplit(resource)
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, "/.well-known/oauth-protected-resource" + path, "", ""))


def www_authenticate(resource: str, error: str | None = None) -> str:
    """RFC 9728 section 5.1 challenge pointing the client at the metadata."""
    value = f'Bearer resource_metadata="{metadata_url(resource)}"'
    return value + (f', error="{error}"' if error else "")
