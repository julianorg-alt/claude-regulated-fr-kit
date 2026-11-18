"""Copy closed audit segments to S3-compatible Object Lock storage (backlog E5.2), then delete them locally.

The shipper runs apart from the guard, with credentials that may only write objects: neither process can
delete what is stored. The bucket's default retention (Object Lock, compliance mode) does the rest. A
segment is deleted locally only after a HEAD shows the stored object has the same MD5 and a retention date.

Standard library only: SigV4 for the few S3 calls needed (HEAD, PUT), path-style addressing.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

LOG = logging.getLogger("crfr.shipper")
HEARTBEAT = Path(os.environ.get("AUDIT_SHIPPER_HEARTBEAT", "/tmp/shipper-alive"))  # noqa: S108 (container-local)
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _hmac(key: bytes, text: str) -> bytes:
    return hmac.new(key, text.encode(), hashlib.sha256).digest()


def sign(method: str, url: str, headers: dict[str, str], payload_sha256: str, access_key: str, secret_key: str,
         region: str, amz_date: str, service: str = "s3") -> str:  # fmt: skip
    """Authorization header value of an AWS Signature Version 4 request (header-based)."""
    parts = urllib.parse.urlsplit(url)
    canonical_headers = {k.lower().strip(): " ".join(v.split()) for k, v in headers.items()}
    canonical_headers["host"] = parts.netloc
    signed = ";".join(sorted(canonical_headers))
    query = "&".join(
        f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
        for k, v in sorted(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    )
    canonical = "\n".join(
        [
            method,
            urllib.parse.quote(parts.path or "/", safe="/-_.~"),
            query,
            "".join(f"{k}:{canonical_headers[k]}\n" for k in sorted(canonical_headers)),
            signed,
            payload_sha256,
        ]
    )
    day = amz_date[:8]
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(f"AWS4{secret_key}".encode(), day), region), service), "aws4_request")
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={signed}, Signature={signature}"


class S3:
    def __init__(self, endpoint: str, bucket: str, access_key: str, secret_key: str, region: str, clock=time.time):
        self.endpoint, self.bucket = endpoint.rstrip("/"), bucket
        self.access_key, self.secret_key, self.region, self.clock = access_key, secret_key, region, clock

    def _request(self, method: str, key: str, body: bytes = b"", extra: dict[str, str] | None = None,
                 query: str = "", read: bool = False):  # fmt: skip
        url = f"{self.endpoint}/{self.bucket}/{urllib.parse.quote(key, safe='/-_.~')}"
        if not key:
            url = url.rstrip("/")
        if query:
            url += "?" + query
        amz_date = datetime.fromtimestamp(self.clock(), UTC).strftime("%Y%m%dT%H%M%SZ")
        payload = hashlib.sha256(body).hexdigest() if body else EMPTY_SHA256
        headers = {"x-amz-date": amz_date, "x-amz-content-sha256": payload, **(extra or {})}
        headers["Authorization"] = sign(
            method, url, headers, payload, self.access_key, self.secret_key, self.region, amz_date
        )
        request = urllib.request.Request(url, data=body or None, method=method, headers=headers)  # noqa: S310
        try:
            with urllib.request.urlopen(request, timeout=30) as answer:  # noqa: S310 (configured endpoint)
                content = answer.read() if read else b""
                return (answer.status, dict(answer.headers), content) if read else (answer.status, dict(answer.headers))
        except urllib.error.HTTPError as error:
            return (error.code, dict(error.headers), error.read()) if read else (error.code, dict(error.headers))

    def head(self, key: str):
        return self._request("HEAD", key)

    def put(self, key: str, body: bytes):
        md5 = base64.b64encode(hashlib.md5(body).digest()).decode()  # noqa: S324 (integrity header required by Object Lock)
        return self._request("PUT", key, body, {"Content-MD5": md5, "Content-Type": "application/x-ndjson"})

    def get(self, key: str):
        return self._request("GET", key, read=True)

    def delete(self, key: str, version_id: str):
        return self._request("DELETE", key, query=f"versionId={urllib.parse.quote(version_id, safe='')}", read=True)

    def create_locked_bucket(self, days: int) -> None:
        """Local stack only: in AWS the bucket comes from Terraform (module gateway-audit-store)."""
        status, _, answer = self._request("PUT", "", extra={"x-amz-bucket-object-lock-enabled": "true"}, read=True)
        if status not in (200, 409):
            raise OSError(f"bucket creation refused: HTTP {status} {answer[:200]!r}")
        rule = (
            '<ObjectLockConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            "<ObjectLockEnabled>Enabled</ObjectLockEnabled><Rule><DefaultRetention>"
            f"<Mode>COMPLIANCE</Mode><Days>{int(days)}</Days></DefaultRetention></Rule></ObjectLockConfiguration>"
        ).encode()
        md5 = base64.b64encode(hashlib.md5(rule).digest()).decode()  # noqa: S324 (required header)
        status, _, answer = self._request("PUT", "", rule, {"Content-MD5": md5}, query="object-lock=", read=True)
        if status != 200:
            raise OSError(f"Object Lock configuration refused: HTTP {status} {answer[:200]!r}")


def object_key(prefix: str, path: Path) -> str:
    stamp = path.name.split("-", 1)[1]  # audit-20261116T120000Z.jsonl
    return f"{prefix.strip('/')}/{stamp[:4]}/{stamp[4:6]}/{stamp[6:8]}/{path.name}"


def closed_segments(directory: Path, segment_s: int, now: float, grace_s: float = 2.0) -> list[Path]:
    out = []
    for path in sorted(directory.glob("audit-*.jsonl")):
        start = datetime.strptime(path.name[6:-6], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).timestamp()
        if start + segment_s + grace_s <= now:
            out.append(path)
    return out


def ship_once(s3: S3, directory: Path, segment_s: int, prefix: str = "audit", now: float | None = None) -> list[str]:
    shipped = []
    for path in closed_segments(directory, segment_s, time.time() if now is None else now):
        body = path.read_bytes()
        key = object_key(prefix, path)
        status, headers = s3.head(key)
        if status == 404:
            status, headers = s3.put(key, body)
            if status != 200:
                LOG.error("upload of %s refused: HTTP %s", key, status)
                continue
            status, headers = s3.head(key)
        lowered = {k.lower(): v for k, v in headers.items()}
        etag = lowered.get("etag", "").strip('"')
        if status != 200 or etag != hashlib.md5(body).hexdigest():  # noqa: S324 (ETag of a single-part upload)
            LOG.error("%s: stored copy differs or is missing (HTTP %s), segment kept", key, status)
            continue
        if "x-amz-object-lock-retain-until-date" not in lowered:
            LOG.error("%s: stored without retention, segment kept; check the bucket's Object Lock", key)
            continue
        path.unlink()
        shipped.append(key)
        LOG.info("shipped %s, retained until %s", key, lowered["x-amz-object-lock-retain-until-date"])
    return shipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ship closed audit segments to Object Lock storage")
    parser.add_argument("--audit-dir", type=Path, default=Path(os.environ.get("GUARD_AUDIT_DIR", "/data/audit")))
    parser.add_argument("--endpoint", default=os.environ.get("AUDIT_S3_ENDPOINT", "https://s3.eu-west-3.amazonaws.com"))
    parser.add_argument("--bucket", default=os.environ.get("AUDIT_S3_BUCKET", "crfr-audit"))
    parser.add_argument("--region", default=os.environ.get("AUDIT_S3_REGION", "eu-west-3"))
    parser.add_argument("--segment-s", type=int, default=int(os.environ.get("AUDIT_SEGMENT_S", "300")))
    parser.add_argument("--interval-s", type=float, default=float(os.environ.get("AUDIT_SHIP_INTERVAL_S", "10")))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--create-bucket-days", type=int, default=int(os.environ.get("AUDIT_CREATE_BUCKET_DAYS", "0")),
                        help="local stack: create the bucket with Object Lock and this default retention")  # fmt: skip
    parser.add_argument("--get", metavar="KEY", help="print a stored object (checks)")
    parser.add_argument("--try-delete", metavar="KEY", help="try to delete the current version of an object (checks)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    access, secret = os.environ.get("AWS_ACCESS_KEY_ID"), os.environ.get("AWS_SECRET_ACCESS_KEY")
    if not access or not secret:
        parser.error("AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required")
    s3 = S3(args.endpoint, args.bucket, access, secret, args.region)
    if args.get:
        status, _, content = s3.get(args.get)
        print(content.decode("utf-8", "replace") if status == 200 else f"HTTP {status}")
        return 0 if status == 200 else 1
    if args.try_delete:
        status, headers = s3.head(args.try_delete)
        version = {k.lower(): v for k, v in headers.items()}.get("x-amz-version-id", "")
        deleted, _, _ = s3.delete(args.try_delete, version)
        after, _ = s3.head(args.try_delete)
        print(json.dumps({"head": status, "version": version, "delete": deleted, "head_after": after}))
        return 0
    if args.create_bucket_days:
        for attempt in range(30):
            try:
                s3.create_locked_bucket(args.create_bucket_days)
                break
            except (OSError, urllib.error.URLError) as error:
                if attempt == 29:
                    raise
                LOG.info("storage not ready (%s), retrying", error)
                time.sleep(1)
    args.audit_dir.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            ship_once(s3, args.audit_dir, args.segment_s)
        except OSError as error:  # storage unreachable: keep the segments, try again
            LOG.error("shipping failed: %s", error)
        if args.once:
            return 0
        HEARTBEAT.touch()  # read by the container healthcheck
        time.sleep(args.interval_s)


if __name__ == "__main__":
    raise SystemExit(main())
