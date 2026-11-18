import json

from conftest import nir

from crfr_pseudo.pseudonymiser import Pseudonymiser, StreamReidentifier
from crfr_pseudo.vault import Vault, VaultError

NIR = nir("1850578006084")


def test_vault_is_stable_typed_and_isolated(vault):
    assert vault.pseudonym("s1", "PERSONNE", "Jean Martin") == "<PERSONNE_1>"
    assert vault.pseudonym("s1", "PERSONNE", "  jean   MARTIN ") == "<PERSONNE_1>", "same person, same pseudonym"
    assert vault.pseudonym("s1", "PERSONNE", "Marie Curie") == "<PERSONNE_2>"
    assert vault.pseudonym("s1", "NIR", NIR) == "<NIR_1>"
    assert vault.pseudonym("s1", "NIR", " ".join(NIR)) == "<NIR_1>", "spacing does not change the identifier"
    assert vault.pseudonym("s2", "PERSONNE", "Marie Curie") == "<PERSONNE_1>", "numbering is per session"
    assert vault.original("s1", "PERSONNE", 2) == "Marie Curie"
    assert vault.original("s2", "PERSONNE", 2) is None, "a session cannot read another session's mapping"


def test_vault_stores_no_clear_value(vault):
    vault.pseudonym("session-secret", "NIR", NIR)
    dump = repr(vault.raw_rows())
    assert NIR not in dump and "session-secret" not in dump


def test_vault_ttl(tmp_path):
    now = [1000.0]
    vault = Vault(tmp_path / "v.sqlite", ttl_s=60, clock=lambda: now[0])
    vault.pseudonym("s", "EMAIL", "a@example.org")
    now[0] += 59
    assert vault.original("s", "EMAIL", 1) == "a@example.org"  # use extends the TTL
    now[0] += 59
    assert vault.original("s", "EMAIL", 1) == "a@example.org"
    now[0] += 61
    assert vault.original("s", "EMAIL", 1) is None
    assert vault.raw_rows() == []


def test_vault_key_checks(monkeypatch):
    import pytest

    from crfr_pseudo.vault import key_from_env

    monkeypatch.setenv("CRFR_VAULT_KEY", "c2hvcnQ=")
    with pytest.raises(VaultError):
        key_from_env()
    with pytest.raises(VaultError):
        Vault(key=b"short")


def test_request_rewrites_every_text_the_model_reads(pseudo):
    body = {
        "model": "claude-sonnet-5",
        "system": [{"type": "text", "text": "Dossier de Jean Martin", "cache_control": {"type": "ephemeral"}}],
        "messages": [
            {"role": "user", "content": f"Mon NIR est {NIR}."},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "lookup", "input": {"q": "jean.martin@example.org"}}
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "content": [{"type": "text", "text": "Tél 06 39 98 12 34"}],
                    }
                ],
            },
        ],
    }
    out, report = pseudo.request(body, "s")
    dumped = json.dumps(out, ensure_ascii=False)
    for secret in ("Jean Martin", NIR, "jean.martin@example.org", "06 39 98 12 34"):
        assert secret not in dumped
    assert out["messages"][0]["content"] == "Mon NIR est <NIR_1>."
    assert out["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert (
        out["messages"][1]["content"][0]["name"] == "lookup" and out["messages"][2]["content"][0]["tool_use_id"] == "t1"
    )
    assert report.counts == {"PERSONNE": 1, "NIR": 1, "EMAIL": 1, "TELEPHONE": 1}


def test_response_reidentification(pseudo):
    pseudo.request({"messages": [{"role": "user", "content": 'Client "Jean Martin"'}]}, "s")
    answer = {
        "content": [
            {"type": "text", "text": "Bonjour <PERSONNE_1>, inconnu <PERSONNE_9>."},
            {"type": "tool_use", "id": "x", "name": "mail", "input": {"to": "<PERSONNE_1>"}},
        ]
    }
    out = pseudo.response(answer, "s")
    assert out["content"][0]["text"] == "Bonjour Jean Martin, inconnu <PERSONNE_9>."
    assert out["content"][1]["input"] == {"to": "Jean Martin"}
    assert pseudo.response(answer, "other-session")["content"][0]["text"] == answer["content"][0]["text"]


def sse(*events) -> bytes:
    return b"".join(b"event: " + e["type"].encode() + b"\ndata: " + json.dumps(e).encode() + b"\n\n" for e in events)


def delta(text, index=0, kind="text_delta"):
    field = "text" if kind == "text_delta" else "partial_json"
    return {"type": "content_block_delta", "index": index, "delta": {"type": kind, field: text}}


def texts(raw: bytes) -> str:
    out = ""
    for line in raw.split(b"\n"):
        if line.startswith(b"data:"):
            event = json.loads(line[5:])
            if event["type"] == "content_block_delta":
                out += event["delta"].get("text", event["delta"].get("partial_json", ""))
    return out


def test_stream_reidentifies_pseudonyms_split_across_deltas_and_chunks(pseudo):
    pseudo.request({"messages": [{"role": "user", "content": f"Jean Martin, NIR {NIR}"}]}, "s")
    stream = sse(
        {"type": "message_start", "message": {"usage": {"input_tokens": 3}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        delta("Bonjour <PERS"),
        delta("ONNE_1>, votre <NI"),
        delta("R_1> est noté. Fin <"),
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "usage": {"output_tokens": 9}},
    )
    expected = f"Bonjour Jean Martin, votre {NIR} est noté. Fin <"
    for size in (1, 7, 64, len(stream)):  # any chunking of the upstream bytes gives the same text
        reid = StreamReidentifier(pseudo, "s")
        out = b"".join(reid.feed(stream[i : i + size]) for i in range(0, len(stream), size)) + reid.finish()
        assert texts(out) == expected, size
        assert b"message_delta" in out and out.count(b"\n\n") >= 7


def test_stream_escapes_json_in_tool_input(pseudo):
    pseudo.vault.pseudonym("s", "PERSONNE", 'Jean "JM" Martin')
    stream = sse(delta('{"to": "<PERSONNE', kind="input_json_delta"), delta('_1>"}', kind="input_json_delta"))
    reid = StreamReidentifier(pseudo, "s")
    out = reid.feed(stream) + reid.finish()
    assert json.loads(texts(out)) == {"to": 'Jean "JM" Martin'}


def test_pseudonym_like_text_from_another_session_is_left_alone(detector):
    a, b = Pseudonymiser(detector, Vault()), None
    a.request({"messages": [{"role": "user", "content": "Jean Martin"}]}, "s1")
    assert a.reidentify("<PERSONNE_1>", "s2") == "<PERSONNE_1>"
    assert b is None
