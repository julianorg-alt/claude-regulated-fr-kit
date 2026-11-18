"""The ext_proc message flow, driven with protobuf messages as Envoy sends them (no network)."""

import json

from conftest import bearer, body
from envoy.config.core.v3 import base_pb2
from envoy.service.ext_proc.v3 import external_processor_pb2 as pb

from crfr_guard.server import Processor


def headers_message(field: str, headers: dict, end_of_stream=False) -> pb.ProcessingRequest:
    message = pb.ProcessingRequest()
    target = getattr(message, field)
    for key, value in headers.items():
        target.headers.headers.append(base_pb2.HeaderValue(key=key, raw_value=value.encode()))
    target.end_of_stream = end_of_stream
    return message


def body_message(field: str, data: bytes, end_of_stream=True) -> pb.ProcessingRequest:
    message = pb.ProcessingRequest()
    getattr(message, field).body = data
    getattr(message, field).end_of_stream = end_of_stream
    return message


def run(guard, messages):
    return list(Processor(guard).Process(iter(messages), None))


def test_admitted_call_flows_through_and_is_charged(guard):
    usage = json.dumps({"usage": {"input_tokens": 3, "output_tokens": 4}}).encode()
    out = run(
        guard,
        [
            headers_message("request_headers", {**bearer(), "x-request-id": "r1"}),
            body_message("request_body", body()),
            headers_message("response_headers", {":status": "200", "content-type": "application/json"}),
            body_message("response_body", usage[:10], end_of_stream=False),
            body_message("response_body", usage[10:]),
        ],
    )
    kinds = [m.WhichOneof("response") for m in out]
    assert kinds == ["request_headers", "request_body", "response_headers", "response_body", "response_body"]
    assert not out[1].request_body.response.HasField("body_mutation"), "the guard does not rewrite bodies (yet)"
    assert guard.ledger.tokens_today("user", "alice") == 7


def test_refusal_is_an_immediate_anthropic_error(guard):
    guard.ledger.set_switch("global", "*", "drill")
    out = run(guard, [headers_message("request_headers", bearer()), body_message("request_body", body())])
    assert [m.WhichOneof("response") for m in out] == ["request_headers", "immediate_response"]
    response = out[1].immediate_response
    assert response.status.code == 503
    assert json.loads(response.body)["error"]["type"] == "overloaded_error"
    assert response.headers.set_headers[0].header.key == "content-type"


def test_request_without_body_is_still_decided(guard):
    out = run(guard, [headers_message("request_headers", {"x": "y"}, end_of_stream=True)])
    assert out[-1].immediate_response.status.code == 401
