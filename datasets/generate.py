"""Synthetic French PII data set (backlog E4.1 and E4.2). Standard library only, deterministic.

Every document is fiction built from templates: a bank complaint letter, an insurance claim, a
medical report and a request to a public body, in equal parts (decision K4). Identifiers carry a valid
key (NIR, IBAN, card, SIREN, SIRET), plus "hard negatives" with a wrong key, which must not be detected.
Reserved values (owner decision 2026-11-17, sources in docs/sources/verifications.md): telephone numbers
only in the ARCEP ranges for audiovisual works, SIREN and SIRET only from ``reserved-siren.json`` (checked
against the public company search), card numbers only from published network test cards, IBAN with the
bank code ``00000``. The NIR is still random (open question). Names come from short lists of common French given names and surnames,
organisations and streets are invented. Any match with a real person or company is chance.

Output: one JSON object per line, character offsets, labels equal to the pseudonym types of
``pseudonymisation/crfr_pseudo``:

    {"id": "banque-0001", "sector": "banque", "template": "reclamation", "text": "...",
     "spans": [{"start": 10, "end": 21, "label": "PERSONNE"}], "negatives": [{"start": .., "end": .., "kind": "NIR"}]}

    python3 datasets/generate.py --seed 2026 --per-sector 50 --out datasets/pii-fr/v1.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import string
from pathlib import Path

ARCEP_FICTION_ROOTS = ["019900", "026191", "035301", "046571", "053649", "063998"]  # decision 2025-2215, plan 2026-01-01
TEST_CARDS = ["4242424242424242", "4000056655665556", "5555555555554444", "2223003122003222", "5200828282828210",
              "5105105105105100", "4000002500001001", "5555552500001001", "4000002500000003"]  # fmt: skip
IBAN_BANK_CODE = "00000"
_FILE_SIREN = frozenset(json.loads(Path(__file__).with_name("reserved-siren.json").read_text(encoding="utf-8"))["siren"])
VERIFIED_SIREN = sorted(_FILE_SIREN)

GIVEN = ["Camille", "Louis", "Léa", "Gabriel", "Chloé", "Raphaël", "Manon", "Arthur", "Inès", "Jules", "Zoé",
         "Hugo", "Lucie", "Nathan", "Sarah", "Paul", "Emma", "Tom", "Julie", "Nicolas", "Hélène", "Mathieu",
         "Céline", "Antoine", "Margaux", "Yanis", "Aïcha", "Karim", "Nadia", "Mehdi", "Sophie", "Thierry"]  # fmt: skip
FAMILY = ["Martin", "Bernard", "Thomas", "Petit", "Robert", "Richard", "Durand", "Dubois", "Moreau", "Laurent",
          "Simon", "Michel", "Lefebvre", "Leroy", "Roux", "David", "Bertrand", "Morel", "Fournier", "Girard",
          "Bonnet", "Dupont", "Lambert", "Fontaine", "Rousseau", "Vincent", "Muller", "Lefèvre", "Faure",
          "Mercier", "Boyer", "Garnier", "Chevalier", "Benali", "Nguyen", "Da Silva"]  # fmt: skip
STREETS = ["rue des Lilas", "avenue Victor Hugo", "boulevard des Platanes", "rue du Moulin", "chemin des Vignes",
           "allée des Cerisiers", "place de la Mairie", "impasse des Glycines", "rue Pasteur", "quai des Brumes",
           "route de la Forêt", "rue de la République"]  # fmt: skip
CITIES = [("75011", "Paris"), ("69003", "Lyon"), ("13008", "Marseille"), ("31000", "Toulouse"), ("33000", "Bordeaux"),
          ("59000", "Lille"), ("44000", "Nantes"), ("67000", "Strasbourg"), ("35000", "Rennes"), ("29200", "Brest"),
          ("21000", "Dijon"), ("63000", "Clermont-Ferrand")]  # fmt: skip
ORG_WORDS = ["Azur", "Horizon", "Tilleul", "Boréal", "Cèdre", "Opale", "Vauban", "Ardoise", "Lumière", "Garance"]
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
          "novembre", "décembre"]  # fmt: skip


def luhn_digit(prefix: str) -> str:
    for d in string.digits:
        total = 0
        for i, c in enumerate(reversed(prefix + d)):
            x = int(c) * (2 if i % 2 else 1)
            total += x - 9 if x > 9 else x
        if total % 10 == 0:
            return d
    raise AssertionError


def nir(r: random.Random, sex: str | None = None, year: int | None = None, month: int | None = None) -> str:
    sex = sex or r.choice("12")
    year = year if year is not None else r.randint(40, 99)
    department = r.choice(["75", "69", "13", "33", "59", "2A", "2B", "29", "99"] + [f"{d:02d}" for d in range(1, 96)])
    commune = f"{r.randint(1, 999):03d}"
    body = f"{sex}{year:02d}{month or r.randint(1, 12):02d}{department}{commune}{r.randint(1, 999):03d}"
    numeric = body.replace("2A", "19").replace("2B", "18")
    return body + f"{97 - int(numeric) % 97:02d}"


def iban_fr(r: random.Random) -> str:
    branch = "".join(r.choice(string.digits) for _ in range(5))
    account = "".join(r.choice(string.digits) for _ in range(11))
    key = 97 - (89 * int(IBAN_BANK_CODE) + 15 * int(branch) + 3 * int(account)) % 97
    bban = f"{IBAN_BANK_CODE}{branch}{account}{key:02d}"
    numeric = "".join(str(int(c, 36)) for c in bban + "FR00")
    return f"FR{98 - int(numeric) % 97:02d}{bban}"


def card(r: random.Random) -> str:
    return r.choice(TEST_CARDS)


def siren(r: random.Random) -> str:
    value = r.choice(VERIFIED_SIREN)
    assert value in _FILE_SIREN, f"SIREN {value} is not in reserved-siren.json (verified unassigned)"
    assert luhn_digit(value[:-1]) == value[-1]
    return value


def siret(r: random.Random, base: str) -> str:
    prefix = base + f"{r.randint(1, 99):04d}"
    return prefix + luhn_digit(prefix)


def phone(r: random.Random) -> str:
    return r.choice(ARCEP_FICTION_ROOTS) + "".join(r.choice(string.digits) for _ in range(4))


def broken(value: str) -> str:
    """Same shape, wrong key: change the last digit."""
    # Changing one digit always breaks Luhn and mod 97 (a change of 3 is not a multiple of 97).
    return value[:-1] + str((int(value[-1]) + 3) % 10)


def spaced(value: str, groups: list[int]) -> str:
    out, i = [], 0
    for g in groups:
        out.append(value[i : i + g])
        i += g
    if i < len(value):
        out.append(value[i:])
    return " ".join(out)


FORMATS = {
    "NIR": lambda v, r: r.choice([v, spaced(v, [1, 2, 2, 2, 3, 3, 2])]),
    "IBAN": lambda v, r: r.choice([v, spaced(v, [4, 4, 4, 4, 4, 4, 3])]),
    "CARTE": lambda v, r: r.choice([v, spaced(v, [4, 4, 4, 4])]),
    "SIREN": lambda v, r: r.choice([v, spaced(v, [3, 3, 3])]),
    "SIRET": lambda v, r: r.choice([v, spaced(v, [3, 3, 3, 5])]),
    "TELEPHONE": lambda v, r: r.choice([spaced(v, [2, 2, 2, 2, 2]), v, "+33 " + spaced(v[1:], [1, 2, 2, 2, 2])]),
}


class Doc:
    """Builds a text piece by piece and records the span of every value."""

    def __init__(self):
        self.parts: list[str] = []
        self.spans: list[dict] = []
        self.negatives: list[dict] = []
        self.length = 0

    def add(self, text: str, label: str | None = None, negative: str | None = None) -> Doc:
        if label:
            self.spans.append({"start": self.length, "end": self.length + len(text), "label": label})
        if negative:
            self.negatives.append({"start": self.length, "end": self.length + len(text), "kind": negative})
        self.parts.append(text)
        self.length += len(text)
        return self

    @property
    def text(self) -> str:
        return "".join(self.parts)


class Person:
    def __init__(self, r: random.Random):
        self.given, self.family = r.choice(GIVEN), r.choice(FAMILY)
        self.sex = r.choice("12")
        self.birth = (r.randint(1, 28), r.randint(1, 12), r.randint(1940, 2004))
        self.nir = nir(r, self.sex, self.birth[2] % 100, self.birth[1])
        self.street = f"{r.randint(1, 180)} {r.choice(STREETS)}"
        self.city = r.choice(CITIES)
        self.email = f"{self.given[0].lower()}.{self.family.lower().replace(' ', '')}{r.randint(1, 99)}@example.org"
        self.email = self.email.encode("ascii", "ignore").decode()
        self.phone = phone(r)

    def name(self, r: random.Random) -> str:
        return r.choice([f"{self.given} {self.family}", f"{self.family.upper()} {self.given}", f"{self.given} {self.family}"])

    def birth_text(self, r: random.Random) -> str:
        d, m, y = self.birth
        return r.choice([f"{d:02d}/{m:02d}/{y}", f"{d} {MONTHS[m - 1]} {y}"])

    def address(self) -> str:
        return f"{self.street}, {self.city[0]} {self.city[1]}"


def org(r: random.Random, kind: str) -> str:
    return f"{kind} {r.choice(ORG_WORDS)} {r.choice(['SA', 'SAS', 'Mutuelle', 'Conseil', 'Services'])}"


def value(r: random.Random, doc: Doc, label: str, raw: str) -> None:
    doc.add(FORMATS[label](raw, r) if label in FORMATS else raw, label)


def bank(r: random.Random) -> Doc:
    p, d = Person(r), Doc()
    d.add("Objet : réclamation sur mon compte\n\nMadame, Monsieur,\n\nJe soussigné(e) ").add(p.name(r), "PERSONNE")
    d.add(", né(e) le ").add(p.birth_text(r), "DATE_NAISSANCE").add(", demeurant ").add(p.address(), "ADRESSE")
    d.add(", conteste un prélèvement sur mon compte IBAN ")
    value(r, d, "IBAN", iban_fr(r))
    d.add(". Le paiement a été fait avec la carte ")
    value(r, d, "CARTE", card(r))
    d.add(" au profit de la société ").add(org(r, "Groupe"), "ORGANISATION").add(" (SIREN ")
    value(r, d, "SIREN", siren(r))
    d.add(").\nVous pouvez me joindre au ")
    value(r, d, "TELEPHONE", p.phone)
    d.add(" ou par courriel à ").add(p.email, "EMAIL").add(".\nAncienne référence de dossier : ")
    d.add(FORMATS["IBAN"](broken(iban_fr(r)), r), negative="IBAN")
    d.add(".\n\nCordialement.")
    return d


def insurance(r: random.Random) -> Doc:
    p, d = Person(r), Doc()
    s = siren(r)
    d.add("Déclaration de sinistre\n\nAssuré : ").add(p.name(r), "PERSONNE").add("\nDate de naissance : ")
    d.add(p.birth_text(r), "DATE_NAISSANCE").add("\nAdresse : ").add(p.address(), "ADRESSE")
    d.add("\nTéléphone : ")
    value(r, d, "TELEPHONE", p.phone)
    d.add("\n\nLe dégât des eaux a été constaté par l’entreprise ").add(org(r, "Plomberie"), "ORGANISATION")
    d.add(", SIRET ")
    value(r, d, "SIRET", siret(r, s))
    d.add(". Merci de verser l’indemnité sur le compte ")
    value(r, d, "IBAN", iban_fr(r))
    d.add(".\nNuméro de contrat (ne contient pas de donnée personnelle) : ")
    d.add(FORMATS["SIRET"](broken(siret(r, s)), r), negative="SIRET")
    d.add(".\nContact : ").add(p.email, "EMAIL").add(".")
    return d


def health(r: random.Random) -> Doc:
    p, d = Person(r), Doc()
    doctor = Person(r)
    d.add("Compte rendu de consultation\n\nPatient : ").add(p.name(r), "PERSONNE").add(", né(e) le ")
    d.add(p.birth_text(r), "DATE_NAISSANCE").add("\nNuméro de sécurité sociale : ")
    value(r, d, "NIR", p.nir)
    d.add("\nAdresse : ").add(p.address(), "ADRESSE")
    d.add("\n\nLe patient consulte pour une douleur thoracique. Examen clinique normal. ECG sans anomalie.\n")
    d.add("Courrier adressé au Dr ").add(f"{doctor.given} {doctor.family}", "PERSONNE")
    d.add(", joignable au ")
    value(r, d, "TELEPHONE", doctor.phone)
    d.add(".\nAncien numéro saisi par erreur : ")
    d.add(FORMATS["NIR"](broken(nir(r)), r), negative="NIR")
    d.add(".")
    return d


def public(r: random.Random) -> Doc:
    p, d = Person(r), Doc()
    d.add("Demande d’aide au logement\n\nNom : ").add(p.name(r), "PERSONNE").add("\nNé(e) le ")
    d.add(p.birth_text(r), "DATE_NAISSANCE").add("\nNIR : ")
    value(r, d, "NIR", p.nir)
    d.add("\nDomicile : ").add(p.address(), "ADRESSE").add("\nCourriel : ").add(p.email, "EMAIL")
    d.add("\nTéléphone : ")
    value(r, d, "TELEPHONE", p.phone)
    d.add("\n\nEmployeur : ").add(org(r, "Association"), "ORGANISATION").add(", SIRET ")
    value(r, d, "SIRET", siret(r, siren(r)))
    d.add(".\nRIB pour le versement : ")
    value(r, d, "IBAN", iban_fr(r))
    d.add(".\nNuméro de carte refusé par le guichet : ")
    d.add(FORMATS["CARTE"](broken(card(r)), r), negative="CARTE")
    d.add(".")
    return d


SECTORS = {
    "banque": ("reclamation", bank),
    "assurance": ("sinistre", insurance),
    "sante": ("compte-rendu", health),
    "public": ("demande-usager", public),
}


def generate(seed: int, per_sector: int) -> list[dict]:
    r = random.Random(seed)
    out = []
    for sector, (template, build) in SECTORS.items():
        for i in range(1, per_sector + 1):
            doc = build(r)
            out.append(
                {"id": f"{sector}-{i:04d}", "sector": sector, "template": template, "text": doc.text,
                 "spans": doc.spans, "negatives": doc.negatives}
            )  # fmt: skip
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--per-sector", type=int, default=50)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    docs = generate(args.seed, args.per_sector)
    args.out.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in docs), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
