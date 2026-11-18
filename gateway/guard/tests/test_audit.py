import hashlib
import hmac
import json

import pytest

from crfr_guard.audit import AuditLog, ContentLog, KmsMac, LocalMac, fingerprint, read_segments, verify

KEY = b"k" * 32


class Clock:
    def __init__(self, now=1_790_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def log(tmp_path, clock=None, segment_s=300):
    return AuditLog(tmp_path / "audit", LocalMac(KEY), segment_s=segment_s, stream=None, clock=clock or Clock())


def test_fingerprint_is_an_hmac_of_the_body_digest():
    body = b'{"messages":[{"role":"user","content":"secret"}]}'
    expected = hmac.new(KEY, hashlib.sha256(body).digest(), hashlib.sha256).hexdigest()
    assert fingerprint(LocalMac(KEY), body) == expected
    assert fingerprint(LocalMac(b"x" * 32), body) != expected


def test_local_mac_refuses_short_keys():
    with pytest.raises(ValueError):
        LocalMac(b"short")


def test_kms_mac_sends_only_a_digest():
    class Client:
        def __init__(self):
            self.calls = []

        def generate_mac(self, **kwargs):
            self.calls.append(kwargs)
            return {"Mac": b"\x01\x02", "KeyId": kwargs["KeyId"]}

    client = Client()
    mac = KmsMac(client, "alias/crfr-audit")
    assert fingerprint(mac, b"x" * 10_000) == "0102"
    (call,) = client.calls
    assert call["MacAlgorithm"] == "HMAC_SHA_256" and call["KeyId"] == "alias/crfr-audit"
    assert len(call["Message"]) == 32  # GenerateMac accepts at most 4096 bytes


def test_entries_are_chained_and_verify(tmp_path):
    audit = log(tmp_path)
    for i in range(3):
        audit.write(event="request", request_id=str(i), user="alice")
    lines = read_segments(tmp_path / "audit")
    entries = [json.loads(line) for line in lines]
    assert entries[0]["prev"] == ""
    assert [e["prev"] for e in entries[1:]] == [e["mac"] for e in entries[:-1]]
    assert verify(lines, LocalMac(KEY)) == (True, 3, None)


@pytest.mark.parametrize("tamper", ["edit", "delete", "swap", "wrong-key"])
def test_tampering_is_detected(tmp_path, tamper):
    audit = log(tmp_path)
    for i in range(3):
        audit.write(event="request", request_id=str(i), decision="refused")
    lines = read_segments(tmp_path / "audit")
    mac = LocalMac(KEY)
    if tamper == "edit":
        lines[1] = lines[1].replace('"refused"', '"admitted"')
    elif tamper == "delete":
        del lines[1]
    elif tamper == "swap":
        lines[0], lines[1] = lines[1], lines[0]
    else:
        mac = LocalMac(b"z" * 32)
    ok, _, error = verify(lines, mac)
    assert not ok and error


def test_segments_rotate_and_the_chain_survives_a_restart(tmp_path):
    clock = Clock()
    audit = log(tmp_path, clock, segment_s=60)
    audit.write(event="a")
    clock.now += 61
    audit.write(event="b")
    restarted = log(tmp_path, clock, segment_s=60)  # new process, same directory
    restarted.write(event="c")
    files = sorted((tmp_path / "audit").glob("audit-*.jsonl"))
    assert len(files) == 2
    assert verify(read_segments(tmp_path / "audit"), LocalMac(KEY)) == (True, 3, None)


def test_chain_head_survives_shipped_segments(tmp_path):
    clock = Clock()
    audit = log(tmp_path, clock, segment_s=60)
    audit.write(event="a")
    first = sorted((tmp_path / "audit").glob("audit-*.jsonl"))[0]
    shipped = first.read_text().splitlines()
    first.unlink()  # the shipper removes a segment once it is stored
    clock.now += 61
    log(tmp_path, clock, segment_s=60).write(event="b")
    assert verify(shipped + read_segments(tmp_path / "audit"), LocalMac(KEY)) == (True, 2, None)


def test_none_values_are_dropped_and_no_body_is_written(tmp_path):
    audit = log(tmp_path)
    entry = audit.write(event="request", reason=None)
    assert "reason" not in entry and {"ts", "prev", "mac", "event"} <= set(entry)


def test_content_log_keeps_short_retention(tmp_path):
    clock = Clock()
    content = ContentLog(tmp_path / "content", retention_days=2, clock=clock)
    content.write(request_id="1", request=b'{"q":"<PERSONNE_1>"}', response=b'{"a":"ok"}')
    clock.now += 3 * 86400
    content.write(request_id="2", request=b"{}", response=b"{}")
    files = sorted(p.name for p in (tmp_path / "content").glob("content-*.jsonl"))
    assert len(files) == 1
    (entry,) = [json.loads(line) for line in (tmp_path / "content" / files[0]).read_text().splitlines()]
    assert entry["request_id"] == "2" and entry["request"] == "{}"


def test_admin_verifies_segments_and_fingerprints(tmp_path, monkeypatch, capsys):
    from crfr_guard import admin

    monkeypatch.setenv("CRFR_AUDIT_KEY", KEY.hex())
    audit = log(tmp_path)
    raw = b'{"model":"m"}'
    audit.write(event="request", prompt_hmac=fingerprint(LocalMac(KEY), raw))
    audit.write(event="response")
    files = sorted((tmp_path / "audit").glob("audit-*.jsonl"))
    assert admin.main(["verify-audit", *map(str, files)]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "lines": 2, "error": None}
    body = tmp_path / "body.json"
    body.write_bytes(raw)
    assert admin.main(["fingerprint", str(body)]) == 0
    assert capsys.readouterr().out.strip() == json.loads(read_segments(tmp_path / "audit")[0])["prompt_hmac"]
    files[0].write_text(files[0].read_text().replace('"response"', '"request"'))
    assert admin.main(["verify-audit", *map(str, files)]) == 1
