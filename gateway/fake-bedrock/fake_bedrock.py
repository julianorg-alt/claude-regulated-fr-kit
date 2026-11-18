"""Fake Amazon Bedrock runtime for the local demo and CI (decision K3: no AWS account).

It behaves like the parts of Bedrock the kit relies on, and refuses what the IAM policy of
infra/terraform/modules/bedrock-eu-access refuses:

* requires a SigV4 ``Authorization`` header whose credential scope names the configured Region
  and the ``bedrock`` service (the gateway must sign, and sign for the right Region);
* only serves the inference profiles listed in ``ALLOWED_PROFILES`` (comma separated);
  ``global.*``, ``us.*``, Fable and Mythos are rejected with ``AccessDeniedException``;
* refuses everything while ``IAM_KILL_SWITCH`` (a file) exists, as the explicit deny of the
  Terraform ``kill_switch`` variable does (backlog E2.6, level 3);
* simulates prompt caching (E2.8): blocks marked with ``cache_control`` define a cached prefix, the
  first call reports ``cache_creation_input_tokens`` and later calls within the TTL report
  ``cache_read_input_tokens``, with the Anthropic field names (token counts are word counts);
* answers ``POST /model/{id}/invoke-with-response-stream`` with the AWS event-stream encoding
  Bedrock uses (one ``chunk`` event per Anthropic server-sent event, text split in small deltas so
  that the gateway's handling of split pseudonyms is exercised);
* plays the second provider of the exit route (E10.1) at ``POST /v1/chat/completions``: OpenAI-compatible
  answers (buffered or streamed), a Bearer key (``FAKE_EXIT_API_KEY``) and its own request log, so that the
  invariant "every request that reached Bedrock is EU" stays checkable on the Bedrock log alone;
* answers ``POST /model/{id}/invoke`` with an Anthropic Messages response. Responses come from
  a cassette file when the request hash is known (recorded answers for evaluations, decision
  K8), otherwise from a deterministic echo.

Every request is appended to a JSON Lines log, so tests can assert what reached "AWS"
(for example that no personal data in clear text left the gateway).

Standard library only.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import struct
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

REGION = os.environ.get("FAKE_BEDROCK_REGION", "eu-west-3")
ALLOWED_PROFILES = {p.strip() for p in os.environ.get("ALLOWED_PROFILES", "").split(",") if p.strip()}
CASSETTE = Path(os.environ.get("FAKE_BEDROCK_CASSETTE", "/data/cassette.json"))
REQUEST_LOG = Path(os.environ.get("FAKE_BEDROCK_LOG", "/data/requests.jsonl"))
EXIT_LOG = Path(os.environ.get("FAKE_BEDROCK_EXIT_LOG", "/data/exit-requests.jsonl"))
EXIT_KEY = os.environ.get("FAKE_EXIT_API_KEY", "local-demo-only-exit-key")  # a demo value, not a secret
IAM_KILL_SWITCH = Path(os.environ.get("FAKE_BEDROCK_IAM_KILL_SWITCH", "/data/iam-kill-switch"))
MAX_BODY = 2 * 1024 * 1024
_CACHE: dict[str, float] = {}  # prefix hash -> expiry time

_PATH = re.compile(r"^/model/(?P<model>[^/]+)/(?P<op>invoke|invoke-with-response-stream|converse|converse-stream)$")
_SCOPE = re.compile(r"Credential=[^/]+/\d{8}/(?P<region>[a-z0-9-]+)/(?P<service>[a-z0-9-]+)/aws4_request")
_FORBIDDEN = re.compile(r"^(global|us|us-gov|apac|au|jp|in|ca)\.|claude-(fable|mythos)", re.I)
_LOCK = threading.Lock()


def request_hash(model: str, body: dict) -> str:
    canonical = json.dumps({"model": model, "body": body}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def load_cassette() -> dict:
    if CASSETTE.is_file():
        return json.loads(CASSETTE.read_text(encoding="utf-8"))
    return {}


def _words(node) -> int:
    if isinstance(node, str):
        return len(node.split())
    if isinstance(node, list):
        return sum(_words(n) for n in node)
    if isinstance(node, dict):
        return sum(_words(v) for k, v in node.items() if k in ("text", "content", "description", "input_schema"))
    return 0


def _blocks(body: dict) -> list:
    """Prompt blocks in the order Anthropic builds the cache prefix: tools, system, messages."""
    out = list(body.get("tools") or [])
    system = body.get("system")
    out += [{"type": "text", "text": system}] if isinstance(system, str) else list(system or [])
    for message in body.get("messages", []):
        content = message.get("content")
        out += [{"type": "text", "text": content}] if isinstance(content, str) else list(content or [])
    return out


def cache_usage(model: str, body: dict, now: float) -> dict:
    blocks = _blocks(body)
    marks = [i for i, b in enumerate(blocks) if isinstance(b, dict) and b.get("cache_control")]
    total = _words(blocks)
    if not marks:
        return {"input_tokens": max(1, total)}
    prefix = blocks[: marks[-1] + 1]
    ttl = 3600 if prefix[-1]["cache_control"].get("ttl") == "1h" else 300
    key = hashlib.sha256(json.dumps([model, prefix], sort_keys=True).encode()).hexdigest()
    cached = _words(prefix)
    with _LOCK:
        hit = _CACHE.get(key, 0) > now
        _CACHE[key] = now + ttl  # the TTL resets on each hit
    field = "cache_read_input_tokens" if hit else "cache_creation_input_tokens"
    other = "cache_creation_input_tokens" if hit else "cache_read_input_tokens"
    return {"input_tokens": total - cached, field: cached, other: 0}


def echo_response(model: str, body: dict) -> dict:
    """Deterministic Anthropic Messages answer: repeats the last user text."""
    text = ""
    for message in reversed(body.get("messages", [])):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                text = content
            else:
                text = " ".join(part.get("text", "") for part in content or [] if part.get("type") == "text")
            break
    answer = f"[fake-bedrock {model}] {text}"
    return {
        "id": "msg_fake_" + request_hash(model, body)[:24],
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": answer}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {**cache_usage(model, body, time.time()), "output_tokens": len(answer.split())},
    }


def event_message(payload: bytes) -> bytes:
    """One AWS event-stream message: prelude, CRC, string headers, payload, CRC."""
    headers = b""
    for name, value in ((":event-type", "chunk"), (":content-type", "application/json"), (":message-type", "event")):
        headers += bytes([len(name)]) + name.encode() + b"\x07" + struct.pack(">H", len(value)) + value.encode()
    total = 12 + len(headers) + len(payload) + 4
    prelude = struct.pack(">II", total, len(headers))
    prelude += struct.pack(">I", binascii.crc32(prelude))
    message = prelude + headers + payload
    return message + struct.pack(">I", binascii.crc32(message))


def stream_events(response: dict, piece: int = 5) -> list[dict]:
    """Anthropic streaming events equivalent to a buffered response."""
    usage = response["usage"]
    start = {k: v for k, v in usage.items() if k != "output_tokens"} | {"output_tokens": 1}
    events = [{"type": "message_start", "message": {**response, "content": [], "usage": start}}]
    for index, block in enumerate(response["content"]):
        events.append({"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}})
        text = block.get("text", "")
        for i in range(0, len(text), piece):
            events.append(
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "text_delta", "text": text[i : i + piece]},
                }
            )
        events.append({"type": "content_block_stop", "index": index})
    events.append(
        {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
         "usage": {"output_tokens": usage["output_tokens"]}}
    )  # fmt: skip
    events.append({"type": "message_stop"})
    return events


def last_user_text(body: dict) -> str:
    for message in reversed(body.get("messages") or []):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content
            return " ".join(p.get("text", "") for p in content or [] if isinstance(p, dict))
    return ""


def openai_completion(body: dict) -> dict:
    model = str(body.get("model", ""))
    answer = f"[fake-exit {model}] {last_user_text(body)}"
    prompt = _words(body.get("messages") or [])
    done = len(answer.split())
    return {
        "id": "chatcmpl-fake-" + request_hash(model, body)[:24],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": done, "total_tokens": prompt + done},
    }


def openai_stream(completion: dict, piece: int = 5) -> bytes:
    text = completion["choices"][0]["message"]["content"]
    base = {"id": completion["id"], "object": "chat.completion.chunk", "created": completion["created"],
            "model": completion["model"]}  # fmt: skip
    chunks = [{**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]}]
    for i in range(0, len(text), piece):
        chunks.append(
            {**base, "choices": [{"index": 0, "delta": {"content": text[i : i + piece]}, "finish_reason": None}]}
        )
    chunks.append({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
    # stream_options.include_usage: usage arrives in one last chunk with no choices, as OpenAI sends it.
    chunks.append({**base, "choices": [], "usage": completion["usage"]})
    return ("".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n").encode()


class Handler(BaseHTTPRequestHandler):
    server_version = "fake-bedrock/1"

    def log_message(self, fmt: str, *args) -> None:  # quiet: the JSON log is the audit trail
        return

    def _send(self, status: int, payload: dict, error_type: str | None = None) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        if error_type:
            self.send_header("x-amzn-ErrorType", error_type)
        self.end_headers()
        self.wfile.write(data)

    def _log(self, entry: dict) -> None:
        with _LOCK:
            REQUEST_LOG.parent.mkdir(parents=True, exist_ok=True)
            with REQUEST_LOG.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._send(HTTPStatus.OK, {"status": "ok"})
        else:
            self._send(HTTPStatus.NOT_FOUND, {"message": "not found"})

    def _exit_provider(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": {"message": "body too large"}})
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(HTTPStatus.BAD_REQUEST, {"error": {"message": "invalid JSON"}})
            return
        authorised = self.headers.get("Authorization") == f"Bearer {EXIT_KEY}"
        with _LOCK:
            EXIT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with EXIT_LOG.open("a", encoding="utf-8") as handle:
                entry = {"model": body.get("model"), "authorised": authorised,
                         "headers": sorted(h.lower() for h in self.headers), "body": body}  # fmt: skip
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if not authorised:
            self._send(HTTPStatus.UNAUTHORIZED, {"error": {"message": "invalid API key"}})
            return
        completion = openai_completion(body)
        if not body.get("stream"):
            self._send(HTTPStatus.OK, completion)
            return
        data = openai_stream(completion)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] == "/v1/chat/completions":
            self._exit_provider()
            return
        match = _PATH.match(self.path.split("?", 1)[0])
        if not match:
            self._send(HTTPStatus.NOT_FOUND, {"message": "unknown operation"}, "UnknownOperationException")
            return
        model, op = unquote(match.group("model")), match.group("op")
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"message": "body too large"}, "ValidationException")
            return
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send(HTTPStatus.BAD_REQUEST, {"message": "invalid JSON"}, "ValidationException")
            return

        scope = _SCOPE.search(self.headers.get("Authorization", ""))
        decision = "allowed"
        status, error = HTTPStatus.OK, None
        if not scope or scope.group("service") != "bedrock":
            decision, status, error = "unsigned", HTTPStatus.FORBIDDEN, "UnrecognizedClientException"
        elif IAM_KILL_SWITCH.exists():
            decision, status, error = "iam-kill-switch", HTTPStatus.FORBIDDEN, "AccessDeniedException"
        elif scope.group("region") != REGION:
            decision, status, error = "wrong-region", HTTPStatus.FORBIDDEN, "AccessDeniedException"
        elif _FORBIDDEN.search(model):
            decision, status, error = "forbidden-model", HTTPStatus.FORBIDDEN, "AccessDeniedException"
        elif ALLOWED_PROFILES and model not in ALLOWED_PROFILES:
            decision, status, error = "not-allowed", HTTPStatus.FORBIDDEN, "AccessDeniedException"
        elif op not in ("invoke", "invoke-with-response-stream"):
            decision, status, error = "unsupported-op", HTTPStatus.BAD_REQUEST, "ValidationException"

        self._log(
            {
                "model": model,
                "op": op,
                "decision": decision,
                "region": scope.group("region") if scope else None,
                "auth_scheme": (self.headers.get("Authorization", "").split(" ", 1)[0] or None),
                "headers": sorted(h.lower() for h in self.headers),
                "hash": request_hash(model, body),
                "body": body,
            }
        )
        if error:
            self._send(status, {"message": f"{decision}: {model}"}, error)
            return
        recorded = load_cassette().get(request_hash(model, body))
        answer = recorded or echo_response(model, body)
        if op == "invoke":
            self._send(HTTPStatus.OK, answer)
            return
        data = b"".join(
            event_message(json.dumps({"bytes": base64.b64encode(json.dumps(e).encode()).decode()}).encode())
            for e in stream_events(answer)
        )
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/vnd.amazon.eventstream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)  # noqa: S104 (container-internal)
    server.serve_forever()


if __name__ == "__main__":
    main()
