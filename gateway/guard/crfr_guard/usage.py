"""Token usage from an Anthropic Messages response, buffered JSON or server-sent events."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read_input_tokens + self.cache_creation_input_tokens


FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def _ints(raw: dict | None) -> dict[str, int]:
    out = {}
    for field in FIELDS:
        value = (raw or {}).get(field)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            out[field] = value
    return out


def parse(body: bytes, content_type: str = "") -> Usage | None:
    """Return the usage reported by the model, or None if the body carries none."""
    if "text/event-stream" in content_type or body.lstrip().startswith((b"event:", b"data:")):
        return _parse_sse(body)
    try:
        doc = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get("usage"), dict):
        return None
    return Usage(**_ints(doc["usage"]))


def _parse_sse(body: bytes) -> Usage | None:
    # message_start carries input and cache counts; message_delta carries the cumulative output count
    # (and, on recent models, may repeat the input counts). Later values win.
    found: dict[str, int] = {}
    seen = False
    for line in body.decode("utf-8", "replace").splitlines():
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[5:].strip())
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "message_start" and isinstance(event.get("message"), dict):
            found.update(_ints(event["message"].get("usage")))
            seen = True
        elif event.get("type") == "message_delta":
            found.update(_ints(event.get("usage")))
            seen = True
    return Usage(**found) if seen else None
