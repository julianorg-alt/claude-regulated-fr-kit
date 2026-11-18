"""Replace personal data by pseudonyms in Anthropic Messages requests, and restore it in answers.

``Pseudonymiser.request(body, session)`` rewrites every text the model reads: the system prompt,
message text, tool results and tool inputs. ``reidentify`` puts the originals back in a buffered
answer; ``StreamReidentifier`` does it on server-sent events, holding back a pseudonym split across
two deltas until it is complete.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .detectors import Detector
from .vault import Vault

PSEUDONYM = re.compile(r"<([A-Z]+(?:_[A-Z]+)*)_(\d{1,6})>")
_PARTIAL_MAX = 40  # longest pseudonym prefix worth holding back, e.g. "<NUMERO_FISCAL_123"


@dataclass
class Report:
    """What was replaced, by type (counts only: no value leaves this object)."""

    counts: dict[str, int] = field(default_factory=dict)

    def add(self, kind: str) -> None:
        self.counts[kind] = self.counts.get(kind, 0) + 1


class Pseudonymiser:
    def __init__(self, detector: Detector, vault: Vault):
        self.detector, self.vault = detector, vault

    def text(self, value: str, session: str, report: Report | None = None) -> str:
        out, last = [], 0
        for span in self.detector.find(value):
            out.append(value[last : span.start])
            out.append(self.vault.pseudonym(session, span.type, span.text(value)))
            if report is not None:
                report.add(span.type)
            last = span.end
        out.append(value[last:])
        return "".join(out)

    def request(self, body: dict, session: str) -> tuple[dict, Report]:
        report = Report()
        rewritten = dict(body)
        if "system" in body:
            rewritten["system"] = self._walk(body["system"], session, report)
        if "messages" in body:
            rewritten["messages"] = [
                {**m, "content": self._walk(m.get("content"), session, report)} if isinstance(m, dict) else m
                for m in body["messages"]
            ]
        return rewritten, report

    def _walk(self, node, session: str, report: Report):
        if isinstance(node, str):
            return self.text(node, session, report)
        if isinstance(node, list):
            return [self._walk(item, session, report) for item in node]
        if isinstance(node, dict):
            out = {}
            for key, value in node.items():
                if key == "input":  # tool inputs: free-form JSON, every string may carry personal data
                    out[key] = self._walk_all(value, session, report)
                    continue
                # Structural fields (type, id, name, cache_control, media type) are not personal data.
                if key in ("text", "content", "input") or (key not in ("type", "id", "tool_use_id", "name",
                                                                         "cache_control", "source", "media_type")
                                                          and isinstance(value, dict | list)):  # fmt: skip
                    out[key] = self._walk(value, session, report)
                else:
                    out[key] = value
            return out
        return node

    def _walk_all(self, node, session: str, report: Report):
        if isinstance(node, str):
            return self.text(node, session, report)
        if isinstance(node, list):
            return [self._walk_all(n, session, report) for n in node]
        if isinstance(node, dict):
            return {k: self._walk_all(v, session, report) for k, v in node.items()}
        return node

    def reidentify(self, value: str, session: str, json_escape: bool = False) -> str:
        def restore(match: re.Match) -> str:
            original = self.vault.original(session, match.group(1), int(match.group(2)))
            if original is None:
                return match.group(0)
            return json.dumps(original)[1:-1] if json_escape else original

        return PSEUDONYM.sub(restore, value)

    def response(self, body: dict, session: str) -> dict:
        """Re-identify a buffered Anthropic Messages response."""
        content = []
        for block in body.get("content") or []:
            if not isinstance(block, dict):
                content.append(block)
            elif block.get("type") == "text" and isinstance(block.get("text"), str):
                content.append({**block, "text": self.reidentify(block["text"], session)})
            elif block.get("type") == "tool_use":
                content.append({**block, "input": self._restore_tree(block.get("input"), session)})
            else:
                content.append(block)
        return {**body, "content": content} if "content" in body else body

    def _restore_tree(self, node, session: str):
        if isinstance(node, str):
            return self.reidentify(node, session)
        if isinstance(node, list):
            return [self._restore_tree(n, session) for n in node]
        if isinstance(node, dict):
            return {k: self._restore_tree(v, session) for k, v in node.items()}
        return node


def _held_back(text: str) -> int:
    """Index from which the tail of ``text`` may be the start of a pseudonym, or len(text)."""
    start = text.rfind("<")
    if start == -1 or ">" in text[start:] or len(text) - start > _PARTIAL_MAX:
        return len(text)
    if re.fullmatch(r"<[A-Z_]*\d*", text[start:]):
        return start
    return len(text)


class StreamReidentifier:
    """Re-identify a stream of server-sent events, one ``feed`` per chunk received from upstream.

    Works event by event (an event ends with a blank line), so that a pseudonym held back at the end
    of a content block can be released as its own delta event just before ``content_block_stop``.
    """

    def __init__(self, pseudonymiser: Pseudonymiser, session: str):
        self.p, self.session = pseudonymiser, session
        self._buffer = b""
        self._pending: dict[int, tuple[str, str]] = {}  # block index -> (delta type, held-back text)

    def feed(self, chunk: bytes) -> bytes:
        self._buffer += chunk.replace(b"\r\n", b"\n")
        *events, self._buffer = self._buffer.split(b"\n\n")
        return b"".join(self._event(e) for e in events)

    def finish(self) -> bytes:
        out = self._event(self._buffer) if self._buffer.strip() else self._buffer
        self._buffer = b""
        for index in list(self._pending):
            out = self._flush(index) + out
        return out

    def _event(self, raw: bytes) -> bytes:
        lines = raw.split(b"\n")
        data_at = next((i for i, line in enumerate(lines) if line.startswith(b"data:")), None)
        if data_at is None:
            return raw + b"\n\n"
        try:
            event = json.loads(lines[data_at][5:].strip())
        except ValueError:
            return raw + b"\n\n"
        if not isinstance(event, dict):
            return raw + b"\n\n"
        kind = event.get("type")
        if kind == "content_block_delta" and isinstance(event.get("delta"), dict):
            index, delta = event.get("index", 0), event["delta"]
            field_name = {"text_delta": "text", "input_json_delta": "partial_json"}.get(delta.get("type"))
            if field_name and isinstance(delta.get(field_name), str):
                _, held = self._pending.pop(index, (delta["type"], ""))
                text = held + delta[field_name]
                cut = _held_back(text)
                if cut < len(text):
                    self._pending[index] = (delta["type"], text[cut:])
                escape = field_name == "partial_json"
                event = {**event, "delta": {**delta, field_name: self.p.reidentify(text[:cut], self.session, escape)}}
                lines[data_at] = b"data: " + json.dumps(event, ensure_ascii=False).encode()
                return b"\n".join(lines) + b"\n\n"
        if kind == "content_block_stop":
            return self._flush(event.get("index", 0)) + raw + b"\n\n"
        return raw + b"\n\n"

    def _flush(self, index: int) -> bytes:
        if index not in self._pending:
            return b""
        delta_type, held = self._pending.pop(index)
        field_name = "text" if delta_type == "text_delta" else "partial_json"
        text = self.p.reidentify(held, self.session, field_name == "partial_json")
        event = {"type": "content_block_delta", "index": index, "delta": {"type": delta_type, field_name: text}}
        return b"event: content_block_delta\ndata: " + json.dumps(event, ensure_ascii=False).encode() + b"\n\n"
