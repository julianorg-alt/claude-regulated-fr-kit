"""promptfoo provider that replays recorded answers (backlog E6.1): CI runs without a model or a key.

One JSON file per task in ``cassettes/answers/<id>.json``:
{"id", "prompt_sha256", "output", "source": "recorded" | "synthetic", "model", "recorded_at"}.
A prompt that changed since the recording fails the test instead of replaying a stale answer.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
    """Hash of the prompt in canonical JSON: promptfoo hands the provider an indented copy of the chat
    prompt and stores a compact one in its output, so both are parsed and re-serialised the same way."""
    if isinstance(prompt, str):
        try:
            prompt = json.loads(prompt)
        except ValueError:
            return hashlib.sha256(prompt.encode()).hexdigest()
    text = json.dumps(plain_messages(prompt), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def call_api(prompt, options, context):
    task_id = (context or {}).get("vars", {}).get("id")
    directory = ROOT / (options or {}).get("config", {}).get("dir", "cassettes/answers")
    path = directory / f"{task_id}.json"
    if not task_id or not path.exists():
        return {"error": f"no cassette for task {task_id!r}: run make eval-live, then make eval-record"}
    cassette = json.loads(path.read_text(encoding="utf-8"))
    if cassette.get("prompt_sha256") != prompt_sha256(prompt):
        return {"error": f"cassette of {task_id} is stale: the prompt changed since it was recorded"}
    return {
        "output": cassette["output"],
        "metadata": {"source": cassette.get("source"), "model": cassette.get("model")},
    }
