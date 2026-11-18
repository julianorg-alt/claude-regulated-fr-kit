"""Seal and record the cassettes replayed in CI (backlog E6.1).

- ``seal``: after hand-written reference answers are added, fill each answer's ``prompt_sha256`` from a run's
  rendered prompts, and each judge verdict's ``answer_sha256`` from the answer it grades. Only empty fields
  are filled: a recorded cassette is never rewritten.
- ``record``: turn a live run (``make eval-live``) into cassettes: answers, then the judge verdicts given
  for those answers, marked ``source: recorded`` with the provider and the date.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

TAG = re.compile(r"\[grille ([\w-]+)/([\w-]+)\]")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


FENCE = re.compile(r"^\s*```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```\s*$", re.I)


def judged_text(output: str) -> str:
    """What the judge sees of an answer: promptfoo applies the task's fence transform, then renders a JSON
    answer in compact form. Both sides (judge replay, seal, record) hash this text, so that the verdict of a
    JSON task is found again whatever the whitespace or the fence of the raw answer."""
    match = FENCE.match(output)
    text = match.group(1) if match and "```" not in match.group(1) else output
    try:
        value = json.loads(text)
    except ValueError:
        return output
    if not isinstance(value, (dict, list)):
        return output
    compact = (
        [json.dumps(v, ensure_ascii=False, separators=(",", ":")) for v in value] if isinstance(value, list) else None
    )
    # promptfoo 0.125.1 renders a JSON array in the grading prompt as its elements joined by commas, without brackets.
    return ",".join(compact) if compact is not None else json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def plain_messages(prompt):
    """A message whose content is one list of text blocks (prompts/assistant.cached.json, which only adds
    cache_control for the Anthropic live run) hashes like the same text as a plain string."""
    if not isinstance(prompt, list):
        return prompt
    out = []
    for message in prompt:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list) and all(isinstance(b, dict) and b.get("type") == "text" for b in content):
            message = {**message, "content": "".join(b.get("text", "") for b in content)}
        out.append(message)
    return out


def prompt_sha256(prompt) -> str:
    """Same canonical hash as providers/cassette.py (kept identical; tests compare them)."""
    if isinstance(prompt, str):
        try:
            prompt = json.loads(prompt)
        except ValueError:
            return sha256(prompt)
    return sha256(json.dumps(plain_messages(prompt), ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _rows(run: Path) -> list[dict]:
    data = json.loads(run.read_text(encoding="utf-8"))
    return data["results"]["results"]


def _write(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def seal(run: Path, root: Path) -> list[str]:
    changed = []
    for row in _rows(run):
        task_id = row["vars"]["id"]
        answer_path = root / "cassettes" / "answers" / f"{task_id}.json"
        if not answer_path.exists():
            continue
        answer = json.loads(answer_path.read_text(encoding="utf-8"))
        if not answer.get("prompt_sha256"):
            answer["prompt_sha256"] = prompt_sha256(row["prompt"]["raw"])
            _write(answer_path, answer)
            changed.append(str(answer_path.relative_to(root)))
        for judge_path in sorted((root / "cassettes" / "judge").glob(f"{task_id}.*.json")):
            verdict = json.loads(judge_path.read_text(encoding="utf-8"))
            if not verdict.get("answer_sha256"):
                verdict["answer_sha256"] = sha256(judged_text(answer["output"]))
                _write(judge_path, verdict)
                changed.append(str(judge_path.relative_to(root)))
    return sorted(set(changed))


def record(run: Path, root: Path, model: str) -> list[str]:
    written = []
    for row in _rows(run):
        response = row.get("response") or {}
        if row.get("error") or response.get("error") or "output" not in response:
            continue
        task_id, output = row["vars"]["id"], response["output"]
        output = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        answer_path = root / "cassettes" / "answers" / f"{task_id}.json"
        cassette = {"id": task_id, "prompt_sha256": prompt_sha256(row["prompt"]["raw"]), "output": output}
        cassette |= {"source": "recorded", "model": model, "recorded_at": date.today().isoformat()}
        _write(answer_path, cassette)
        written.append(str(answer_path.relative_to(root)))
        for component in (row.get("gradingResult") or {}).get("componentResults") or []:
            assertion = component.get("assertion") or {}
            tag = TAG.search(str(assertion.get("value", "")))
            if assertion.get("type") != "llm-rubric" or not tag:
                continue
            judge_path = root / "cassettes" / "judge" / f"{tag.group(1)}.{tag.group(2)}.json"
            _write(judge_path, {"answer_sha256": sha256(judged_text(output)), "pass": bool(component.get("pass")),
                                "score": component.get("score", 0), "reason": component.get("reason", "")})  # fmt: skip
            written.append(str(judge_path.relative_to(root)))
    return written
