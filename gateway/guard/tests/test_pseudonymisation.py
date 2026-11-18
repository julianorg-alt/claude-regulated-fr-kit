"""The guard with the pseudonymisation stage (E3.5): request rewrite, residual check, re-identification."""

import json

import pytest
from conftest import RAW_CONFIG, FakeOpa, bearer, body
from crfr_pseudo.detectors import Detector
from crfr_pseudo.pseudonymiser import Pseudonymiser
from crfr_pseudo.vault import Vault
from test_server import body_message, headers_message, run

from crfr_guard import config as config_module
from crfr_guard.audit import AuditLog, LocalMac, read_segments
from crfr_guard.engine import Exchange, Guard
from crfr_guard.ledger import Ledger

NIR = "1850578006084" + f"{97 - 1850578006084 % 97:02d}"
TEXT = f"Je suis Jean Martin, NIR {NIR}, IBAN FR76 0000 0012 3412 3456 7890 151."


@pytest.fixture(scope="module")
def detector():
    return Detector()


@pytest.fixture
def pguard(tmp_path, detector):
    cfg = config_module.parse(RAW_CONFIG)
    return Guard(
        cfg, Ledger(tmp_path / "g.sqlite"), FakeOpa(), AuditLog(tmp_path / "audit", LocalMac(b"k" * 32), stream=None),
        Pseudonymiser(detector, Vault()),
    )  # fmt: skip


def test_request_is_rewritten_and_residual_is_empty(pguard, tmp_path):
    exchange = Exchange()
    assert pguard.on_request(exchange, {**bearer(), "x-crfr-session": "conv-1"}, body(text=TEXT)) is None
    sent = json.loads(exchange.new_body)
    assert sent["messages"][0]["content"] == "Je suis <PERSONNE_1>, NIR <NIR_1>, IBAN <IBAN_1>."
    policy = pguard.opa.inputs[-1]["pii"]
    assert policy == {"residual": [], "pseudonymised": {"PERSONNE": 1, "NIR": 1, "IBAN": 1}}
    log = "\n".join(read_segments(tmp_path / "audit"))
    assert NIR not in log and "Jean Martin" not in log and '"NIR": 1' in log


def test_session_is_scoped_to_the_caller(pguard):
    mine, other = Exchange(), Exchange()
    pguard.on_request(mine, {**bearer(), "x-crfr-session": "same"}, body(text=TEXT))
    pguard.on_request(other, {**bearer(user="bob"), "x-crfr-session": "same"}, body(text="rien"))
    assert pguard.pseudonymiser.reidentify("<NIR_1>", other.session) == "<NIR_1>"
    assert pguard.pseudonymiser.reidentify("<NIR_1>", mine.session) == NIR


def test_nothing_to_pseudonymise_leaves_body_untouched(pguard):
    exchange = Exchange()
    pguard.on_request(exchange, bearer(), body(text="Bonjour"))
    assert exchange.new_body is None


def test_json_answer_is_reidentified(pguard):
    answer = json.dumps(
        {
            "content": [{"type": "text", "text": "Bien reçu <PERSONNE_1>."}],
            "usage": {"input_tokens": 1, "output_tokens": 2},
        }
    ).encode()
    out = run(
        pguard,
        [
            headers_message("request_headers", {**bearer(), "x-request-id": "r"}),
            body_message("request_body", body(text=TEXT)),
            headers_message(
                "response_headers", {":status": "200", "content-type": "application/json", "content-length": "9"}
            ),
            body_message("response_body", answer[:20], end_of_stream=False),
            body_message("response_body", answer[20:]),
        ],
    )
    assert out[1].request_body.response.body_mutation.body.startswith(b"{")
    assert list(out[2].response_headers.response.header_mutation.remove_headers) == ["content-length"]
    assert out[3].response_body.response.body_mutation.body == b""
    final = json.loads(out[4].response_body.response.body_mutation.body)
    assert final["content"][0]["text"] == "Bien reçu Jean Martin."
    assert pguard.ledger.tokens_today("user", "alice") == 3


def test_streamed_answer_is_reidentified_and_charged(pguard):
    events = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 5}}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Votre NIR <NI"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "R_1> est noté."}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "usage": {"output_tokens": 6}},
    ]
    stream = b"".join(b"event: x\ndata: " + json.dumps(e).encode() + b"\n\n" for e in events)
    messages = [
        headers_message("request_headers", bearer()),
        body_message("request_body", body(text=TEXT)),
        headers_message("response_headers", {":status": "200", "content-type": "text/event-stream"}),
    ]
    messages += [
        body_message("response_body", stream[i : i + 25], end_of_stream=False) for i in range(0, len(stream), 25)
    ]
    messages.append(body_message("response_body", b""))
    out = run(pguard, messages)
    sent = b"".join(
        m.response_body.response.body_mutation.body for m in out if m.WhichOneof("response") == "response_body"
    )
    text = "".join(
        json.loads(line[5:])["delta"]["text"]
        for line in sent.split(b"\n")
        if line.startswith(b"data:") and b"text_delta" in line
    )
    assert text == f"Votre NIR {NIR} est noté."
    assert pguard.ledger.tokens_today("user", "alice") == 11


def test_request_line_carries_a_fingerprint_of_the_original_body(pguard, tmp_path):
    from crfr_guard.audit import fingerprint

    raw = body(text=TEXT)
    pguard.on_request(Exchange(), bearer(), raw)
    entry = json.loads(read_segments(tmp_path / "audit")[-1])
    assert entry["prompt_hmac"] == fingerprint(LocalMac(b"k" * 32), raw)


def test_content_log_keeps_only_what_bedrock_saw(tmp_path, detector):
    from crfr_guard.audit import ContentLog

    cfg = config_module.parse(RAW_CONFIG)
    guard = Guard(
        cfg, Ledger(tmp_path / "g.sqlite"), FakeOpa(), AuditLog(tmp_path / "audit", LocalMac(b"k" * 32), stream=None),
        Pseudonymiser(detector, Vault()), ContentLog(tmp_path / "content", retention_days=3),
    )  # fmt: skip
    exchange = Exchange()
    guard.on_request(exchange, bearer(), body(text=TEXT))
    answer = json.dumps({"content": [{"type": "text", "text": "Bonjour <PERSONNE_1>"}], "usage": {}}).encode()
    exchange.response_status, exchange.content_type = 200, "application/json"
    guard.on_response_chunk(exchange, answer)
    assert b"Jean Martin" in guard.response_out(exchange, answer, True)
    guard.on_response_end(exchange)
    stored = "\n".join(read_segments(tmp_path / "content", "content"))
    assert "<PERSONNE_1>" in stored and "<NIR_1>" in stored
    assert "Jean Martin" not in stored and NIR not in stored


def test_content_log_without_pseudonymisation_is_refused(tmp_path):
    from crfr_guard.audit import ContentLog

    cfg = config_module.parse(RAW_CONFIG)
    with pytest.raises(ValueError):
        Guard(cfg, Ledger(tmp_path / "g.sqlite"), FakeOpa(), AuditLog(None, LocalMac(b"k" * 32), stream=None),
              None, ContentLog(tmp_path / "content", retention_days=3))  # fmt: skip
    with pytest.raises(config_module.ConfigError):
        config_module.parse({**RAW_CONFIG, "audit": {"content": {"enabled": True}}})
    with pytest.raises(config_module.ConfigError):
        config_module.parse({**RAW_CONFIG, "pseudonymisation": {"enabled": True},
                             "audit": {"content": {"enabled": True, "retention_days": 90}}})  # fmt: skip
