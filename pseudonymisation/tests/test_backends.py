"""Optional backends, tested with stand-ins for the models (the real ones are gated or heavy)."""

from types import SimpleNamespace

import pytest

from crfr_pseudo.backends import EdsPseudoBackend, GlinerBackend
from crfr_pseudo.detectors import Detector


class FakeGliner:
    def predict_entities(self, text, labels, threshold):
        assert "person" in labels and threshold == 0.5
        start = text.index("Zoé")
        return [
            {"start": start, "end": start + 9, "label": "person", "score": 0.93},
            {"start": 0, "end": 3, "label": "weapon", "score": 0.99},
        ]


class FakeEds:
    def __call__(self, text):
        start = text.index("IPP")
        ents = [SimpleNamespace(start_char=start + 4, end_char=start + 12, label_="IPP"),
                SimpleNamespace(start_char=0, end_char=2, label_="UNKNOWN")]  # fmt: skip
        return SimpleNamespace(ents=ents)


def test_gliner_spans_are_mapped_and_merged(detector):
    text = "Le dossier de Zoé Lemar est suivi."
    combined = Detector(analyzer=detector.analyzer, extra=[GlinerBackend(model=FakeGliner())])
    spans = [(s.type, s.text(text)) for s in combined.find(text)]
    assert ("PERSONNE", "Zoé Lemar") in spans
    assert all(t != "weapon" for t, _ in spans)


def test_eds_pseudo_patient_ids(detector):
    text = "Patient IPP 80012345 admis."
    combined = Detector(analyzer=detector.analyzer, extra=[EdsPseudoBackend(nlp=FakeEds())])
    assert ("IDENTIFIANT_PATIENT", "80012345") in [(s.type, s.text(text)) for s in combined.find(text)]


def test_eds_pseudo_requires_local_weights():
    with pytest.raises(ValueError, match="gated"):
        EdsPseudoBackend()
