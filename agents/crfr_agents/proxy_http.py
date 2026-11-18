"""HTTP front of the MCP proxy (backlog E8.2).

Routes: POST /mcp/<server> (JSON-RPC to a registered server), GET the RFC 9728 metadata at
/.well-known/oauth-protected-resource<resource path>, GET /jwks.json (keys servers use to check the
credentials the proxy mints). Requests are limited to MAX_BODY bytes. Run it behind a TLS terminator.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from crfr_agents.proxy import McpProxy
from crfr_agents.tokens import metadata_url

MAX_BODY = 1024 * 1024


def make_server(proxy: McpProxy, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    resource_path = urlsplit(proxy.resource).path.rstrip("/")
    metadata_path = urlsplit(metadata_url(proxy.resource)).path

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):  # the call log is the record
            pass

        def _reply(self, status: int, doc: dict | None, headers: dict[str, str] | None = None) -> None:
            raw = json.dumps(doc, ensure_ascii=False).encode() if doc is not None else b""
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):  # noqa: N802
            if self.path == metadata_path:
                return self._reply(200, proxy.metadata())
            if self.path == "/jwks.json":
                return self._reply(200, proxy.minter.jwks())
            return self._reply(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            prefix = resource_path + "/"
            if not self.path.startswith(prefix) or "/" in self.path[len(prefix) :]:
                return self._reply(404, {"error": "not found"})
            length = int(self.headers.get("content-length") or 0)
            if length <= 0 or length > MAX_BODY:
                return self._reply(413 if length > MAX_BODY else 400, {"error": "body size"})
            try:
                message = json.loads(self.rfile.read(length))
            except ValueError:
                return self._reply(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse"}})
            response = proxy.handle(self.path[len(prefix) :], dict(self.headers.items()), message)
            self._reply(response.status, response.body, response.headers)

    return ThreadingHTTPServer((host, port), Handler)
