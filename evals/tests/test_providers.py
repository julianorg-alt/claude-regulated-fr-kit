import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "providers"))
import cassette  # noqa: E402
import judge  # noqa: E402


def test_cassette_replays_and_refuses_stale_prompts(tmp_path, monkeypatch):
    monkeypatch.setattr(cassette, "ROOT", tmp_path)
    (tmp_path / "cassettes" / "answers").mkdir(parents=True)
    prompt = '[{"role":"user","content":"q"}]'
    (tmp_path / "cassettes" / "answers" / "t-01.json").write_text(
        json.dumps(
            {
                "prompt_sha256": cassette.prompt_sha256(prompt),
                "output": "réponse",
                "source": "synthetic",
            }
        )
    )
    assert cassette.call_api(prompt, {}, {"vars": {"id": "t-01"}})["output"] == "réponse"
    assert "stale" in cassette.call_api(prompt.replace("q", "autre"), {}, {"vars": {"id": "t-01"}})["error"]
    assert "no cassette" in cassette.call_api(prompt, {}, {"vars": {"id": "t-02"}})["error"]


def test_judge_replays_only_for_the_answer_it_graded(tmp_path, monkeypatch):
    monkeypatch.setattr(judge, "ROOT", tmp_path)
    (tmp_path / "cassettes" / "judge").mkdir(parents=True)
    verdict = {
        "answer_sha256": hashlib.sha256(b"bonne reponse").hexdigest(),
        "pass": True,
        "score": 1,
        "reason": "ok",
    }
    (tmp_path / "cassettes" / "judge" / "t-01.exactitude.json").write_text(json.dumps(verdict))

    def grading(output):
        user = (
            f"<Task>\nquestion et document\n</Task>\n<Output>\n{output}\n</Output>\n"
            "<Rubric>\n[grille t-01/exactitude] critère\n</Rubric>"
        )
        system = "Examples:\n<Output>Hello world</Output>"
        return json.dumps([{"role": "system", "content": system}, {"role": "user", "content": user}])

    assert json.loads(judge.call_api(grading("bonne reponse"), {}, {})["output"])["pass"] is True
    assert "another answer" in judge.call_api(grading("autre"), {}, {})["error"]
    assert "tag" in judge.call_api("<Task>t</Task><Output>x</Output>", {}, {})["error"]


def test_prompt_hash_ignores_json_layout_and_matches_the_seal_script():
    from crfr_eval.cassettes import prompt_sha256

    compact = '[{"role":"user","content":"é"}]'
    indented = '[\n  {\n    "role": "user",\n    "content": "é"\n  }\n]'
    assert cassette.prompt_sha256(compact) == cassette.prompt_sha256(indented) == prompt_sha256(indented)
    assert cassette.prompt_sha256("plain text") == prompt_sha256("plain text")


def test_cached_live_prompt_is_the_same_prompt_and_hashes_like_it():
    """prompts/assistant.cached.json adds cache_control to the system block for the Anthropic live run. It must say
    exactly what assistant.json says and hash identically, so recorded cassettes still replay in CI."""
    from crfr_eval.cassettes import prompt_sha256

    root = Path(__file__).resolve().parent.parent / "prompts"
    plain = json.loads((root / "assistant.json").read_text(encoding="utf-8"))
    cached = json.loads((root / "assistant.cached.json").read_text(encoding="utf-8"))
    block = cached[0]["content"]
    assert isinstance(block, list) and len(block) == 1 and block[0]["cache_control"] == {"type": "ephemeral"}
    assert block[0]["text"] == plain[0]["content"] and cached[1] == plain[1]  # the task message is never cached
    assert cassette.prompt_sha256(cached) == cassette.prompt_sha256(plain) == prompt_sha256(cached)
    assert cassette.prompt_sha256(json.dumps(cached, indent=2)) == cassette.prompt_sha256(plain)
