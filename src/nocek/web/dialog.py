"""The operating system's own folder dialog, opened by the server for the page.

A page cannot learn where a chosen folder is, but the server runs on the
user's own computer and can ask the system to show its dialog: osascript on
macOS, PowerShell on Windows, zenity or kdialog on Linux. Where none is
there, the page browses folders through the server instead (folders.py).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

# The macOS script takes its prompt and starting folder as arguments, so
# neither needs quoting. "tell me to activate" brings the dialog in front of
# the browser.
MAC_SCRIPT = [
    "on run argv",
    "tell me to activate",
    "if (count of argv) > 1 then",
    "set chosen to choose folder with prompt (item 1 of argv)"
    " default location (POSIX file (item 2 of argv))",
    "else",
    "set chosen to choose folder with prompt (item 1 of argv)",
    "end if",
    "return POSIX path of chosen",
    "end run",
]
MAC_CANCELLED = "(-128)"


class NoDialog(Exception):
    """This system has no folder dialog to open, or it could not be opened."""


def command(
    title: str,
    start: Path | None,
    platform: str = sys.platform,
    which: Callable[[str], str | None] = shutil.which,
) -> list[str]:
    """The command that shows the dialog and prints the chosen folder."""
    if platform == "darwin" and which("osascript"):
        lines = [arg for line in MAC_SCRIPT for arg in ("-e", line)]
        return ["osascript", *lines, title, *([str(start)] if start else [])]
    if platform == "win32" and which("powershell"):
        return [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-STA",
            "-Command",
            _windows(title, start),
        ]
    if which("zenity"):
        where = [f"--filename={start}/"] if start else []
        return ["zenity", "--file-selection", "--directory", f"--title={title}", *where]
    if which("kdialog"):
        return ["kdialog", "--getexistingdirectory", str(start or Path.home()), "--title", title]
    raise NoDialog(f"no folder dialog on {platform}")


def choose_folder(title: str, start: Path | None = None) -> Path | None:
    """Show the dialog and wait; the chosen folder, or None if the user cancelled."""
    if start is not None and not start.is_dir():
        start = None
    shown = command(title, start)
    done = subprocess.run(shown, capture_output=True, text=True, check=False)
    chosen = done.stdout.strip()
    if done.returncode == 0:
        return Path(chosen) if chosen else None
    # Each tool says "cancelled" its own way: osascript with an error numbered
    # -128, zenity and kdialog by exiting with 1.
    cancelled = (
        (MAC_CANCELLED in done.stderr) if shown[0] == "osascript" else (done.returncode == 1)
    )
    if cancelled:
        return None
    raise NoDialog(done.stderr.strip() or f"the folder dialog exited with {done.returncode}")


def _windows(title: str, start: Path | None) -> str:
    def quote(text: str) -> str:
        return "'" + text.replace("'", "''") + "'"

    return "; ".join(
        [
            "Add-Type -AssemblyName System.Windows.Forms",
            "[Console]::OutputEncoding = [Text.Encoding]::UTF8",
            "$d = New-Object System.Windows.Forms.FolderBrowserDialog",
            f"$d.Description = {quote(title)}",
            *([f"$d.SelectedPath = {quote(str(start))}"] if start else []),
            # An invisible window kept on top, so the dialog is not hidden behind the browser.
            "$owner = New-Object System.Windows.Forms.Form -Property @{ TopMost = $true }",
            "if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK)"
            " { $d.SelectedPath }",
        ]
    )
