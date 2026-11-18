"""promptfoo grading provider that replays recorded judge verdicts (backlog E6.3).

Each rubric starts with a tag ``[grille <task id>/<dimension>]``. The verdict for that tag is in
``cassettes/judge/<task id>.<dimension>.json``: {"answer_sha256", "pass", "score", "reason"}. It applies
only to the answer it was given for: if the graded output differs (new model, new answer), the verdict is
not replayed and the test errors, so that a judge result is never reused for an answer it did not see.
The grading prompt must also carry the task and its source document in a <Task> block.
A verdict whose reason starts with "INCONNU" means the judge could not decide: the report sends it to a human.
"""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAG = re.compile(r"\[grille ([\w-]+)/([\w-]+)\]")
OUTPUT = re.compile(r"<Output>\n?(.*?)\n?</Output>", re.S)
TASK = re.compile(r"<Task>\n?(.*?)\n?</Task>", re.S)


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


def _text(prompt) -> str:
    if isinstance(prompt, str):
        try:
            prompt = json.loads(prompt)
        except ValueError:
            return prompt
    if isinstance(prompt, list):
        return "\n".join(m.get("content", "") for m in prompt if isinstance(m, dict))
    return str(prompt)


def call_api(prompt, options, context):
    text = _text(prompt)
    # The grading prompt's own examples come first; the graded output is the last <Output> block.
    tag, outputs = TAG.search(text), OUTPUT.findall(text)
    if not tag or not outputs:
        return {"error": "rubric without [grille <id>/<dimension>] tag, or no <Output> in the grading prompt"}
    # The grading prompt (prompts/judge.json) must carry the task with its source document: without it the live
    # judge answers INCONNU on everything that depends on the document. Replay checks it so CI proves it.
    task = TASK.search(text)
    if not task or not task.group(1).strip():
        return {"error": "grading prompt without a non-empty <Task> block: the judge would not see the source document"}
    task_id, dimension = tag.groups()
    path = ROOT / "cassettes" / "judge" / f"{task_id}.{dimension}.json"
    if not path.exists():
        return {"error": f"no judge cassette for {task_id}/{dimension}"}
    verdict = json.loads(path.read_text(encoding="utf-8"))
    if verdict.get("answer_sha256") != hashlib.sha256(judged_text(outputs[-1]).encode()).hexdigest():
        return {"error": f"judge cassette of {task_id}/{dimension} was recorded for another answer"}
    return {"output": json.dumps({k: verdict[k] for k in ("pass", "score", "reason")}, ensure_ascii=False)}
