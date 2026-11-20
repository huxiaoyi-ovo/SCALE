import shutil
import subprocess
import sys

import yaml

from experiments import runner


def _invoke_from(directory, *arguments):
    script = runner.PROJECT_ROOT / "experiments/runner.py"
    subprocess.run([sys.executable, str(script), *arguments], cwd=directory, check=True, timeout=20)


def test_default_configuration_is_loaded_from_the_checkout(tmp_path):
    unrelated_profiles = tmp_path / "configs/execution_profiles.yaml"
    unrelated_profiles.parent.mkdir()
    unrelated_profiles.write_text("profiles: {}\n")

    _invoke_from(tmp_path)

    assert (tmp_path / "data/run_0001/metadata.json").is_file()
    assert (tmp_path / "data/run_0002/metadata.json").is_file()


def test_custom_config_can_reference_files_beside_it(tmp_path):
    config_directory = tmp_path / "inputs"
    config_directory.mkdir()
    config = runner._load(runner.PROJECT_ROOT / "configs/pilot.yaml")
    shutil.copyfile(runner.PROJECT_ROOT / config["execution_profiles"], config_directory / "profiles.yaml")
    (config_directory / "layout.yaml").write_text(yaml.safe_dump(config["layout"]))
    config.update({"execution_profiles": "profiles.yaml", "layout": "layout.yaml"})
    (config_directory / "experiment.yaml").write_text(yaml.safe_dump(config))

    _invoke_from(tmp_path, "--config", "inputs/experiment.yaml")

    assert (tmp_path / "data/run_0001/metadata.json").is_file()
    assert (tmp_path / "data/run_0002/metadata.json").is_file()
