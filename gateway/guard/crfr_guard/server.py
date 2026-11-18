"""gRPC external processor for Envoy (envoy.service.ext_proc.v3), wired to the guard's decisions.

Envoy sends the request headers, then the buffered request body, then the response headers and the
response body in chunks (streamed mode). The guard answers every message; a refusal is an immediate
response in the Anthropic error format. If the guard is down, Envoy refuses the request
(``failOpen: false`` in the generated EnvoyExtensionPolicy).
"""

from __future__ import annotations

import argparse
import logging
import os
import secrets
from concurrent import futures
from pathlib import Path

import grpc
from envoy.service.ext_proc.v3 import external_processor_pb2 as pb
from envoy.service.ext_proc.v3 import external_processor_pb2_grpc as pb_grpc
from envoy.type.v3 import http_status_pb2

from . import config as config_module
from .audit import AuditLog, ContentLog, LocalMac
from .audit import key_from_env as audit_key_from_env
from .engine import Exchange, Guard, Refusal
from .ledger import Ledger
from .policy import OpaClient
from .telemetry import Telemetry

LOG = logging.getLogger("crfr_guard")


def header_map(headers) -> dict[str, str]:
    return {
        h.key.lower(): (h.raw_value.decode("utf-8", "replace") if h.raw_value else h.value) for h in headers.headers
    }


def immediate(refusal: Refusal) -> pb.ProcessingResponse:
    response = pb.ProcessingResponse()
    response.immediate_response.status.code = http_status_pb2.StatusCode.Value(_STATUS_NAMES[refusal.status])
    response.immediate_response.body = refusal.body()
    header = response.immediate_response.headers.set_headers.add()
    header.header.key = "content-type"
    header.header.raw_value = b"application/json"
    return response


_STATUS_NAMES = {
    400: "BadRequest",
    401: "Unauthorized",
    403: "Forbidden",
    429: "TooManyRequests",
    503: "ServiceUnavailable",
}


class Processor(pb_grpc.ExternalProcessorServicer):
    def __init__(self, guard: Guard):
        self.guard = guard

    def Process(self, request_iterator, context):  # noqa: N802 (gRPC method name)
        exchange = Exchange()
        headers: dict[str, str] = {}
        for message in request_iterator:
            kind = message.WhichOneof("request")
            response = pb.ProcessingResponse()
            if kind == "request_headers":
                headers = header_map(message.request_headers.headers)
                response.request_headers.SetInParent()
                if message.request_headers.end_of_stream:  # no body: still a decision to take
                    refusal = self.guard.on_request(exchange, headers, b"")
                    if refusal:
                        yield immediate(refusal)
                        return
            elif kind == "request_body":
                refusal = self.guard.on_request(exchange, headers, message.request_body.body)
                if refusal:
                    yield immediate(refusal)
                    return
                response.request_body.SetInParent()
                if exchange.new_body is not None:
                    common = response.request_body.response
                    common.body_mutation.body = exchange.new_body
                    length = common.header_mutation.set_headers.add()
                    length.header.key = "content-length"
                    length.header.raw_value = str(len(exchange.new_body)).encode()
            elif kind == "response_headers":
                response_headers = header_map(message.response_headers.headers)
                exchange.response_status = int(response_headers.get(":status", "0") or 0)
                exchange.content_type = response_headers.get("content-type", "")
                response.response_headers.SetInParent()
                if self.guard.rewrites_response(exchange):
                    # Restored values change the length; Envoy switches to chunked encoding.
                    response.response_headers.response.header_mutation.remove_headers.append("content-length")
                if message.response_headers.end_of_stream:
                    self.guard.on_response_end(exchange)
            elif kind == "response_body":
                chunk, end = message.response_body.body, message.response_body.end_of_stream
                self.guard.on_response_chunk(exchange, chunk)
                response.response_body.SetInParent()
                if self.guard.rewrites_response(exchange):
                    response.response_body.response.body_mutation.body = self.guard.response_out(exchange, chunk, end)
                if message.response_body.end_of_stream:
                    self.guard.on_response_end(exchange)
            else:
                getattr(response, kind).SetInParent()
            yield response


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="crfr guard (Envoy external processor)")
    parser.add_argument("--config", type=Path, default=Path(os.environ.get("GUARD_CONFIG", "/config/guard.json")))
    parser.add_argument("--state", type=Path, default=Path(os.environ.get("GUARD_STATE", "/data/guard.sqlite")))
    parser.add_argument("--audit-dir", type=Path, default=Path(os.environ.get("GUARD_AUDIT_DIR", "/data/audit")))
    parser.add_argument("--listen", default=os.environ.get("GUARD_LISTEN", "0.0.0.0:9002"))  # noqa: S104 (container)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    cfg = config_module.load(args.config)
    pseudonymiser = None
    if cfg.pseudonymisation:
        from crfr_pseudo.detectors import Detector
        from crfr_pseudo.pseudonymiser import Pseudonymiser
        from crfr_pseudo.vault import Vault, key_from_env

        key = key_from_env()
        if key is None:
            LOG.warning("CRFR_VAULT_KEY not set: random in-memory key, mappings are lost on restart")
        vault = Vault(args.state.with_name("vault.sqlite") if key else ":memory:", key=key, ttl_s=cfg.vault_ttl_s)
        pseudonymiser = Pseudonymiser(Detector(types=cfg.pseudonym_types), vault)
        LOG.info("pseudonymisation enabled")
    audit_key = audit_key_from_env()
    if audit_key is None:
        # Fingerprints and the MAC chain then only hold within this process: fine for tests, not for an audit.
        LOG.warning("CRFR_AUDIT_KEY not set: random in-memory audit key, fingerprints cannot be checked later")
        audit_key = secrets.token_bytes(32)
    audit = AuditLog(args.audit_dir, LocalMac(audit_key), segment_s=cfg.audit_segment_s)
    content = None
    if cfg.content_log:
        content = ContentLog(args.audit_dir.with_name("content"), cfg.content_retention_days)
        LOG.info("content log enabled, retention %d days", cfg.content_retention_days)
    telemetry = Telemetry.from_env()
    if telemetry:
        LOG.info("OTLP export to %s, without content", telemetry.url)
    guard = Guard(
        cfg, Ledger(args.state), OpaClient(cfg.opa_url, cfg.opa_timeout_s), audit, pseudonymiser, content, telemetry
    )
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=32))
    pb_grpc.add_ExternalProcessorServicer_to_server(Processor(guard), server)
    server.add_insecure_port(args.listen)
    server.start()
    LOG.info("guard listening on %s", args.listen)
    server.wait_for_termination()


if __name__ == "__main__":
    main()
