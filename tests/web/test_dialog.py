import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nocek.web import dialog
from nocek.web.dialog import NoDialog


def only(*tools: str) -> Any:
    return lambda name: f"/usr/bin/{name}" if name in tools else None


def test_macos_passes_the_title_and_start_as_arguments() -> None:
    shown = dialog.command("Pick 'a' folder", Path("/Volumes/CARD"), "darwin", only("osascript"))

    assert shown[0] == "osascript"
    assert shown[-2:] == ["Pick 'a' folder", "/Volumes/CARD"]
    assert "choose folder" in " ".join(shown)


def test_windows_quotes_for_powershell() -> None:
    shown = dialog.command("O'Brien's card", Path("C:/Cards"), "win32", only("powershell"))

    assert shown[:2] == ["powershell", "-NoProfile"]
    assert "$d.Description = 'O''Brien''s card'" in shown[-1]
    assert "$d.SelectedPath = 'C:/Cards'" in shown[-1]


def test_linux_prefers_zenity_then_kdialog() -> None:
    zenity = dialog.command("Card", Path("/media/card"), "linux", only("zenity", "kdialog"))
    kdialog = dialog.command("Card", None, "linux", only("kdialog"))

    assert zenity == [
        "zenity",
        "--file-selection",
        "--directory",
        "--title=Card",
        "--filename=/media/card/",
    ]
    assert kdialog[:3] == ["kdialog", "--getexistingdirectory", str(Path.home())]


def test_no_dialog_anywhere() -> None:
    with pytest.raises(NoDialog):
        dialog.command("Card", None, "linux", only())


def answer(
    monkeypatch: pytest.MonkeyPatch, tool: str, code: int, out: str = "", err: str = ""
) -> None:
    monkeypatch.setattr(dialog, "command", lambda title, start: [tool])
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([tool], code, out, err)
    )


def test_the_chosen_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    answer(monkeypatch, "osascript", 0, "/Volumes/CARD/\n")

    assert dialog.choose_folder("Card") == Path("/Volumes/CARD")


@pytest.mark.parametrize(
    ("tool", "code", "err"),
    [
        ("osascript", 1, "execution error: User canceled. (-128)"),
        ("zenity", 1, "Gtk-WARNING: something about themes"),
        ("kdialog", 1, ""),
        ("powershell", 0, ""),
    ],
)
def test_cancelling(monkeypatch: pytest.MonkeyPatch, tool: str, code: int, err: str) -> None:
    answer(monkeypatch, tool, code, "", err)

    assert dialog.choose_folder("Card") is None


def test_a_dialog_that_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    answer(monkeypatch, "osascript", 1, "", "execution error: Not authorised (-1743)")

    with pytest.raises(NoDialog, match="-1743"):
        dialog.choose_folder("Card")


def test_a_start_that_is_not_a_folder_is_dropped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    starts: list[Path | None] = []

    def command(title: str, start: Path | None) -> list[str]:
        starts.append(start)
        return ["kdialog"]

    monkeypatch.setattr(dialog, "command", command)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 1, "", "")
    )

    dialog.choose_folder("Card", tmp_path / "gone")
    dialog.choose_folder("Card", tmp_path)

    assert starts == [None, tmp_path]


def test_the_api_opens_the_dialog(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[tuple[str, Path | None]] = []

    def choose(title: str, start: Path | None) -> Path | None:
        asked.append((title, start))
        return Path("/cards/a")

    monkeypatch.setattr(dialog, "choose_folder", choose)

    body = client.post("/api/folders/choose", json={"title": "Card", "start": "/cards"}).json()

    assert body == {"path": "/cards/a"}
    assert asked == [("Card", Path("/cards"))]


def test_the_api_says_when_there_is_no_dialog(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def none(title: str, start: Path | None) -> Path | None:
        raise NoDialog("none here")

    monkeypatch.setattr(dialog, "choose_folder", none)

    response = client.post("/api/folders/choose", json={})

    assert (response.status_code, response.json()["error"]) == (501, "no-folder-dialog")


def test_another_page_cannot_open_a_dialog(stranger: TestClient) -> None:
    assert stranger.post("/api/folders/choose", json={}).status_code == 403
