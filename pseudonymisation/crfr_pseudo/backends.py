"""Optional named-entity backends, added to the default detector with ``Detector(extra=[...])``.

* ``GlinerBackend`` (E3.2): GLiNER zero-shot NER, by default ``urchade/gliner_multi_pii-v1``
  (Apache-2.0, French covered, about 1.2 GB). Needs ``pip install crfr-pseudo[gliner]`` (PyTorch).
  Always pin the model revision: a model is code that changes what is detected.
* ``EdsPseudoBackend`` (E3.3): EDS-Pseudo, the clinical pseudonymisation model of AP-HP, for
  medical texts. The code is BSD-3-Clause; the public weights (``AP-HP/eds-pseudo-public``, trained
  on synthetic data) are gated on Hugging Face, so the kit cannot ship or download them: the
  operator requests access, downloads them and passes the local path.

Both are loaded lazily, so the default image needs neither PyTorch nor edsnlp.
"""

from __future__ import annotations

from .detectors import Span

GLINER_MODEL = "urchade/gliner_multi_pii-v1"
GLINER_REVISION = "1fcf13e85f4eef5394e1fcd406cf2ca9ea82351d"
# GLiNER label (natural language, prompted to the model) -> pseudonym type
GLINER_LABELS = {
    "person": "PERSONNE",
    "organization": "ORGANISATION",
    "address": "ADRESSE",
    "date of birth": "DATE_NAISSANCE",
    "email": "EMAIL",
    "phone number": "TELEPHONE",
}
# EDS-Pseudo labels (README of aphp/eds-pseudo) -> pseudonym type
EDS_LABELS = {
    "NOM": "PERSONNE",
    "PRENOM": "PERSONNE",
    "ADRESSE": "ADRESSE",
    "VILLE": "ADRESSE",
    "ZIP": "ADRESSE",
    "DATE_NAISSANCE": "DATE_NAISSANCE",
    "SECU": "NIR",
    "TEL": "TELEPHONE",
    "MAIL": "EMAIL",
    "HOPITAL": "ORGANISATION",
    "IPP": "IDENTIFIANT_PATIENT",
    "NDA": "IDENTIFIANT_PATIENT",
}


class GlinerBackend:
    def __init__(self, model=None, model_id: str = GLINER_MODEL, revision: str = GLINER_REVISION, threshold=0.5):
        if model is None:
            from gliner import GLiNER  # optional dependency

            model = GLiNER.from_pretrained(model_id, revision=revision)
        self.model, self.threshold = model, threshold

    def find(self, text: str) -> list[Span]:
        found = self.model.predict_entities(text, list(GLINER_LABELS), threshold=self.threshold)
        return [
            Span(e["start"], e["end"], GLINER_LABELS[e["label"]], float(e.get("score", self.threshold)))
            for e in found
            if e.get("label") in GLINER_LABELS
        ]


class EdsPseudoBackend:
    def __init__(self, nlp=None, model_path: str | None = None, score: float = 0.9):
        if nlp is None:
            if not model_path:
                raise ValueError("EDS-Pseudo weights are gated: download them and pass model_path")
            import edsnlp  # optional dependency

            nlp = edsnlp.load(model_path)
        self.nlp, self.score = nlp, score

    def find(self, text: str) -> list[Span]:
        doc = self.nlp(text)
        return [
            Span(ent.start_char, ent.end_char, EDS_LABELS[ent.label_], self.score)
            for ent in doc.ents
            if ent.label_ in EDS_LABELS
        ]
