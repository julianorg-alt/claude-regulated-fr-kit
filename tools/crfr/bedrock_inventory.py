"""Inventory of where AWS Bedrock processes Claude requests made from European regions.

The inventory is the residency evidence of the kit (backlog E1.3). AWS asks customers not to
rely on the geographic prefix of an inference profile ("eu.") and to check every destination
Region of every source Region they use (Bedrock user guide, "Supported Regions and models for
inference profiles", read 2026-11-16). This module:

* parses the public Bedrock model cards (Markdown) into a normalised inventory;
* compares the inventory with ``aws bedrock get-inference-profile`` outputs from a real account;
* evaluates whether a (model, mode, source Region) combination keeps data inside the allowed
  jurisdiction.

Standard library only, so it runs in CI and on locked-down workstations.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

DOC_BASE = "https://docs.aws.amazon.com/bedrock/latest/userguide/"
INDEX_PAGE = "model-cards.md"

# EU member-state Regions. eu-west-2 (London) and eu-central-2 (Zurich) are in AWS's "EU"
# geography but outside the European Union; both countries have an EU adequacy decision.
EU_REGIONS = frozenset({"eu-central-1", "eu-north-1", "eu-south-1", "eu-south-2", "eu-west-1", "eu-west-3"})
ADEQUACY_REGIONS = frozenset({"eu-west-2", "eu-central-2"})
RESIDENCY_MODES = {
    "eu": EU_REGIONS,
    "eu_plus_adequacy": EU_REGIONS | ADEQUACY_REGIONS,
}
ENDPOINTS = ("bedrock-runtime", "bedrock-mantle")

_REGION_CELL = re.compile(r"^\s*([a-z]{2}(?:-gov)?-[a-z]+-\d)\s*\(([^)]*)\)\s*$")
_SUPPORT = re.compile(r"!\[(supported|not-supported)\]")
_ENDPOINT_HEADING = re.compile(r"\*\*Availability using the `([a-z-]+)` endpoint\*\*")
_GEO_HEADING = re.compile(r"^\*\*Geo: ([A-Za-z ]+)\*\*\s*$")
_GEO_ID = re.compile(r"^Geo inference ID: `([^`]+)`", re.I)
_AT_A_GLANCE = re.compile(r"Regional availability at a glance", re.I)
_EOL = re.compile(r"EOL:\s*(\d{4}-\d{2}-\d{2})")
_TITLE = re.compile(r"^# (.+?)\s*$", re.M)
_CARD_LINK = re.compile(r"\((model-card-anthropic-[a-z0-9-]+)\.md\)")


class InventoryError(ValueError):
    """Raised when a model card cannot be parsed into a trustworthy inventory entry."""


@dataclass
class ModelEntry:
    card: str
    name: str
    # endpoint -> region -> {"in_region": bool, "geo": bool, "global": bool}
    availability: dict[str, dict[str, dict[str, bool | str]]] = field(default_factory=dict)
    eu_profile: str | None = None
    # source region -> sorted destination regions, for the "eu." profile
    eu_destinations: dict[str, list[str]] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "card": self.card,
            "name": self.name,
            "availability": self.availability,
            "eu_profile": self.eu_profile,
            "eu_destinations": self.eu_destinations,
        }

    @classmethod
    def from_json(cls, data: dict) -> ModelEntry:
        return cls(
            card=data["card"],
            name=data["name"],
            availability=data.get("availability", {}),
            eu_profile=data.get("eu_profile"),
            eu_destinations=data.get("eu_destinations", {}),
        )


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_model_card(card: str, markdown: str) -> ModelEntry:
    """Parse one Bedrock model card. Raises InventoryError if expected tables are missing."""
    title = _TITLE.search(markdown)
    entry = ModelEntry(card=card, name=title.group(1) if title else card)
    lines = markdown.splitlines()
    endpoint: str | None = None
    geo: str | None = None
    for raw in lines:
        line = raw.strip()
        if _AT_A_GLANCE.search(line):
            # Cards with a single endpoint have one table and no "Availability using" heading.
            endpoint, geo = "bedrock-runtime", None
            continue
        heading = _ENDPOINT_HEADING.search(line)
        if heading:
            endpoint, geo = heading.group(1), None
            continue
        geo_heading = _GEO_HEADING.match(line)
        if geo_heading:
            geo, endpoint = geo_heading.group(1).strip(), None
            continue
        geo_id = _GEO_ID.match(line)
        if geo_id and geo == "EU":
            entry.eu_profile = geo_id.group(1)
            continue
        if line.startswith("## "):
            endpoint, geo = None, None
            continue
        if not line.startswith("|"):
            continue
        cells = _cells(line)
        region = _REGION_CELL.match(cells[0]) if cells else None
        if not region:
            continue
        code = region.group(1)
        if endpoint and len(cells) >= 4:
            row: dict[str, bool | str] = {}
            for key, cell in zip(("in_region", "geo", "global"), cells[1:4], strict=True):
                flag = _SUPPORT.search(cell)
                eol = _EOL.search(cell)
                if flag:
                    row[key] = flag.group(1) == "supported"
                elif eol:
                    # End-of-life rows are not routable: treat as unsupported, keep the date.
                    row[key] = False
                    row[f"{key}_eol"] = eol.group(1)
                else:
                    raise InventoryError(f"{card}: unreadable availability cell {cell!r} for {code}")
            entry.availability.setdefault(endpoint, {})[code] = row
        elif geo == "EU" and len(cells) >= 2:
            destinations = sorted(
                m.group(1) for m in (_REGION_CELL.match(part.strip()) for part in cells[1].split(",")) if m
            )
            if not destinations:
                raise InventoryError(f"{card}: empty EU destination list for source {code}")
            entry.eu_destinations[code] = destinations
    if not entry.availability:
        raise InventoryError(f"{card}: no availability table found")
    if entry.eu_destinations and not entry.eu_profile:
        raise InventoryError(f"{card}: EU destinations listed without an EU profile id")
    return entry


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    destinations: tuple[str, ...] = ()


def evaluate(entry: ModelEntry, mode: str, source_region: str, residency: str = "eu") -> Decision:
    """Decide whether a call keeps data in the allowed jurisdiction.

    mode: "geo" (eu. profile through bedrock-runtime), "in_region_runtime" or
    "in_region_mantle" (single-Region processing), "global" (always refused).
    """
    if residency not in RESIDENCY_MODES:
        raise ValueError(f"unknown residency mode {residency!r}")
    allowed_regions = RESIDENCY_MODES[residency]
    if source_region not in allowed_regions:
        return Decision(False, f"source Region {source_region} is outside {residency}")
    if mode == "global":
        return Decision(False, "global profiles route to all commercial Regions")
    if mode == "geo":
        if not entry.eu_profile:
            return Decision(False, f"{entry.name} has no EU geographic profile")
        row = entry.availability.get("bedrock-runtime", {}).get(source_region)
        if not row or not row.get("geo"):
            return Decision(False, f"{entry.name}: geo profile not available (or end of life) in {source_region}")
        destinations = tuple(entry.eu_destinations.get(source_region, ()))
        if not destinations:
            return Decision(False, f"{entry.name}: {source_region} is not a source of the EU profile")
        outside = sorted(set(destinations) - allowed_regions)
        if outside:
            return Decision(False, f"destinations outside {residency}: {', '.join(outside)}", destinations)
        return Decision(True, "all destinations inside the allowed jurisdiction", destinations)
    if mode in ("in_region_runtime", "in_region_mantle"):
        endpoint = "bedrock-runtime" if mode == "in_region_runtime" else "bedrock-mantle"
        row = entry.availability.get(endpoint, {}).get(source_region)
        if not row or not row["in_region"]:
            return Decision(False, f"{entry.name}: no in-Region {endpoint} in {source_region}")
        return Decision(True, "single-Region processing", (source_region,))
    raise ValueError(f"unknown mode {mode!r}")


def allowed_routes(entries: Iterable[ModelEntry], residency: str = "eu") -> list[dict]:
    """Every (model, mode, source) combination the kit allows, for the IaC and the gateway."""
    routes = []
    for entry in entries:
        sources = sorted(set(entry.eu_destinations) | {r for ep in entry.availability.values() for r in ep})
        for source in sources:
            for mode in ("geo", "in_region_runtime", "in_region_mantle"):
                decision = evaluate(entry, mode, source, residency)
                if decision.allowed:
                    routes.append(
                        {
                            "model": entry.name,
                            "card": entry.card,
                            "mode": mode,
                            "source_region": source,
                            "profile": entry.eu_profile if mode == "geo" else None,
                            "destinations": list(decision.destinations),
                        }
                    )
    return routes


def compare_with_aws(entry: ModelEntry, source_region: str, model_arns: list[str]) -> list[str]:
    """Compare the documented EU destinations with a real get-inference-profile answer.

    model_arns: the ``models[].modelArn`` list returned by
    ``aws bedrock get-inference-profile --region <source> --inference-profile-identifier <eu id>``.
    Returns a list of human-readable discrepancies (empty when they match).
    """
    regions = set()
    for arn in model_arns:
        parts = arn.split(":")
        if len(parts) < 4 or not parts[3]:
            return [f"unreadable model ARN: {arn}"]
        regions.add(parts[3])
    documented = set(entry.eu_destinations.get(source_region, ()))
    problems = []
    if regions - documented:
        problems.append(f"{entry.name} from {source_region}: undocumented destinations {sorted(regions - documented)}")
    if documented - regions:
        problems.append(f"{entry.name} from {source_region}: documented but absent {sorted(documented - regions)}")
    return problems


def _fetch(url: str, timeout: float = 30.0) -> str:
    if not url.startswith(DOC_BASE):
        raise InventoryError(f"refusing to fetch outside the Bedrock documentation: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "claude-regulated-fr-inventory"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (https host checked above)
        return response.read().decode("utf-8")


def build_inventory(fetch=_fetch) -> dict:
    index = fetch(DOC_BASE + INDEX_PAGE)
    cards = sorted(set(_CARD_LINK.findall(index)))
    if not cards:
        raise InventoryError("no Anthropic model card linked from the Bedrock index")
    models = [parse_model_card(card, fetch(DOC_BASE + card + ".md")).to_json() for card in cards]
    return {"source": DOC_BASE + INDEX_PAGE, "models": models}


def load_inventory(path: Path) -> list[ModelEntry]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ModelEntry.from_json(m) for m in data["models"]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    fetch_p = sub.add_parser("fetch", help="rebuild the inventory from the public model cards")
    fetch_p.add_argument("--out", type=Path, required=True)
    routes_p = sub.add_parser("routes", help="list the routes allowed for a residency mode")
    routes_p.add_argument("--inventory", type=Path, required=True)
    routes_p.add_argument("--residency", choices=sorted(RESIDENCY_MODES), default="eu")
    routes_p.add_argument("--out", type=Path)
    check_p = sub.add_parser("check-aws", help="compare with get-inference-profile JSON files")
    check_p.add_argument("--inventory", type=Path, required=True)
    check_p.add_argument("answers", type=Path, nargs="+", help="files named <source-region>__<profile-id>.json")
    args = parser.parse_args(argv)

    if args.command == "fetch":
        inventory = build_inventory()
        args.out.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"{len(inventory['models'])} models written to {args.out}")
        return 0
    entries = load_inventory(args.inventory)
    if args.command == "routes":
        routes = allowed_routes(entries, args.residency)
        text = json.dumps({"residency": args.residency, "routes": routes}, indent=2, sort_keys=True) + "\n"
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        return 0
    by_profile = {e.eu_profile: e for e in entries if e.eu_profile}
    problems: list[str] = []
    for answer in args.answers:
        source, _, profile = answer.stem.partition("__")
        entry = by_profile.get(profile)
        if entry is None:
            problems.append(f"{answer.name}: profile {profile} is not in the inventory")
            continue
        data = json.loads(answer.read_text(encoding="utf-8"))
        arns = [m["modelArn"] for m in data.get("models", [])] if isinstance(data, dict) else list(data)
        problems.extend(compare_with_aws(entry, source, arns))
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
