import matplotlib
import pytest

from experiments import runner


def test_failed_plot_save_releases_the_figure(tmp_path, monkeypatch):
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    previous_figures = plt.get_fignums()
    monkeypatch.setattr(runner, "preview", lambda *args: None)

    def fail_save(*args, **kwargs):
        raise OSError("plot destination is unavailable")

    monkeypatch.setattr(plt.Figure, "savefig", fail_save)

    with pytest.raises(OSError, match="plot destination is unavailable"):
        runner._plot(tmp_path / "plot.png", [{"x": 0, "y": 0}], {})

    assert plt.get_fignums() == previous_figures
