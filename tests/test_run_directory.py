from concurrent.futures import ThreadPoolExecutor

from experiments.runner import _run_dir


def test_concurrent_runs_reserve_distinct_output_directories(tmp_path):
    output = tmp_path / "runs"
    previous = output / "run_0001"
    previous.mkdir(parents=True)
    artifact = previous / "metadata.json"
    artifact.write_text("previous run")

    with ThreadPoolExecutor(max_workers=4) as pool:
        paths = list(pool.map(_run_dir, [output] * 8))

    assert sorted(path.name for path in paths) == [
        "run_{:04d}".format(number) for number in range(2, 10)
    ]
    assert all(path.is_dir() for path in paths)
    assert artifact.read_text() == "previous run"
