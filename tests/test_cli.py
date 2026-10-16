import pytest

from nyctalus import __version__
from nyctalus.cli import main


def test_runs_without_arguments() -> None:
    assert main([]) == 0


def test_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out
