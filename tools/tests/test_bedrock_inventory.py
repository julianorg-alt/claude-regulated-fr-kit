import json
from pathlib import Path

import pytest

from crfr import bedrock_inventory as inv

FIXTURES = Path(__file__).parent / "fixtures"


def card(name: str) -> inv.ModelEntry:
    text = (FIXTURES / f"model-card-anthropic-{name}.md").read_text(encoding="utf-8")
    return inv.parse_model_card(f"model-card-anthropic-{name}", text)


def test_parses_eu_profile_and_destinations():
    entry = card("claude-sonnet-5")
    assert entry.eu_profile == "eu.anthropic.claude-sonnet-5"
    assert entry.eu_destinations["eu-west-3"] == sorted(
        ["eu-central-1", "eu-north-1", "eu-south-1", "eu-south-2", "eu-west-1", "eu-west-3"]
    )
    assert "eu-west-2" in entry.eu_destinations["eu-west-2"]


def test_endpoints_are_kept_apart():
    entry = card("claude-sonnet-5")
    assert entry.availability["bedrock-runtime"]["eu-west-1"]["in_region"] is False
    assert entry.availability["bedrock-mantle"]["eu-west-1"]["in_region"] is True
    assert entry.availability["bedrock-runtime"]["eu-west-2"]["in_region"] is True


def test_paris_geo_is_allowed_and_stays_in_eu():
    decision = inv.evaluate(card("claude-sonnet-5"), "geo", "eu-west-3")
    assert decision.allowed
    assert set(decision.destinations) <= inv.EU_REGIONS


@pytest.mark.parametrize("source", ["eu-west-2", "eu-central-2"])
def test_london_and_zurich_sources_are_refused_in_strict_eu_mode(source):
    decision = inv.evaluate(card("claude-sonnet-5"), "geo", source)
    assert not decision.allowed


def test_london_source_is_accepted_with_adequacy_mode():
    decision = inv.evaluate(card("claude-sonnet-5"), "geo", "eu-west-2", residency="eu_plus_adequacy")
    assert decision.allowed
    assert "eu-west-2" in decision.destinations


def test_global_is_always_refused():
    assert not inv.evaluate(card("claude-sonnet-5"), "global", "eu-west-3").allowed


def test_us_source_is_refused():
    assert not inv.evaluate(card("claude-sonnet-5"), "geo", "us-east-1").allowed


def test_global_only_model_has_no_allowed_route():
    entry = card("claude-fable-5-2")
    assert entry.eu_profile is None
    assert inv.allowed_routes([entry]) == []


def test_in_region_mantle_in_ireland():
    decision = inv.evaluate(card("claude-sonnet-5"), "in_region_mantle", "eu-west-1")
    assert decision.allowed and decision.destinations == ("eu-west-1",)
    assert not inv.evaluate(card("claude-sonnet-5"), "in_region_runtime", "eu-west-1").allowed


def test_allowed_routes_never_leave_the_eu():
    for route in inv.allowed_routes([card("claude-sonnet-5")]):
        assert route["source_region"] in inv.EU_REGIONS
        assert set(route["destinations"]) <= inv.EU_REGIONS


def test_compare_with_aws_detects_new_destination():
    entry = card("claude-sonnet-5")
    arns = [
        f"arn:aws:bedrock:{r}::foundation-model/anthropic.claude-sonnet-5"
        for r in entry.eu_destinations["eu-west-3"] + ["us-east-1"]
    ]
    problems = inv.compare_with_aws(entry, "eu-west-3", arns)
    assert problems and "us-east-1" in problems[0]


def test_compare_with_aws_matches():
    entry = card("claude-sonnet-5")
    arns = [f"arn:aws:bedrock:{r}::foundation-model/x" for r in entry.eu_destinations["eu-west-3"]]
    assert inv.compare_with_aws(entry, "eu-west-3", arns) == []


def test_unparseable_card_raises():
    with pytest.raises(inv.InventoryError):
        inv.parse_model_card("broken", "# Broken\nno tables here")


def test_build_inventory_with_fake_fetch():
    pages = {
        inv.DOC_BASE + inv.INDEX_PAGE: "[x](model-card-anthropic-claude-sonnet-5.md)",
        inv.DOC_BASE + "model-card-anthropic-claude-sonnet-5.md": (
            FIXTURES / "model-card-anthropic-claude-sonnet-5.md"
        ).read_text(encoding="utf-8"),
    }
    data = inv.build_inventory(fetch=pages.__getitem__)
    assert data["models"][0]["eu_profile"] == "eu.anthropic.claude-sonnet-5"


def test_committed_inventory_is_consistent():
    path = Path(__file__).resolve().parents[2] / "infra" / "inventory" / "bedrock-claude.json"
    entries = inv.load_inventory(path)
    assert entries, "inventory must not be empty"
    for route in inv.allowed_routes(entries):
        assert set(route["destinations"]) <= inv.EU_REGIONS, route
    names = {e.name for e in entries}
    for forbidden in ("Fable", "Mythos"):
        for entry in entries:
            if forbidden in entry.name:
                assert inv.allowed_routes([entry]) == [], entry.name
    json.dumps([e.to_json() for e in entries])
    assert names
