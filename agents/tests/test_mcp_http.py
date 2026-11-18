"""The MCP proxy over HTTP, in front of the demo server over HTTP (backlog E8.2)."""

import json
import threading
import urllib.error
import urllib.request

import pytest
from conftest import Env
from crfr_agents.demo import DemoServer
from crfr_agents.proxy_http import make_server
from crfr_agents.registry import Registry, Server


@pytest.fixture
def stack(tmp_path):
    env = Env(tmp_path)
    demo = DemoServer(url="", issuer=env.minter.issuer, public_key=env.minter.public_key())
    upstream = demo.serve()
    demo.url = f"http://127.0.0.1:{upstream.server_address[1]}/mcp"
    pinned = env.registry.server("dossiers")
    env.proxy.registry = Registry({"dossiers": Server("dossiers", demo.url, pinned.tools)})
    from crfr_agents.proxy import http_send

    env.proxy._send = http_send
    front = make_server(env.proxy)
    for server in (upstream, front):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    yield env, demo, f"http://127.0.0.1:{front.server_address[1]}"
    for server in (upstream, front):
        server.shutdown()


def post(url, message, token=None):
    headers = {"content-type": "application/json", **({"authorization": f"Bearer {token}"} if token else {})}
    request = urllib.request.Request(url, json.dumps(message).encode(), headers)  # noqa: S310 (loopback test server)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 (loopback test server)
            return response.status, json.load(response), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null"), dict(error.headers)


def test_list_and_call_over_http(stack):
    env, demo, base = stack
    status, body, _ = post(f"{base}/mcp/dossiers", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, env.token())
    assert status == 200 and len(body["result"]["tools"]) == 3
    call = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "lire_dossier", "arguments": {"id": "7"}},
    }
    status, body, _ = post(f"{base}/mcp/dossiers", call, env.token())
    assert status == 200 and "Dossier 7" in body["result"]["content"][0]["text"]


def test_challenge_and_metadata_over_http(stack):
    env, _, base = stack
    status, _, headers = post(f"{base}/mcp/dossiers", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert status == 401 and "resource_metadata=" in headers["WWW-Authenticate"]
    with urllib.request.urlopen(f"{base}/.well-known/oauth-protected-resource/mcp", timeout=10) as response:  # noqa: S310 (loopback test server)
        assert json.load(response)["resource"] == env.proxy.resource
    with urllib.request.urlopen(f"{base}/jwks.json", timeout=10) as response:  # noqa: S310 (loopback test server)
        assert json.load(response)["keys"][0]["kty"] == "EC"


def test_unknown_paths_and_bad_bodies(stack):
    env, _, base = stack
    assert post(f"{base}/mcp/dossiers/x", {"jsonrpc": "2.0"}, env.token())[0] == 404
    request = urllib.request.Request(f"{base}/mcp/dossiers", b"{not json", {"content-type": "application/json"})  # noqa: S310 (loopback test server)
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=10)  # noqa: S310 (loopback test server)
    assert caught.value.code == 400
