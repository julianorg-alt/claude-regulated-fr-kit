"""Negative control (backlog E6.3): an answer that does nothing must fail every task.

Used with ``promptfooconfig.negative.yaml``. The judge there always says yes, so only the code graders
decide: a task that this answer passes has no code grader that bites, and the check fails.
"""

import json


def call_api(prompt, options, context):
    return {"output": "Bien reçu, je transmets votre demande."}


def judge(prompt, options, context):
    return {"output": json.dumps({"pass": True, "score": 1, "reason": "negative control: judge disabled"})}
