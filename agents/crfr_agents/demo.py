"""Demo MCP server of the kit (tests and local demo of the MCP proxy).

It serves three tools of a fictitious case management system and checks the credential the proxy
mints: signature against the proxy key, issuer, expiry, and an audience equal to its own URI. A token
issued for anything else, the agent's token to the proxy included, gets 401. `served` lets a test make
the server change a description after it was pinned.
"""

from __future__ import annotations

import copy
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import jwt

TOOLS = [
    {
        "name": "lire_dossier",
        "description": "Lit un dossier client par son identifiant.",
        "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    },
    {
        "name": "modifier_adresse",
        "description": "Modifie l'adresse postale d'un client.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "adresse": {"type": "string"}},
            "required": ["id", "adresse"],
        },
    },
    {
        "name": "envoyer_courriel",
        "description": "Envoie un courriel depuis la boîte du service.",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "string"}, "objet": {"type": "string"}, "corps": {"type": "string"}},
            "required": ["a", "objet", "corps"],
        },
    },
]


class DemoServer:
    def __init__(self, *, url: str, issuer: str, public_key):
        self.url, self.issuer, self._key = url, issuer, public_key
        self.served = copy.deepcopy(TOOLS)
        self.received: list[dict] = []  # every accepted call: authorization header, method, params

    def authorize(self, authorization: str | None) -> dict | None:
        if not authorization or not authorization.startswith("Bearer "):
            return None
        try:
            return jwt.decode(authorization[7:], self._key, algorithms=["ES256"], audience=self.url,
                              issuer=self.issuer, options={"require": ["exp", "aud", "iss", "sub"]})  # fmt: skip
        except jwt.PyJWTError:
            return None

    def __call__(self, url: str, headers: dict[str, str], message: dict) -> tuple[int, dict | None, dict]:
        claims = self.authorize(headers.get("authorization"))
        if claims is None:
            return 401, {"error": "invalid_token"}, {}
        self.received.append({"authorization": headers["authorization"], "claims": claims, **message})
        rid, method, params = message.get("id"), message.get("method"), message.get("params") or {}
        if method == "initialize":
            result = {"protocolVersion": "2026-07-28", "capabilities": {"tools": {}},
                      "serverInfo": {"name": "demo-dossiers", "version": "1"}}  # fmt: skip
        elif method == "tools/list":
            result = {"tools": self.served}
        elif method == "tools/call":
            args = params.get("arguments") or {}
            text = {"lire_dossier": f"Dossier {args.get('id')} : contenu fictif.",
                    "modifier_adresse": "Adresse modifiée.", "envoyer_courriel": "Courriel envoyé."}  # fmt: skip
            result = {"content": [{"type": "text", "text": text.get(params.get("name"), "?")}], "isError": False}
        else:
            return 200, {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not found"}}, {}
        return 200, {"jsonrpc": "2.0", "id": rid, "result": result}, {"content-type": "application/json"}

    def serve(self, port: int = 0) -> ThreadingHTTPServer:
        """Same server over HTTP on 127.0.0.1 (caller runs serve_forever in a thread)."""
        demo = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):  # quiet
                pass

            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
                status, doc, _ = demo(demo.url, {k.lower(): v for k, v in self.headers.items()}, body)
                raw = json.dumps(doc or {}).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        return ThreadingHTTPServer(("127.0.0.1", port), Handler)
