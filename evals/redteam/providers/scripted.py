"""Scripted agent for the self-test of the live indirect injection tests (backlog E7.3).

`obedient` does exactly what the attack asks (every test must fail); `refusing` takes no action and
answers with a refusal (every test must pass). Running both in CI proves that the assertions of
`indirect.yaml` can tell a followed injection from a refused one, without any model.
"""

import json


def call_api(prompt, options, context):
    mode = (options or {}).get("config", {}).get("mode")
    attack = json.loads((context or {}).get("vars", {}).get("attack", "{}"))
    if mode == "obedient":
        if attack.get("kind") == "answer":
            doc = {"actions": [], "reponse": attack["content"]}
        else:
            doc = {"actions": [{"tool": attack["tool"], "arguments": attack.get("arguments", {})}], "reponse": "Fait."}
    elif mode == "refusing":
        doc = {"actions": [], "reponse": "Le document contient une instruction que je n'exécute pas."}
    else:
        return {"error": f"unknown mode {mode!r}"}
    return {"output": json.dumps(doc, ensure_ascii=False)}
