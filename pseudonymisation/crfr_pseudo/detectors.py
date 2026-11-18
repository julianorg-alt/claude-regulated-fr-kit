"""Detectors of French personal data (backlog E3.1 and E3.2), on top of Presidio.

Identifiers with a check digit (NIR, SIREN, SIRET, IBAN, card) are pattern recognisers
whose ``validate_result`` rejects a number with an invalid key. Telephone numbers, e-mail addresses,
dates of birth, street addresses and the tax number (no public check digit) are patterns with
context. Names and organisations come from a named-entity model: spaCy ``fr_core_news_md`` by
default, GLiNER or EDS-Pseudo as options (``backends.py``).

Overlaps are resolved here, not left to the caller: the longest span wins, then the higher score,
then the entity listed first in ``PRIORITY``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider

from . import checksums

LANGUAGE = "fr"
# Pseudonym type -> Presidio entity. Pseudonyms read <TYPE_n>.
TYPES = {
    "NIR": "FR_NIR",
    "IBAN": "IBAN_CODE",
    "CARTE": "CREDIT_CARD",
    "SIRET": "FR_SIRET",
    "SIREN": "FR_SIREN",
    "NUMERO_FISCAL": "FR_TAX_ID",
    "TELEPHONE": "PHONE_NUMBER",
    "EMAIL": "EMAIL_ADDRESS",
    "DATE_NAISSANCE": "DATE_OF_BIRTH",
    "ADRESSE": "FR_ADDRESS",
    "PERSONNE": "PERSON",
    "ORGANISATION": "ORGANIZATION",
    "IDENTIFIANT_PATIENT": "FR_PATIENT_ID",  # only from the clinical backend (EDS-Pseudo)
}
ENTITY_TO_TYPE = {v: k for k, v in TYPES.items()}
PRIORITY = list(TYPES)  # identifiers with a key first, model-based entities last
IDENTIFIER_TYPES = ("NIR", "IBAN", "CARTE", "SIRET", "SIREN")  # types with a check digit


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    type: str
    score: float

    def text(self, source: str) -> str:
        return source[self.start : self.end]


class _Checked(PatternRecognizer):
    """Pattern recogniser whose matches must pass a check-digit function."""

    def __init__(self, entity: str, patterns: list[Pattern], check, context: list[str]):
        super().__init__(
            supported_entity=entity, supported_language=LANGUAGE, patterns=patterns, context=context, name=entity
        )
        self._check = check

    def validate_result(self, pattern_text: str) -> bool:
        return bool(self._check(pattern_text))


MONTHS = "janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre"
STREET = (
    "rue|avenue|av\\.|boulevard|bd|allée|allee|chemin|impasse|place|quai|route|cours|square|passage|"
    "lieu-dit|résidence|residence|hameau|faubourg|voie"
)


def recognizers() -> list[PatternRecognizer]:
    sep = r"[\s.\-]?"
    return [
        _Checked(
            "FR_NIR",
            [
                Pattern(
                    "nir",
                    rf"\b[1278]{sep}\d{{2}}{sep}\d{{2}}{sep}(?:\d{{2}}|2[AB]){sep}\d{{3}}{sep}\d{{3}}{sep}\d{{2}}\b",
                    0.5,
                )
            ],
            checksums.nir_ok,
            ["sécurité sociale", "securite sociale", "nir", "numéro de sécu", "insee", "assuré", "carte vitale"],
        ),
        _Checked(
            "IBAN_CODE",
            [Pattern("iban", r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,4})?\b", 0.5)],
            checksums.iban_ok,
            ["iban", "rib", "virement", "compte"],
        ),
        _Checked(
            "CREDIT_CARD",
            [Pattern("card", r"(?<!\d[ \t]?)\b(?:\d[ \-]?){14,18}\d\b(?![ \t]?\d)", 0.3)],
            checksums.card_ok,
            ["carte", "cb", "visa", "mastercard", "paiement"],
        ),
        _Checked(
            "FR_SIRET",
            [Pattern("siret", r"(?<!\d[ \t]?)\b\d{3}[ \t]?\d{3}[ \t]?\d{3}[ \t]?\d{5}\b(?![ \t]?\d)", 0.4)],
            checksums.siret_ok,
            ["siret", "établissement", "etablissement"],
        ),
        _Checked(
            "FR_SIREN",
            [Pattern("siren", r"(?<!\d[ \t]?)\b\d{3}[ \t]?\d{3}[ \t]?\d{3}\b(?![ \t]?\d)", 0.3)],
            checksums.siren_ok,
            ["siren", "rcs", "entreprise", "société", "societe"],
        ),
        PatternRecognizer(
            # No public check digit: only with a context word right before it (lookbehind).
            supported_entity="FR_TAX_ID",
            name="FR_TAX_ID",
            supported_language=LANGUAGE,
            patterns=[
                Pattern(
                    "spi",
                    r"(?<=\b(?:num[ée]ro\s+fiscal|n°\s*fiscal|SPI|identifiant\s+fiscal)\b[^\d\n]{0,20})\d(?:\s?\d){12}\b",
                    0.8,
                )
            ],
        ),
        PatternRecognizer(
            supported_entity="PHONE_NUMBER",
            name="FR_PHONE",
            supported_language=LANGUAGE,
            patterns=[
                Pattern(
                    "phone",
                    r"(?<![\d+])(?:(?:\+|00)33[\s.\-]?(?:\(0\)[\s.\-]?)?[1-9]|0[1-9])(?:[\s.\-]?\d{2}){4}(?!\d)",
                    0.6,
                )
            ],
            context=["téléphone", "telephone", "tél", "tel", "portable", "mobile", "joindre", "appeler"],
        ),
        PatternRecognizer(
            supported_entity="EMAIL_ADDRESS",
            name="EMAIL",
            supported_language=LANGUAGE,
            patterns=[Pattern("email", r"\b[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)*\.[a-z]{2,}\b", 0.9)],
        ),
        PatternRecognizer(
            supported_entity="DATE_OF_BIRTH",
            name="FR_DATE_OF_BIRTH",
            supported_language=LANGUAGE,
            patterns=[
                Pattern(
                    "dob",
                    r"(?<=\b(?:né|née|nee|ne|naissance|DDN|né\(e\)|née?\s+le)\b[^\d\n]{0,30})"
                    rf"(?:\d{{1,2}}[/.\-]\d{{1,2}}[/.\-]\d{{2,4}}|\d{{1,2}}(?:er)?\s+(?:{MONTHS})\s+\d{{4}})",
                    0.85,
                )
            ],
        ),
        PatternRecognizer(
            supported_entity="FR_ADDRESS",
            name="FR_ADDRESS",
            supported_language=LANGUAGE,
            patterns=[
                Pattern(
                    "street",
                    rf"\b\d{{1,4}}(?:\s?(?:bis|ter|quater|[A-D]))?,?\s+(?:{STREET})\s+[^\n,;:()]{{2,60}}?"
                    r"(?:,?[ \t]+\d{5}[ \t]+[A-ZÉÈÀÂÎÔÛ][\w'\-]+(?:[ \-][A-ZÉÈÀÂÎÔÛ][\w'\-]+)*|(?=[,.;\n)]|$))",
                    0.7,
                )
            ],
        ),
    ]


UPPER = "A-ZÉÈÊËÀÂÄÎÏÔÖÛÜÇ"
LOWER = "a-zéèêëàâäîïôöûüç"
ACRONYMS = {"IBAN", "SIRET", "SIREN", "NIR", "RIB", "ECG", "SA", "SAS", "SARL", "CB", "TVA", "CAF", "CPAM",
            "URSSAF", "SPI", "IPP", "NDA", "DDN", "IRM", "PDF", "RCS", "EDF", "SNCF", "RATP", "BNP", "INSEE",
            "FR", "UE"}  # fmt: skip


class UpperSurnameRecognizer(PatternRecognizer):
    """French administrative order: surname in capitals, then given name ("DUPONT Marie")."""

    def __init__(self):
        super().__init__(
            supported_entity="PERSON",
            name="FR_UPPER_SURNAME",
            supported_language=LANGUAGE,
            patterns=[
                Pattern(
                    "upper-surname",
                    rf"\b[{UPPER}][{UPPER}'\-]+(?:[ \t][{UPPER}][{UPPER}'\-]+)?"
                    rf"[ \t][{UPPER}][{LOWER}]+(?:-[{UPPER}][{LOWER}]+)?\b",
                    0.6,
                )
            ],
            global_regex_flags=0,  # case matters here
        )

    def validate_result(self, pattern_text: str) -> bool:
        return not any(word in ACRONYMS for word in pattern_text.split())


def build_analyzer(model: str = "fr_core_news_md") -> AnalyzerEngine:
    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": LANGUAGE, "model_name": model}],
            "ner_model_configuration": {
                "model_to_presidio_entity_mapping": {"PER": "PERSON", "ORG": "ORGANIZATION"},
                "labels_to_ignore": ["LOC", "MISC"],
            },
        }
    )
    registry = RecognizerRegistry(supported_languages=[LANGUAGE])
    registry.load_predefined_recognizers(languages=[LANGUAGE], nlp_engine=provider.create_engine())
    # Keep only the NER recogniser of the predefined set; every pattern recogniser is the kit's own.
    for recognizer in list(registry.recognizers):
        if recognizer.name != "SpacyRecognizer":
            registry.remove_recognizer(recognizer.name)
    for recognizer in [*recognizers(), UpperSurnameRecognizer()]:
        registry.add_recognizer(recognizer)
    nlp_engine = provider.create_engine()
    return AnalyzerEngine(registry=registry, nlp_engine=nlp_engine, supported_languages=[LANGUAGE])


MODEL_TYPES = ("PERSONNE", "ORGANISATION")
_IBAN_SHAPE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ \t]?[A-Z0-9]{4}){2,7}(?:[ \t]?[A-Z0-9]{1,4})?\b")


def resolve(spans: Iterable[Span]) -> list[Span]:
    """Drop overlapping spans. Pattern detections beat model detections (a named-entity model often
    swallows a neighbouring identifier); then the longest span wins, then the score, then the type
    priority."""
    ordered = sorted(
        spans,
        key=lambda s: (s.type in MODEL_TYPES, -(s.end - s.start), -s.score, PRIORITY.index(s.type), s.start),
    )
    kept: list[Span] = []
    for span in ordered:
        if all(span.end <= k.start or span.start >= k.end for k in kept):
            kept.append(span)
    return sorted(kept, key=lambda s: s.start)


# Words a French NER model tends to tag as a person or organisation in forms and letters.
NOT_A_NAME = {
    "madame", "monsieur", "mademoiselle", "messieurs", "assuré", "assurée", "adresse", "patient", "patiente",
    "nom", "prénom", "objet", "domicile", "courriel", "téléphone", "employeur", "contact", "cordialement",
    "docteur", "dr", "maître", "date", "né", "née", "né(e)",
}  # fmt: skip
_TITLE = re.compile(r"^(?:(?:Dr|Docteur|Pr|Professeur|M\.|Mme|Mlle|Me|Monsieur|Madame|Maître)\.?\s+)+")


def _trim(span: Span, text: str) -> Span | None:
    """Model spans never cross a line break and never include a title (Dr, Mme); label words are dropped."""
    if span.type not in MODEL_TYPES:
        return span
    value = text[span.start : span.end]
    first = value.split("\n", 1)[0].rstrip(" ,;:")
    start = span.start
    if span.type == "PERSONNE":
        title = _TITLE.match(first)
        if title and title.end() < len(first):
            start, first = start + title.end(), first[title.end() :]
    if first.casefold() in NOT_A_NAME or not first.strip():
        return None
    return Span(start, start + len(first), span.type, span.score)


def _nir_shaped(digits: str) -> bool:
    """15 digits shaped like a NIR whose key failed: a mistyped NIR, not a card number."""
    return len(digits) == 15 and digits[0] in "12" and (1 <= int(digits[3:5]) <= 12 or int(digits[3:5]) >= 20)


class Detector:
    """Presidio analyser plus overlap resolution; ``extra`` backends (GLiNER) add model spans."""

    def __init__(self, analyzer: AnalyzerEngine | None = None, threshold: float = 0.35, extra=(), types=None):
        self.analyzer = analyzer or build_analyzer()
        self.threshold = threshold
        self.extra = list(extra)
        self.types = set(types or TYPES)

    def find(self, text: str) -> list[Span]:
        if not text.strip():
            return []
        results = self.analyzer.analyze(text=text, language=LANGUAGE, score_threshold=self.threshold)
        spans = [
            Span(r.start, r.end, ENTITY_TO_TYPE[r.entity_type], r.score)
            for r in results
            if r.entity_type in ENTITY_TO_TYPE
        ]
        for backend in self.extra:
            spans += backend.find(text)
        spans = [t for s in spans if s.type in self.types and (t := _trim(s, text))]
        spans = [s for s in spans if not (s.type == "CARTE" and _nir_shaped(re.sub(r"\D", "", s.text(text))))]
        # A number inside an IBAN-shaped token (even one with a wrong key) is part of it, not a card.
        ibans = [m.span() for m in _IBAN_SHAPE.finditer(text)]
        spans = [s for s in spans if s.type == "IBAN" or not any(a <= s.start and s.end <= b for a, b in ibans)]
        return resolve(spans)
