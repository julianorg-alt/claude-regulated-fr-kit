"""OpenTelemetry spans of the gateway, GenAI semantic conventions, without any content (backlog E5.3).

One span per call, named after ``gen_ai.operation.name`` as the conventions ask, with the model, the token
usage and the guard's decision. The conventions leave prompts and answers out unless the user opts in; the
guard has no such option at all: what the SIEM receives is what the audit log holds.

Export: OTLP/HTTP with JSON encoding to ``$OTEL_EXPORTER_OTLP_ENDPOINT/v1/traces``, from a background thread,
standard library only. A collector forwards to the SIEM. When the endpoint is not set, nothing is exported.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import secrets
import threading
import time
import urllib.request

LOG = logging.getLogger("crfr.telemetry")
SPAN_KIND_CLIENT = 3
STATUS_OK, STATUS_ERROR = 1, 2


def _value(value):
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


def attributes_of(exchange, refusal=None, found=None) -> dict:
    identity = exchange.identity
    attrs = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "aws.bedrock",
        "gen_ai.request.model": exchange.model,
        "crfr.decision": "refused" if refusal else "admitted",
        "crfr.reason": refusal.reason if refusal else None,
        "crfr.request_id": exchange.request_id,
        "crfr.user": identity.user if identity else None,
        "crfr.team": identity.team if identity else None,
        "crfr.app": identity.app if identity else None,
        "http.response.status_code": refusal.status if refusal else exchange.response_status,
    }
    if exchange.pseudonymised:
        attrs["crfr.pseudonymised"] = sum(exchange.pseudonymised.values())
    if found:
        cache_read, cache_write = found.cache_read_input_tokens, found.cache_creation_input_tokens
        # The conventions count cached tokens inside gen_ai.usage.input_tokens.
        attrs["gen_ai.usage.input_tokens"] = found.input_tokens + cache_read + cache_write
        attrs["gen_ai.usage.output_tokens"] = found.output_tokens
        attrs["gen_ai.usage.cache_read.input_tokens"] = cache_read
        attrs["gen_ai.usage.cache_write.input_tokens"] = cache_write
    return {k: v for k, v in attrs.items() if v is not None}


def span(name: str, start_ns: int, end_ns: int, attrs: dict, error: bool) -> dict:
    return {
        "traceId": secrets.token_hex(16),
        "spanId": secrets.token_hex(8),
        "name": name,
        "kind": SPAN_KIND_CLIENT,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": [{"key": k, "value": _value(v)} for k, v in sorted(attrs.items())],
        "status": {"code": STATUS_ERROR if error else STATUS_OK},
    }


def payload(spans: list[dict], service: str = "crfr-guard") -> bytes:
    return json.dumps(
        {
            "resourceSpans": [
                {
                    "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": service}}]},
                    "scopeSpans": [{"scope": {"name": "crfr_guard"}, "spans": spans}],
                }
            ]
        }
    ).encode()


class Telemetry:
    def __init__(self, endpoint: str, interval_s: float = 2.0, max_queue: int = 10_000, send=None):
        self.url = endpoint.rstrip("/") + "/v1/traces"
        self.interval_s = interval_s
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue)
        self._send = send or self._post
        self.dropped = 0
        threading.Thread(target=self._run, name="otlp-export", daemon=True).start()

    @classmethod
    def from_env(cls) -> Telemetry | None:
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        return cls(endpoint) if endpoint else None

    def record(self, exchange, refusal=None, found=None) -> None:
        end = time.time_ns()
        start = exchange.started_ns or end
        error = bool(refusal) or (exchange.response_status or 200) >= 400
        try:
            self._queue.put_nowait(span("chat", start, end, attributes_of(exchange, refusal, found), error))
        except queue.Full:  # telemetry never slows or blocks a call; the audit log stays complete
            self.dropped += 1

    def flush(self) -> None:
        batch = []
        while not self._queue.empty() and len(batch) < 512:
            batch.append(self._queue.get_nowait())
        if batch:
            try:
                self._send(payload(batch))
            except OSError as error:
                self.dropped += len(batch)
                LOG.warning("OTLP export failed (%s), %d spans dropped", error, len(batch))

    def _post(self, body: bytes) -> None:
        request = urllib.request.Request(self.url, body, {"content-type": "application/json"})  # noqa: S310
        with urllib.request.urlopen(request, timeout=5) as answer:  # noqa: S310 (configured collector)
            answer.read()

    def _run(self) -> None:
        while True:
            time.sleep(self.interval_s)
            self.flush()
