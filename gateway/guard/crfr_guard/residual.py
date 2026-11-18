"""Identifiers that must never reach the model in clear text (input of the OPA rule ``not-pseudonymised``).

Only identifiers with a check digit are detected here, and a number counts only if its key is valid,
so the false-positive rate stays low. Until the pseudonymisation stage (backlog E3) runs in front of
this check, a request that still contains one of them is refused. The pseudonymisation stage
(``crfr_pseudo``) runs first; this check catches what it missed.
"""

from __future__ import annotations

import re

from crfr_pseudo import checksums

_NIR = re.compile(r"(?<![\dA-Za-z])[12]\s?\d{2}\s?\d{2}\s?(?:\d{2}|2[AB])\s?\d{3}\s?\d{3}\s?\d{2}(?![\dA-Za-z])", re.I)
_IBAN_FR = re.compile(r"(?<![A-Z0-9])FR\d{2}(?:\s?[A-Z0-9]){23}(?![A-Z0-9])", re.I)
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
nir_ok, iban_ok, luhn_ok = checksums.nir_ok, checksums.iban_ok, checksums.card_ok


def find(text: str) -> list[str]:
    """Return the sorted list of identifier types found with a valid key."""
    found = set()
    for match in _NIR.finditer(text):
        if nir_ok(match.group(0)):
            found.add("NIR")
    for match in _IBAN_FR.finditer(text):
        if iban_ok(match.group(0)):
            found.add("IBAN_FR")
    for match in _CARD.finditer(text):
        if luhn_ok(match.group(0)):
            found.add("CARD")
    return sorted(found)


def texts(body: dict) -> list[str]:
    """Every piece of text the model would read: system prompt, messages, tool results."""
    out: list[str] = []

    def walk(node):
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for key, value in node.items():
                if key in ("text", "content", "system", "input") or isinstance(value, list | dict):
                    walk(value)

    walk(body.get("system"))
    walk(body.get("messages"))
    return out
