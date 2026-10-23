from audit_agent.runner import _wilson
from audit_agent.selfcheck import run_selfcheck


def test_oracle_known_answer_and_mutants() -> None:
    result = run_selfcheck()
    assert result["golden_passed"], result["golden_failed_assertions"]
    assert result["mutants_detected"] == result["mutants_total"], result["mutants"]
    assert result["passed"]


def test_wilson_interval_is_bounded_and_asymmetric_at_extremes() -> None:
    low, high = _wilson(5, 5)
    assert 0.0 <= low < 1.0
    assert high == 1.0
    assert low > 0.4
    low, high = _wilson(0, 5)
    assert low == 0.0
    assert 0.0 < high < 0.6
