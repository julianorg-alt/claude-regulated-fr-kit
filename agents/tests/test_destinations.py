"""Destination allowlist of tool arguments (backlog E7.4: no exfiltration through a read tool)."""

import pytest
from crfr_agents.approval import ToolCall
from crfr_agents.destinations import DestinationPolicy

POLICY = DestinationPolicy.from_dict(
    {
        "tools": {
            "lire_url": {"destination": {"argument": "url", "kind": "url", "allowed": ["intranet.banque.example"]}},
            "envoyer_courriel": {"destination": {"argument": "a", "kind": "email", "allowed": ["banque.example"]}},
            "lire_dossier": {"effect": "read"},
        }
    }
)


def check(tool, **arguments):
    return POLICY.check(ToolCall("agent", tool, arguments))


def test_tool_without_destination_is_not_concerned():
    assert check("lire_dossier", id="1").allowed


def test_allowed_url_host_passes():
    assert check("lire_url", url="https://intranet.banque.example/taux?annee=2026").allowed


@pytest.mark.parametrize(
    "url",
    [
        "https://collecte.attaquant.example/?d=secret",
        "https://intranet.banque.example.attaquant.example/",
        "https://intranet.banque.example@attaquant.example/",
        "http://intranet.banque.example/",  # plain HTTP
        "file:///etc/passwd",
        "not a url",
    ],
)
def test_other_destinations_are_refused(url):
    decision = check("lire_url", url=url)
    assert not decision.allowed and decision.reason == "destination-not-allowed"


def test_missing_argument_is_refused():
    assert check("lire_url").reason == "destination-missing"


def test_email_domain_must_match_exactly():
    assert check("envoyer_courriel", a="conseiller@banque.example").allowed
    assert not check("envoyer_courriel", a="x@banque.example.attaquant.example").allowed
    assert not check("envoyer_courriel", a="x@attaquant.example, y@banque.example").allowed


def test_invalid_kind_is_rejected():
    with pytest.raises(ValueError, match="kind"):
        DestinationPolicy.from_dict({"tools": {"t": {"destination": {"argument": "u", "kind": "ftp", "allowed": []}}}})
