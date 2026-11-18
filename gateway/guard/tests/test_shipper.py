import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from crfr_guard.shipper import EMPTY_SHA256, S3, closed_segments, object_key, ship_once, sign


def test_sigv4_matches_the_aws_s3_get_object_example():
    # Example "GET Object" of the S3 API reference (Signature Version 4, header-based authentication).
    headers = {"Range": "bytes=0-9", "x-amz-content-sha256": EMPTY_SHA256, "x-amz-date": "20130524T000000Z"}
    auth = sign("GET", "https://examplebucket.s3.amazonaws.com/test.txt", headers, EMPTY_SHA256,
                "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "us-east-1",
                "20130524T000000Z")  # fmt: skip
    assert auth == (
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, "
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )


class FakeS3(BaseHTTPRequestHandler):
    store: dict = {}
    retention = True
    corrupt = False

    def log_message(self, *args):
        pass

    def do_HEAD(self):
        body = self.store.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        digest = hashlib.md5(b"x" if self.corrupt else body).hexdigest()  # noqa: S324
        self.send_header("ETag", f'"{digest}"')
        if self.retention:
            self.send_header("x-amz-object-lock-retain-until-date", "2027-05-16T00:00:00Z")
        self.end_headers()

    def do_PUT(self):
        assert self.headers["Authorization"].startswith("AWS4-HMAC-SHA256 ")
        assert self.headers["Content-MD5"]
        self.store[self.path] = self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.end_headers()


@pytest.fixture
def s3():
    FakeS3.store, FakeS3.retention, FakeS3.corrupt = {}, True, False
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeS3)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield S3(f"http://127.0.0.1:{server.server_port}", "audit", "test", "test-secret", "eu-west-3")
    server.shutdown()


def segments(tmp_path):
    directory = tmp_path / "audit"
    directory.mkdir()
    (directory / "audit-20261116T120000Z.jsonl").write_text('{"a":1}\n')
    (directory / "audit-20261116T120500Z.jsonl").write_text('{"b":2}\n')
    return directory


NOW = 1_794_830_710.0  # 2026-11-16T12:05:10Z: the first segment is closed, the second is open


def test_only_closed_segments_are_shipped(tmp_path):
    directory = segments(tmp_path)
    assert [p.name for p in closed_segments(directory, 300, NOW)] == ["audit-20261116T120000Z.jsonl"]
    assert object_key("audit", directory / "audit-20261116T120000Z.jsonl") == (
        "audit/2026/11/16/audit-20261116T120000Z.jsonl"
    )


def test_segment_is_deleted_only_once_stored_with_retention(tmp_path, s3):
    directory = segments(tmp_path)
    assert ship_once(s3, directory, 300, now=NOW) == ["audit/2026/11/16/audit-20261116T120000Z.jsonl"]
    assert FakeS3.store == {"/audit/audit/2026/11/16/audit-20261116T120000Z.jsonl": b'{"a":1}\n'}
    assert sorted(p.name for p in directory.iterdir()) == ["audit-20261116T120500Z.jsonl"]


@pytest.mark.parametrize("fault", ["no-retention", "corrupt"])
def test_segment_is_kept_when_the_stored_copy_is_not_safe(tmp_path, s3, fault):
    FakeS3.retention = fault != "no-retention"
    FakeS3.corrupt = fault == "corrupt"
    directory = segments(tmp_path)
    assert ship_once(s3, directory, 300, now=NOW) == []
    assert len(list(directory.iterdir())) == 2
