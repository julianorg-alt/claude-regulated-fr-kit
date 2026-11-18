import pytest
from conftest import luhn_complete, nir

from crfr_pseudo import checksums as c


def test_nir():
    assert c.nir_ok(nir("1850578006084"))
    assert c.nir_ok(" ".join([nir("1850578006084")[:1], nir("1850578006084")[1:3]]) + nir("1850578006084")[3:])
    good = nir("1850578006084")
    assert not c.nir_ok(good[:-2] + f"{(int(good[-2:]) + 1) % 100:02d}")
    assert c.nir_ok(nir("29001" + "2A" + "123456"))
    assert c.nir_ok(nir("29001" + "2B" + "123456"))
    assert not c.nir_ok(nir("3850578006084")), "first digit is the sex: 1 or 2"
    assert not c.nir_ok("12345")


def test_luhn_family():
    siren = luhn_complete("13438944")
    assert c.siren_ok(siren) and not c.siren_ok(siren[:-1] + str((int(siren[-1]) + 1) % 10))
    siret = luhn_complete(siren + "0001")
    assert c.siret_ok(siret) and not c.siret_ok(siret[:-1] + str((int(siret[-1]) + 1) % 10))
    card = luhn_complete("424242424242424")
    assert c.card_ok(card) and c.card_ok(" ".join(card[i : i + 4] for i in range(0, 16, 4)))
    assert not c.card_ok("1234")


def test_la_poste_siret_rule():
    # SIREN 356000000: establishments are valid when the digit sum is a multiple of 5.
    base = "35600000000"
    valid = next(base + f"{n:03d}" for n in range(1000) if sum(map(int, base + f"{n:03d}")) % 5 == 0)
    assert c.siret_ok(valid)
    invalid = next(base + f"{n:03d}" for n in range(1000) if sum(map(int, base + f"{n:03d}")) % 5)
    assert not c.siret_ok(invalid)


@pytest.mark.parametrize(
    "iban,ok",
    [
        ("FR76 0000 0012 3412 3456 7890 151", True),
        ("FR7600000012341234567890151", True),
        ("FR76 0000 0012 3412 3456 7890 150", False),
        ("FR76 0000 0012 3412 3456 7890 15", False),  # French IBANs have 27 characters
        ("DE89 3704 0044 0532 0130 00", True),
        ("XX00", False),
    ],
)
def test_iban(iban, ok):
    assert c.iban_ok(iban) is ok


def test_tax_number_shape():
    assert c.tax_number_shape_ok("0123 456 789 012") and not c.tax_number_shape_ok("012345678901")


def test_la_poste_head_office_uses_luhn():
    assert c.siret_ok(c.LA_POSTE_HEAD_OFFICE) == c.luhn_ok(c.LA_POSTE_HEAD_OFFICE)
