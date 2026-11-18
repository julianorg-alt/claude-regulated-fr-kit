"""The fake exit provider in fake-bedrock (backlog E10.1): an OpenAI-compatible endpoint with a Bearer key."""

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "gateway/fake-bedrock/fake_bedrock.py"


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_BEDROCK_EXIT_LOG", str(tmp_path / "exit.jsonl"))
    monkeypatch.setenv("FAKE_BEDROCK_LOG", str(tmp_path / "bedrock.jsonl"))
    monkeypatch.setenv("FAKE_EXIT_API_KEY", "k-test")
    spec = importlib.util.spec_from_file_location("fake_bedrock_under_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", tmp_path
    httpd.shutdown()


def post(base, body, key="k-test", path="/v1/chat/completions"):
    headers = {"content-type": "application/json"}
    if key:
        headers["authorization"] = f"Bearer {key}"
    request = urllib.request.Request(base + path, json.dumps(body).encode(), headers)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=5) as r:  # noqa: S310 (loopback test server)
            return r.status, r.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def test_answers_in_openai_format_and_echoes_the_last_user_text(server):
    base, _ = server
    status, text = post(base, {"model": "m-large", "messages": [{"role": "user", "content": "bonjour"}]})
    body = json.loads(text)
    assert status == 200
    assert body["model"] == "m-large"
    assert "bonjour" in body["choices"][0]["message"]["content"]
    assert body["usage"]["total_tokens"] == body["usage"]["prompt_tokens"] + body["usage"]["completion_tokens"]


def test_refuses_a_missing_or_wrong_key(server):
    base, _ = server
    for key in (None, "other"):
        assert post(base, {"model": "m", "messages": []}, key=key)[0] == 401


def test_streams_chat_completion_chunks(server):
    base, _ = server
    status, text = post(base, {"model": "m", "stream": True, "messages": [{"role": "user", "content": "un deux"}]})
    assert status == 200
    assert text.rstrip().endswith("data: [DONE]")
    chunks = [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: {")]
    assert "".join(c["choices"][0]["delta"].get("content", "") for c in chunks if c["choices"]).endswith("un deux")
    assert chunks[-1]["usage"]["completion_tokens"] > 0


def test_logs_to_its_own_file_never_to_the_bedrock_log(server):
    base, tmp = server
    post(base, {"model": "m", "messages": [{"role": "user", "content": "canari"}]})
    entry = json.loads((tmp / "exit.jsonl").read_text().splitlines()[-1])
    assert entry["model"] == "m" and "canari" in json.dumps(entry["body"])
    assert not (tmp / "bedrock.jsonl").exists()
