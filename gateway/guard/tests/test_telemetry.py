import json

from conftest import bearer, body
from test_engine import OK, admit, complete

from crfr_guard.telemetry import Telemetry


class Sink:
    def __init__(self):
        self.bodies = []

    def __call__(self, raw: bytes):
        self.bodies.append(json.loads(raw))

    def spans(self):
        return [s for b in self.bodies for r in b["resourceSpans"] for sc in r["scopeSpans"] for s in sc["spans"]]


def attrs(span):
    return {a["key"]: next(iter(a["value"].values())) for a in span["attributes"]}


def telemetry(guard):
    sink = Sink()
    guard.telemetry = Telemetry("http://collector:4318", interval_s=3600, send=sink)
    return sink


def test_admitted_call_gives_one_genai_span_without_content(guard):
    sink = telemetry(guard)
    exchange, _ = admit(guard, raw=body(text="texte confidentiel"))
    complete(guard, exchange, OK)
    guard.telemetry.flush()
    (span,) = sink.spans()
    a = attrs(span)
    assert span["name"] == "chat" and span["kind"] == 3 and span["status"] == {"code": 1}
    assert a["gen_ai.operation.name"] == "chat" and a["gen_ai.provider.name"] == "aws.bedrock"
    assert a["gen_ai.request.model"] == "claude-sonnet-5" and a["crfr.decision"] == "admitted"
    assert (a["gen_ai.usage.input_tokens"], a["gen_ai.usage.output_tokens"]) == ("40", "20")
    assert "confidentiel" not in json.dumps(sink.bodies)
    assert int(span["endTimeUnixNano"]) >= int(span["startTimeUnixNano"])


def test_cached_tokens_are_counted_in_input_tokens(guard):
    sink = telemetry(guard)
    exchange, _ = admit(guard)
    usage = {"input_tokens": 5, "output_tokens": 2, "cache_read_input_tokens": 30, "cache_creation_input_tokens": 7}
    complete(guard, exchange, json.dumps({"usage": usage}).encode())
    guard.telemetry.flush()
    a = attrs(sink.spans()[0])
    assert a["gen_ai.usage.input_tokens"] == "42"
    assert (a["gen_ai.usage.cache_read.input_tokens"], a["gen_ai.usage.cache_write.input_tokens"]) == ("30", "7")


def test_refusal_gives_an_error_span(guard):
    sink = telemetry(guard)
    admit(guard, headers={"authorization": "Bearer nope"})
    guard.telemetry.flush()
    (span,) = sink.spans()
    assert span["status"] == {"code": 2}
    assert attrs(span)["crfr.decision"] == "refused" and attrs(span)["crfr.reason"] == "identity"


def test_export_failure_drops_spans_without_raising(guard):
    def down(_):
        raise OSError("collector down")

    guard.telemetry = Telemetry("http://collector:4318", interval_s=3600, send=down)
    exchange, _ = admit(guard, bearer())
    complete(guard, exchange, OK)
    guard.telemetry.flush()
    assert guard.telemetry.dropped == 1
