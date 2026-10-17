import os
import plistlib
from pathlib import Path

import pytest

from nyctalus import shortcut
from nyctalus.shortcut import DesktopEntry, MacApp, ShortcutError, StartMenu

PYTHON = Path("/home/ann/bats $tools/.venv/bin/python")


def test_each_system_gets_its_own_kind(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for platform, kind, name in [
        ("darwin", MacApp, "Nyctalus.app"),
        ("win32", StartMenu, "Nyctalus.lnk"),
        ("linux", DesktopEntry, "nyctalus.desktop"),
    ]:
        monkeypatch.setattr("sys.platform", platform)
        made = shortcut.for_this_system(tmp_path, PYTHON)
        assert type(made) is kind
        assert made.path.name == name
        assert made.path.is_relative_to(tmp_path)


def test_a_mac_app_starts_this_python(tmp_path: Path) -> None:
    app = MacApp(tmp_path / "Applications" / "Nyctalus.app", PYTHON)

    app.create()

    contents = app.path / "Contents"
    with (contents / "Info.plist").open("rb") as f:
        info = plistlib.load(f)
    launcher = contents / "MacOS" / info["CFBundleExecutable"]
    assert info["CFBundleIdentifier"] == shortcut.BUNDLE_ID
    assert launcher.read_text().splitlines()[1].startswith(f"'{PYTHON}' -m nyctalus ")
    assert os.access(launcher, os.X_OK)
    assert (contents / "Resources" / "nyctalus.icns").stat().st_size > 0

    app.create()  # made again over itself
    assert app.remove()
    assert not app.path.exists()
    assert not app.remove()


def test_an_app_nyctalus_did_not_make_is_left_alone(tmp_path: Path) -> None:
    other = tmp_path / "Nyctalus.app" / "Contents"
    other.mkdir(parents=True)
    with (other / "Info.plist").open("wb") as f:
        plistlib.dump({"CFBundleIdentifier": "com.example.other"}, f)

    with pytest.raises(ShortcutError):
        MacApp(tmp_path / "Nyctalus.app", PYTHON).remove()
    assert other.exists()


def test_a_desktop_entry_quotes_the_path(tmp_path: Path) -> None:
    entry = DesktopEntry(tmp_path / "nyctalus.desktop", PYTHON)

    entry.create()

    lines = entry.path.read_text().splitlines()
    assert lines[0] == "[Desktop Entry]"
    assert 'Exec="/home/ann/bats \\\\$tools/.venv/bin/python" -m nyctalus' in lines
    assert any(line.startswith("Icon=/") and line.endswith("nyctalus.png") for line in lines)
    assert entry.remove()


def test_a_desktop_entry_escapes_percent_signs() -> None:
    assert 'Exec="/opt/100%%/python" -m nyctalus' in shortcut.desktop_entry(
        Path("/opt/100%/python"), Path("/icon.png")
    )


def test_the_start_menu_script_quotes_for_powershell() -> None:
    script = shortcut.start_menu_script(
        Path("C:/Users/O'Brien/Start Menu/Nyctalus.lnk"),
        Path("C:/Users/O'Brien/venv/Scripts/pythonw.exe"),
        Path("C:/icons/nyctalus.ico"),
    )

    assert "CreateShortcut('C:/Users/O''Brien/Start Menu/Nyctalus.lnk')" in script
    assert "$s.TargetPath = 'C:/Users/O''Brien/venv/Scripts/pythonw.exe'" in script
    assert "$s.Arguments = '-m nyctalus'" in script


def test_pythonw_is_used_where_there_is_one(tmp_path: Path) -> None:
    python = tmp_path / "python.exe"
    assert shortcut.windowless(python) == python
    (tmp_path / "pythonw.exe").touch()
    assert shortcut.windowless(python) == tmp_path / "pythonw.exe"
