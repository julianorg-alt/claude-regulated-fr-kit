import pytest
from conftest import luhn_complete, nir

from crfr_pseudo.detectors import Span, resolve

NIR = nir("2850375120005")
SIRET = luhn_complete(luhn_complete("13438944") + "0001")
CARD = luhn_complete("424242424242424")


def found(detector, text):
    return [(s.type, s.text(text)) for s in detector.find(text)]


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "Mon numéro de sécurité sociale est "
            f"{NIR[0]} {NIR[1:3]} {NIR[3:5]} {NIR[5:7]} {NIR[7:10]} {NIR[10:13]} {NIR[13:]}.",
            "NIR",
        ),
        ("Virement depuis FR76 0000 0012 3412 3456 7890 151 hier.", "IBAN"),
        (f"Payé avec la carte {CARD}.", "CARTE"),
        (f"Établissement SIRET {SIRET} à Lyon.", "SIRET"),
        (f"Entreprise SIREN {SIRET[:9]}.", "SIREN"),
        ("Appelez-moi au 06 39 98 12 34 ou au +33 1 99 00 12 34.", "TELEPHONE"),
        ("Écrire à jean.martin@example.org merci.", "EMAIL"),
        ("Votre numéro fiscal : 0123 456 789 012.", "NUMERO_FISCAL"),
        ("Patient né le 3 mars 1960 à Brest.", "DATE_NAISSANCE"),
        ("Domicile : 4 bis avenue des Tilleuls, 69003 Lyon.", "ADRESSE"),
        ("Le dossier de Monsieur Jean Martin est complet.", "PERSONNE"),
    ],
)
def test_detects_each_type(detector, text, expected):
    assert expected in {t for t, _ in found(detector, text)}, found(detector, text)


def test_invalid_keys_are_not_identifiers(detector):
    bad_nir = NIR[:-2] + f"{(int(NIR[-2:]) + 1) % 100:02d}"
    text = f"NIR {bad_nir}, IBAN FR76 0000 0012 3412 3456 7890 150, carte {CARD[:-1]}{(int(CARD[-1]) + 1) % 10}"
    assert not {"NIR", "IBAN", "CARTE"} & {t for t, _ in found(detector, text)}


def test_thirteen_digits_without_context_are_not_a_tax_number(detector):
    assert "NUMERO_FISCAL" not in {t for t, _ in found(detector, "Référence 0123456789012.")}


def test_dates_without_birth_context_are_kept(detector):
    assert "DATE_NAISSANCE" not in {t for t, _ in found(detector, "Rendez-vous le 12/03/2026 à 14h.")}


def test_spans_are_exact(detector):
    text = "IBAN : FR76 0000 0012 3412 3456 7890 151."
    assert ("IBAN", "FR76 0000 0012 3412 3456 7890 151") in found(detector, text)


def test_resolve_prefers_longest_then_score_then_priority():
    spans = [
        Span(0, 14, "SIRET", 1.0),
        Span(0, 9, "SIREN", 1.0),
        Span(20, 25, "PERSONNE", 0.5),
        Span(20, 25, "ORGANISATION", 0.9),
    ]
    assert [s.type for s in resolve(spans)] == ["SIRET", "ORGANISATION"]


def test_upper_surname_titles_and_labels(detector):
    text = "Patient : DUPONT Marie-Anne\nCourrier adressé au Dr Paul Girard.\nMadame, Monsieur,"
    got = found(detector, text)
    assert ("PERSONNE", "DUPONT Marie-Anne") in got
    assert ("PERSONNE", "Paul Girard") in got, "titles are not part of the name"
    assert all(v not in ("Madame", "Monsieur", "Patient") for _, v in got)
    assert ("PERSONNE", "IBAN Paris") not in found(detector, "Mon IBAN Paris")


def test_numbers_inside_an_iban_or_a_longer_number_are_not_cards_or_sirens(detector):
    text = "Référence FR85 3548 6439 0618 8479 1889 et contrat 385 723 978 0052."
    assert not {"CARTE", "SIREN"} & {t for t, _ in found(detector, text)}


def test_mistyped_nir_is_not_a_card(detector):
    from crfr_pseudo.detectors import _nir_shaped

    assert _nir_shaped("155032575164534") and not _nir_shaped("424242424242424")
