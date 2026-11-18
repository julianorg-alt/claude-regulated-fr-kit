import pytest

from crfr_pseudo.detectors import Detector
from crfr_pseudo.pseudonymiser import Pseudonymiser
from crfr_pseudo.vault import Vault


def nir(body13: str) -> str:
    """Builds a NIR with a valid key from 13 synthetic characters."""
    digits = body13.replace("2A", "19").replace("2B", "18")
    return f"{body13}{97 - int(digits) % 97:02d}"


def luhn_complete(prefix: str) -> str:
    for d in "0123456789":
        candidate = prefix + d
        total = 0
        for i, c in enumerate(reversed(candidate)):
            x = int(c) * (2 if i % 2 else 1)
            total += x - 9 if x > 9 else x
        if total % 10 == 0:
            return candidate
    raise AssertionError


@pytest.fixture(scope="session")
def detector():
    return Detector()


@pytest.fixture
def vault():
    return Vault()


@pytest.fixture
def pseudo(detector, vault):
    return Pseudonymiser(detector, vault)
