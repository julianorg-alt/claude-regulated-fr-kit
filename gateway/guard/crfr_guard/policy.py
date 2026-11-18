"""Client of the OPA decision API (backlog E2.5). Any failure is a refusal: the guard fails closed."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


class PolicyUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class PolicyDecision:
    allow: bool
    reasons: tuple[str, ...]


class OpaClient:
    def __init__(self, url: str, timeout_s: float):
        if not url.startswith(("http://", "https://")):
            raise ValueError("OPA URL must be http(s)")
        self.url, self.timeout_s = url, timeout_s

    def decide(self, policy_input: dict) -> PolicyDecision:
        data = json.dumps({"input": policy_input}).encode()
        request = urllib.request.Request(self.url, data, {"content-type": "application/json"})  # noqa: S310 (URL checked to be http(s) in __init__)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:  # noqa: S310 (fixed URL)
                result = json.load(response).get("result")
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise PolicyUnavailable(str(error)) from error
        if not isinstance(result, dict) or not isinstance(result.get("allow"), bool):
            raise PolicyUnavailable("OPA returned no decision: is the policy loaded?")
        reasons = result.get("reasons") or []
        return PolicyDecision(result["allow"], tuple(str(r) for r in reasons))
