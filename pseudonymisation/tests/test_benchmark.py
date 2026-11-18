"""Benchmark gate (E3 criterion, E4.3): recall of at least 0.99 on identifiers with a key, on both splits."""

import json
from pathlib import Path

import pytest

from crfr_pseudo.benchmark import score

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    return [json.loads(line) for line in (ROOT / "datasets/pii-fr" / name).read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def results(detector):
    return {name: score(load(name), detector) for name in ("v1.jsonl", "v1-test.jsonl")}


@pytest.mark.parametrize("name", ["v1.jsonl", "v1-test.jsonl"])
def test_identifier_recall_and_hard_negatives(results, name):
    result = results[name]
    assert result["modes"]["strict"]["identifiers_recall"] >= 0.99
    assert result["negatives_detected"] == {}, "an identifier with a wrong key was detected"


def test_published_results_are_current(results):
    for name in ("v1.jsonl", "v1-test.jsonl"):
        published = json.loads((ROOT / f"datasets/pii-fr/results/{Path(name).stem}-spacy.json").read_text())
        assert published["modes"] == json.loads(json.dumps(results[name]["modes"])), (
            "run: make benchmark, then commit datasets/pii-fr/results"
        )
