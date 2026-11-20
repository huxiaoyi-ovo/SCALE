import subprocess

import pytest

from experiments import runner


def _commit_fixture(path):
    path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.com", "-c", "commit.gpgsign=false",
         "commit", "--allow-empty", "-qm", path.name],
        cwd=path, check=True,
    )
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()


@pytest.fixture
def launch_checkout(tmp_path, monkeypatch):
    path = tmp_path / "launch"
    _commit_fixture(path)
    monkeypatch.chdir(path)
    return path


def test_git_commit_comes_from_source_checkout(tmp_path, monkeypatch, launch_checkout):
    source = tmp_path / "source"
    expected = _commit_fixture(source)
    monkeypatch.setattr(runner, "PROJECT_ROOT", source)

    assert runner._git_commit() == expected


def test_unpacked_source_does_not_report_enclosing_repository_commit(monkeypatch, launch_checkout):
    source = launch_checkout / "unpacked"
    source.mkdir()
    monkeypatch.setattr(runner, "PROJECT_ROOT", source)

    assert runner._git_commit() is None
