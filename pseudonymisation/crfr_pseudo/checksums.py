"""Check digits of French identifiers. Pure functions, no dependency.

A number counts as an identifier only when its key is valid; this keeps false positives low and is
what the detectors and the gateway's residual check rely on. Rules and sources:
docs/sources/verifications.md (sprint 2, pseudonymisation).
"""

from __future__ import annotations

import re

_SPACES = re.compile(r"[\s.\-]")


def compact(value: str) -> str:
    return _SPACES.sub("", value)


def luhn_ok(number: str) -> bool:
    digits = compact(number)
    if not digits.isdigit() or len(digits) < 2:
        return False
    total = 0
    for i, char in enumerate(reversed(digits)):
        d = int(char)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def nir_ok(value: str) -> bool:
    """NIR: sex (1 or 2) and 12 more characters, then a 2-digit key, key = 97 - (number mod 97) (INSEE).

    Corsica: INSEE replaces the letter by 0 and subtracts 1,000,000 (A) or 2,000,000 (B) from the
    13-digit number, which amounts to reading 2A as 19 and 2B as 18.
    """
    nir = compact(value).upper()
    if len(nir) != 15 or nir[0] not in "12":
        return False
    body, key = nir[:13], nir[13:]
    department = body[5:7]
    if department == "2A":
        body = body[:5] + "19" + body[7:]
    elif department == "2B":
        body = body[:5] + "18" + body[7:]
    if not body.isdigit() or not key.isdigit():
        return False
    return 97 - int(body) % 97 == int(key)


LA_POSTE_SIREN = "356000000"
LA_POSTE_HEAD_OFFICE = "35600000000048"


def siren_ok(value: str) -> bool:
    siren = compact(value)
    return len(siren) == 9 and siren.isdigit() and luhn_ok(siren)


def siret_ok(value: str) -> bool:
    """SIRET: Luhn on 14 digits (INSEE).

    La Poste establishments (SIREN 356000000, head office excepted) use a digit sum divisible by 5. INSEE
    does not publish this exception; it comes from python-stdnum and editors' notes (verifications.md V27).
    """
    siret = compact(value)
    if len(siret) != 14 or not siret.isdigit():
        return False
    if siret.startswith(LA_POSTE_SIREN) and siret != LA_POSTE_HEAD_OFFICE:
        return sum(int(c) for c in siret) % 5 == 0
    return luhn_ok(siret)


def iban_ok(value: str) -> bool:
    iban = compact(value).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", iban):
        return False
    if iban.startswith("FR") and len(iban) != 27:
        return False
    rearranged = iban[4:] + iban[:4]
    return int("".join(str(int(c, 36)) for c in rearranged)) % 97 == 1


def card_ok(value: str) -> bool:
    digits = compact(value)
    return 13 <= len(digits) <= 19 and digits.isdigit() and luhn_ok(digits)


def tax_number_shape_ok(value: str) -> bool:
    """Numéro fiscal: 13 digits (impots.gouv.fr). No public check digit was found, so the detector
    requires a context word as well (verifications.md V28)."""
    spi = compact(value)
    return len(spi) == 13 and spi.isdigit()
