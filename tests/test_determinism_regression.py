import sys

import pytest

from navigation.scale_planner_bridge.scripts import determinism_regression


@pytest.mark.parametrize("reference, candidate", [
    (float("nan"), 1.0),
    (1.0, float("nan")),
    (float("inf"), float("inf")),
    (float("-inf"), float("-inf")),
])
def test_compare_rejects_nonfinite_trace_values(reference, candidate):
    with pytest.raises(AssertionError, match=r"trace\.execution_states\[0\]\.x.*non-finite"):
        determinism_regression.compare(
            {"execution_states": [{"x": reference}]},
            {"execution_states": [{"x": candidate}]},
            tolerance=1e-9,
        )


def test_compare_returns_largest_finite_difference_within_tolerance():
    assert determinism_regression.compare(
        {"xy": [1.0, 2.0]}, {"xy": [1.0625, 2.125]}, tolerance=0.125,
    ) == 0.125


@pytest.mark.parametrize("tolerance", ["nan", "inf", "-inf", "-1"])
def test_cli_rejects_invalid_tolerance_before_startup(tolerance, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["determinism_regression.py", "--tolerance=" + tolerance])
    monkeypatch.setattr(determinism_regression, "PYTHON", tmp_path / "missing-python")

    with pytest.raises(ValueError, match="tolerance must be finite and non-negative"):
        determinism_regression.main()
