import shutil

import yaml

from experiments import runner


def test_replay_uses_captured_profile_even_after_source_deletion(tmp_path):
    config = runner._load(runner.PROJECT_ROOT / "configs/pilot.yaml")
    source = runner.PROJECT_ROOT / config["execution_profiles"]
    profile_path = tmp_path / "profiles.yaml"
    shutil.copyfile(source, profile_path)
    config["execution_profiles"] = str(profile_path)
    config["output_directory"] = str(tmp_path / "runs")

    original = runner.run(config)
    profile_path.unlink()

    for initial_run in original:
        saved_config = yaml.safe_load((initial_run / "config.yaml").read_text())
        assert saved_config["execution_profiles_source"] == str(profile_path)
        for initial, rerun in zip(original, runner.run(saved_config)):
            for artifact in ("trajectory.csv", "metrics.json"):
                assert (initial / artifact).read_bytes() == (rerun / artifact).read_bytes()
