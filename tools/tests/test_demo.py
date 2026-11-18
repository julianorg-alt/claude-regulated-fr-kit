"""The demo must print the three texts in full, wrapped, never cut."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gateway" / "tests"))
spec = importlib.util.spec_from_file_location("demo", ROOT / "scripts" / "demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)

SENT = demo.PROMPT
SEEN = (
    "Bonjour, je suis Monsieur <PERSONNE_1>. Mon numéro de sécurité sociale est <NIR_1>, "
    "mon IBAN <IBAN_1>. Résume ma situation."
)
ANSWER = "[fake-bedrock eu.anthropic.claude-sonnet-5] " + SENT


def flat(text: str) -> str:
    return " ".join(text.split())


def test_block_keeps_full_text_and_wraps():
    block = demo.block("Bedrock sees", SEEN)
    assert flat(block.split(":", 1)[1]) == SEEN
    assert all(len(line) <= demo.WIDTH for line in block.splitlines())
    assert len(block.splitlines()) > 1


def test_report_has_final_sentence_on_bedrock_and_client_sides():
    out = demo.report(SENT, SEEN, 200, ANSWER)
    assert "Résume ma situation." in flat(out.split("Bedrock sees")[1].split("client gets")[0])
    assert flat(out.split("client gets")[1]).endswith("Résume ma situation.")
    assert "…" not in out


def test_user_text_reads_string_and_block_content():
    assert demo.user_text({"messages": [{"role": "user", "content": "a"}]}) == "a"
    blocks = [{"text": "a"}, {"text": "b"}]
    assert demo.user_text({"messages": [{"role": "user", "content": blocks}]}) == "a b"
