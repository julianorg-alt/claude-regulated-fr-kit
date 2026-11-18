"""Exit drill (backlog E10.2): the gateway runs the *switch* configuration, where the primary aliases
themselves go to the second provider. Run by ``make exit-drill``, never by ``make e2e`` (it needs the stack
started with ``AIGW_CONFIG=aigw-switch.yaml``). Standard library only.
"""

import json
import unittest

from test_e2e import bedrock_log, call, token
from test_e2e_exit import exit_log


class SwitchDrill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.alice = token("alice")

    def test_primary_aliases_are_served_by_the_second_provider_and_nothing_reaches_bedrock(self):
        before = len(bedrock_log())
        for alias, model in (("claude-sonnet-5", "exit-model-fr"), ("claude-haiku-4-5", "exit-model-fr-small")):
            marker = f"canari-bascule-{alias}"
            with self.subTest(alias=alias):
                status, body = call(alias, self.alice, marker)
                self.assertEqual(status, 200, body)
                self.assertEqual(body["type"], "message")
                self.assertIn(marker, body["content"][0]["text"])
                entry = next(e for e in reversed(exit_log()) if marker in json.dumps(e["body"]))
                self.assertEqual(entry["model"], model)
        self.assertEqual(len(bedrock_log()), before, "after the switch, Bedrock receives nothing")

    def test_the_aliases_not_switched_keep_their_bedrock_route(self):
        before = len(bedrock_log())
        self.assertEqual(call("claude-opus-5-5", self.alice, "reste sur bedrock")[0], 200)
        self.assertEqual(len(bedrock_log()), before + 1)

    def test_controls_still_apply_after_the_switch(self):
        self.assertEqual(call("claude-sonnet-5", None)[0], 401)
        self.assertEqual(call("claude-opus-5-5", token("carol"))[0], 403)


if __name__ == "__main__":
    unittest.main()
