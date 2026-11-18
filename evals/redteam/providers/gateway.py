"""promptfoo provider that sends each red team prompt through the local gateway (backlog E7.1).

It runs in the `e2e` CI job, against the stack of `make up`: the gateway in front of the fake Bedrock.
The output is a JSON object the assertions read: the HTTP status, the refusal reason of the guard,
the answer text, and whether any of the test's `needles` reached the fake Bedrock (its request log).
Standard library only; the stack's URLs come from CRFR_GATEWAY and CRFR_KEYCLOAK.
"""

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

GATEWAY = os.environ.get("CRFR_GATEWAY", f"http://127.0.0.1:{os.environ.get('CRFR_GATEWAY_PORT', '1975')}")
KEYCLOAK = os.environ.get("CRFR_KEYCLOAK", f"http://127.0.0.1:{os.environ.get('CRFR_KEYCLOAK_PORT', '8081')}")
COMPOSE = ["docker", "compose", "-f", str(Path(__file__).resolve().parents[3] / "gateway" / "compose.yaml")]
_TOKENS: dict[str, str] = {}


def token(user: str) -> str:
    if user not in _TOKENS:
        data = urllib.parse.urlencode(
            {
                "grant_type": "password",
                "client_id": "demo-app",
                "client_secret": "local-demo-only-not-a-secret",
                "username": user,
                "password": "local-demo-only",
            }  # fmt: skip
        ).encode()
        url = f"{KEYCLOAK}/realms/crfr/protocol/openid-connect/token"
        with urllib.request.urlopen(urllib.request.Request(url, data), timeout=15) as response:  # noqa: S310
            _TOKENS[user] = json.load(response)["access_token"]
    return _TOKENS[user]


def bedrock_log() -> str:
    run = subprocess.run(  # noqa: S603
        [*COMPOSE, "exec", "-T", "fake-bedrock", "cat", "/data/requests.jsonl"],
        check=False, capture_output=True, text=True,
    )  # fmt: skip
    return run.stdout


def call_api(prompt, options, context):
    v = (context or {}).get("vars", {})
    payload = {"model": v.get("model", "claude-sonnet-5"), "messages": [{"role": "user", "content": prompt}]}
    if v.get("max_tokens", 256) is not None:
        payload["max_tokens"] = v.get("max_tokens", 256)
    if v.get("pad_bytes"):
        payload["metadata_pad"] = "x" * int(v["pad_bytes"])
    headers = {"content-type": "application/json", "anthropic-version": "2023-06-01"}
    auth = v.get("auth", "valid")
    if auth == "valid":
        headers["authorization"] = f"Bearer {token(v.get('user', 'alice'))}"
    elif auth == "tampered":
        head, body, _ = token(v.get("user", "alice")).split(".")
        headers["authorization"] = f"Bearer {head}.{body}.c2lnbmF0dXJlLWZhbHNpZmllZQ"
    request = urllib.request.Request(f"{GATEWAY}/anthropic/v1/messages", json.dumps(payload).encode(), headers)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            status, doc = response.status, json.load(response)
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
        try:
            doc = json.loads(raw)
        except ValueError:
            doc = {"raw": raw.decode(errors="replace")}
    message = (doc.get("error") or {}).get("message", "") if isinstance(doc, dict) else ""
    text = " ".join(b.get("text", "") for b in doc.get("content", []) if isinstance(b, dict)) if status == 200 else ""
    needles = [n for n in str(v.get("needles") or "").split("|") if n]
    upstream = bedrock_log() if needles else ""
    leaked = sorted(n for n in needles if n in upstream)
    return {"output": json.dumps({"status": status, "reason": message.split(":")[0], "text": text, "leaked": leaked})}
