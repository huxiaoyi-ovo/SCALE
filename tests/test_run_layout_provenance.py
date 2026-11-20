import yaml

from experiments import runner


def test_replay_does_not_need_original_layout_file(tmp_path):
    config = runner._load(runner.PROJECT_ROOT / "configs/pilot.yaml")
    config["execution_profiles"] = str(runner.PROJECT_ROOT / config["execution_profiles"])
    config["output_directory"] = str(tmp_path / "runs")
    layout = config["layout"]
    layout_file = tmp_path / "layout.yaml"
    layout_file.write_text(yaml.safe_dump({"layout": layout}))
    config["layout"] = layout_file

    original_runs = runner.run(config)
    layout_file.unlink()
    saved_config = yaml.safe_load((original_runs[0] / "config.yaml").read_text())

    assert saved_config["layout"] == layout
    assert config["layout"] is layout_file
    replayed_runs = runner.run(saved_config)
    for original, replayed in zip(original_runs, replayed_runs):
        assert (original / "trajectory.csv").read_bytes() == (replayed / "trajectory.csv").read_bytes()
