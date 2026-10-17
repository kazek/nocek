"""A shortcut that starts Nocek without a terminal, in the system's own menu.

macOS gets a small application in ~/Applications, Windows an entry in the
Start menu, Linux a desktop entry. Each starts the Python Nocek is
installed in, so the shortcut keeps working for as long as that installation
does; installing Nocek somewhere else needs the shortcut made again.
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from nocek import __version__

ICONS = Path(__file__).parent / "icons"
BUNDLE_ID = "org.nocek.Nocek"
NAME = "Nocek"
COMMENT = "Identify bats from ultrasonic recordings"


class ShortcutError(Exception):
    pass


@dataclass(frozen=True)
class Shortcut:
    """Where a shortcut goes and what it starts."""

    path: Path
    python: Path

    def create(self) -> None:
        raise NotImplementedError

    def remove(self) -> bool:
        """Remove the shortcut; False if there was none."""
        if not self.path.exists():
            return False
        self.path.unlink()
        return True


class MacApp(Shortcut):
    """~/Applications/Nocek.app: a script that starts Nocek, with an icon."""

    def create(self) -> None:
        contents = self.path / "Contents"
        if self.path.exists():
            self.remove()
        (contents / "MacOS").mkdir(parents=True)
        (contents / "Resources").mkdir()
        with (contents / "Info.plist").open("wb") as f:
            plistlib.dump(info_plist(), f)
        launcher = contents / "MacOS" / NAME
        launcher.write_text(mac_launcher(self.python), encoding="utf-8")
        launcher.chmod(0o755)
        shutil.copy(ICONS / "nocek.icns", contents / "Resources" / "nocek.icns")

    def remove(self) -> bool:
        if not self.path.exists():
            return False
        # Only ever delete a bundle this module made.
        try:
            with (self.path / "Contents" / "Info.plist").open("rb") as f:
                ours = plistlib.load(f).get("CFBundleIdentifier") == BUNDLE_ID
        except (OSError, plistlib.InvalidFileException):
            ours = False
        if not ours:
            raise ShortcutError(f"{self.path} was not made by Nocek; leaving it alone")
        shutil.rmtree(self.path)
        return True


class StartMenu(Shortcut):
    """A Start menu entry, made through PowerShell to need nothing installed."""

    def create(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        script = start_menu_script(self.path, windowless(self.python), ICONS / "nocek.ico")
        done = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if done.returncode != 0:
            raise ShortcutError(done.stderr.strip() or "PowerShell could not make the shortcut")


class DesktopEntry(Shortcut):
    """~/.local/share/applications/nocek.desktop, for the desktop's menu."""

    def create(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(desktop_entry(self.python, ICONS / "nocek.png"), encoding="utf-8")


def for_this_system(home: Path | None = None, python: Path | None = None) -> Shortcut:
    home = home or Path.home()
    python = python or Path(sys.executable)
    if sys.platform == "darwin":
        return MacApp(home / "Applications" / f"{NAME}.app", python)
    if sys.platform == "win32":
        menu = home / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        return StartMenu(menu / f"{NAME}.lnk", python)
    return DesktopEntry(home / ".local" / "share" / "applications" / "nocek.desktop", python)


# --- What each file says ------------------------------------------------------


def info_plist() -> dict[str, object]:
    return {
        "CFBundleName": NAME,
        "CFBundleDisplayName": NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": NAME,
        "CFBundleIconFile": "nocek",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": __version__,
        # A server, not a window: no icon in the Dock. It is quit from the page.
        "LSUIElement": True,
    }


def mac_launcher(python: Path) -> str:
    """Start Nocek and let go of it.

    macOS then sees the application end at once, so the next click starts it
    again, and that start shows the Nocek already running. Were the server
    the application itself, a second click would only bring forward a program
    with no window, and nothing would appear.
    """
    return f"#!/bin/sh\n{_sh_quote(str(python))} -m nocek </dev/null >/dev/null 2>&1 &\n"


def windowless(python: Path) -> Path:
    """pythonw.exe beside python.exe: the same Python, without a console window."""
    candidate = python.with_name("pythonw.exe")
    return candidate if candidate.exists() else python


def start_menu_script(link: Path, python: Path, icon: Path) -> str:
    return "; ".join(
        [
            f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(str(link))})",
            f"$s.TargetPath = {_ps_quote(str(python))}",
            "$s.Arguments = '-m nocek'",
            f"$s.IconLocation = {_ps_quote(str(icon))}",
            f"$s.Description = {_ps_quote(COMMENT)}",
            "$s.Save()",
        ]
    )


def desktop_entry(python: Path, icon: Path) -> str:
    return "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            f"Name={NAME}",
            f"Comment={COMMENT}",
            f"Exec={_exec_quote(str(python))} -m nocek",
            f"Icon={icon}",
            "Terminal=false",
            "Categories=Science;Education;",
            "",
        ]
    )


def _sh_quote(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _exec_quote(text: str) -> str:
    """A desktop entry's Exec argument: quoted, with its reserved characters escaped.

    Escaped twice over, as the specification has it: once within the quotes,
    then once more as any string value, which doubles every backslash.
    """
    escaped = "".join("\\" + c if c in '"`$\\' else c for c in text)
    return ('"' + escaped + '"').replace("\\", "\\\\").replace("%", "%%")
