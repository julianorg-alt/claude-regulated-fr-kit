"""Demo of the running stack (make demo): what the client sends, what Bedrock receives, what comes back.

Everything is synthetic: the identifiers have valid check digits but belong to nobody, and the model is
the fake Bedrock of the kit, which echoes the prompt it receives.
"""

import json
import sys
import textwrap
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway" / "tests"))
from test_e2e import GATEWAY, bedrock_log, token  # noqa: E402

PROMPT = (
    "Bonjour, je suis Monsieur Hippolyte Zebrowskiquin. Mon numéro de sécurité sociale est "
    "2 99 12 99 123 456 62, mon IBAN FR76 0000 0012 3412 3456 7890 151. Résume ma situation."
)
MODEL = "claude-sonnet-5"
WIDTH = 100


def send(bearer: str | None, model: str = MODEL) -> tuple[int, dict]:
    body = {"model": model, "max_tokens": 128, "messages": [{"role": "user", "content": PROMPT}]}
    headers = {"content-type": "application/json", "anthropic-version": "2023-06-01"}
    if bearer:
        headers["authorization"] = f"Bearer {bearer}"
    request = urllib.request.Request(f"{GATEWAY}/anthropic/v1/messages", json.dumps(body).encode(), headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, {}


def user_text(body: dict) -> str:
    """Text of the last user message, whether the content is a string or a list of text blocks."""
    content = body["messages"][-1]["content"]
    if isinstance(content, str):
        return content
    return " ".join(part.get("text", "") for part in content)


def block(label: str, text: str) -> str:
    """One labelled text, wrapped at WIDTH with the continuation lines aligned under the first."""
    head = f"   {label:<13}: "
    return textwrap.fill(text, WIDTH, initial_indent=head, subsequent_indent=" " * len(head))


def report(sent: str, seen: str, status: int, answer: str) -> str:
    return "\n".join(
        [block("client sends", sent), block("Bedrock sees", seen), block("client gets", f"HTTP {status}, {answer}")]
    )


def main() -> int:
    print("1. Without a token:", send(None)[0])
    print(
        "2. Model with no EU route (claude-fable-5-2), refused with HTTP", send(token("alice"), "claude-fable-5-2")[0]
    )
    print("3. Authorised user, prompt with a NIR and an IBAN in clear text")
    status, answer = send(token("alice"))
    seen = user_text(bedrock_log()[-1]["body"])
    print(report(PROMPT, seen, status, answer["content"][0]["text"] if status == 200 else ""))
    return 0 if status == 200 and "<NIR_1>" in seen and "123 456 62" not in seen else 1


if __name__ == "__main__":
    raise SystemExit(main())
