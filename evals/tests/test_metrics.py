import pytest
from crfr_eval.metrics import cohen_kappa, dataset_pass_hat_k, pass_hat_k
from crfr_eval.results import FAIL, PASS, Outcome


def test_pass_hat_k_is_c_choose_k_over_n_choose_k():
    assert pass_hat_k(4, 4, 3) == 1.0
    assert pass_hat_k(4, 3, 3) == pytest.approx(1 / 4)
    assert pass_hat_k(4, 2, 3) == 0.0
    assert pass_hat_k(5, 3, 1) == pytest.approx(3 / 5)  # pass^1 is the success rate
    with pytest.raises(ValueError):
        pass_hat_k(2, 2, 3)


def run(task, outcomes, critical=False):
    return [Outcome(task, "banque", critical, o, ()) for o in outcomes]


def test_dataset_pass_hat_k_averages_tasks():
    outcomes = run("a", [PASS] * 3) + run("b", [PASS, PASS, FAIL], critical=True)
    assert dataset_pass_hat_k(outcomes, 3) == pytest.approx(0.5)
    assert dataset_pass_hat_k(outcomes, 3, critical_only=True) == 0.0
    assert dataset_pass_hat_k(outcomes, 1) == pytest.approx((1 + 2 / 3) / 2)


def test_kappa_known_values():
    # Two raters, 50 items: 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no: po 0.7, pe 0.5, kappa 0.4.
    a = ["oui"] * 25 + ["non"] * 25
    b = ["oui"] * 20 + ["non"] * 5 + ["oui"] * 10 + ["non"] * 15
    assert cohen_kappa(a, b) == pytest.approx(0.4)
    assert cohen_kappa(a, a) == 1.0
    assert cohen_kappa(["oui", "non"], ["non", "oui"]) == pytest.approx(-1.0)
    with pytest.raises(ValueError):
        cohen_kappa(["oui"], [])
