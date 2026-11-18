"""The synthetic data set (E4.1, E4.2): reproducible, consistent annotations, keys valid or not as declared."""

import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from crfr_pseudo import checksums

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("generate", ROOT / "datasets/generate.py")
generate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate)
SETS = {"v1.jsonl": (2026, 50), "v1-test.jsonl": (7, 25)}
CHECKS = {"NIR": checksums.nir_ok, "IBAN": checksums.iban_ok, "CARTE": checksums.card_ok,
          "SIREN": checksums.siren_ok, "SIRET": checksums.siret_ok}  # fmt: skip


def load(name):
    return [json.loads(line) for line in (ROOT / "datasets/pii-fr" / name).read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("name", SETS)
def test_committed_set_is_reproducible(name):
    seed, per_sector = SETS[name]
    assert generate.generate(seed, per_sector) == load(name), "run: python3 datasets/generate.py (see README)"


@pytest.mark.parametrize("name", SETS)
def test_annotations_are_consistent(name):
    docs = load(name)
    assert Counter(d["sector"] for d in docs) == {s: SETS[name][1] for s in ("banque", "assurance", "sante", "public")}
    for doc in docs:
        text, spans = doc["text"], sorted(doc["spans"], key=lambda s: s["start"])
        for a, b in zip(spans, spans[1:], strict=False):
            assert a["end"] <= b["start"], doc["id"]
        for span in spans:
            value = text[span["start"] : span["end"]]
            assert value.strip() == value and value, (doc["id"], span)
            if span["label"] in CHECKS:
                assert CHECKS[span["label"]](value), (doc["id"], value)
        for negative in doc["negatives"]:
            value = text[negative["start"] : negative["end"]]
            assert not CHECKS[negative["kind"]](value), (doc["id"], value)
            assert not any(s["start"] < negative["end"] and negative["start"] < s["end"] for s in spans)


def test_only_fictional_contact_domains():
    for doc in load("v1.jsonl"):
        for email in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", doc["text"]):
            assert email.endswith("@example.org"), email


# Reserved values (owner decision 2026-11-17): no generated value may belong to a real person or company.
ARCEP_FICTION_ROOTS = ("019900", "026191", "035301", "046571", "053649", "063998")
TEST_CARDS = {"4242424242424242", "4000056655665556", "5555555555554444", "2223003122003222", "5200828282828210",
              "5105105105105100", "4000002500001001", "5555552500001001", "4000002500000003"}  # fmt: skip


def values(docs, label):
    for doc in docs:
        for span in doc["spans"]:
            if span["label"] == label:
                yield re.sub(r"\D", "", doc["text"][span["start"] : span["end"]]), doc["id"]


def test_phone_numbers_are_in_the_arcep_fiction_ranges():
    for name in SETS:
        found = list(values(load(name), "TELEPHONE"))
        assert found
        for digits, doc_id in found:
            national = "0" + digits[-9:]
            assert len(national) == 10 and national.startswith(ARCEP_FICTION_ROOTS), (doc_id, digits)


def test_siren_and_siret_come_from_the_verified_unassigned_list():
    record = json.loads((ROOT / "datasets/reserved-siren.json").read_text())
    verified = set(record["siren"])
    assert len(verified) >= 30 and all(checksums.siren_ok(s) for s in verified)
    for name in SETS:
        docs = load(name)
        for digits, doc_id in values(docs, "SIREN"):
            assert digits in verified, (doc_id, digits)
        for digits, doc_id in values(docs, "SIRET"):
            assert digits[:9] in verified, (doc_id, digits)


def test_generator_refuses_an_unverified_siren(monkeypatch):
    monkeypatch.setattr(generate, "VERIFIED_SIREN", ["552100554"])
    with pytest.raises(AssertionError):
        generate.siren(generate.random.Random(0))


def test_card_numbers_are_documented_network_test_cards():
    for name in SETS:
        for digits, doc_id in values(load(name), "CARTE"):
            assert digits in TEST_CARDS, (doc_id, digits)


def test_iban_uses_the_reserved_bank_code_and_a_valid_rib_key():
    for doc in load("v1.jsonl"):
        for span in doc["spans"]:
            if span["label"] == "IBAN":
                iban = doc["text"][span["start"] : span["end"]].replace(" ", "")
                assert iban.startswith("FR") and checksums.iban_ok(iban) and iban[4:9] == generate.IBAN_BANK_CODE
                rib = iban[4:]
                assert (89 * int(rib[:5]) + 15 * int(rib[5:10]) + 3 * int(rib[10:21]) + int(rib[21:])) % 97 == 0
