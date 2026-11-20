import json
import math

import pytest

from experiments.logger import write_run


@pytest.mark.parametrize("clearance, expected", [(math.inf, None), (0.25, 0.25)])
def test_clearance_can_be_read_by_strict_json_parsers(tmp_path, clearance, expected):
    rows = [{"clearance": clearance}]
    metrics = {"minimum_clearance": clearance}
    write_run(tmp_path, {}, {"valid": True}, rows, metrics)

    def reject_non_json_constant(value):
        raise AssertionError("unexpected JSON constant: {}".format(value))

    document = json.loads(
        (tmp_path / "metrics.json").read_text(), parse_constant=reject_non_json_constant,
    )
    assert document["minimum_clearance"] == expected
    assert metrics["minimum_clearance"] == clearance
    assert (tmp_path / "trajectory.csv").read_text().splitlines() == ["clearance", str(clearance)]


def test_nonfinite_values_in_other_metrics_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="Out of range float values"):
        write_run(tmp_path, {}, {"valid": True}, [{"clearance": 0.0}], {"path_length": math.nan})

    assert not (tmp_path / "metrics.json").exists()
