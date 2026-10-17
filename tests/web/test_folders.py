from pathlib import Path

from fastapi.testclient import TestClient


def test_starts_from_home_and_mounted_volumes(client: TestClient) -> None:
    body = client.get("/api/folders").json()

    assert body["path"] is None
    assert str(Path.home()) in [f["path"] for f in body["folders"]]


def test_lists_folders_and_counts_recordings(client: TestClient, tmp_path: Path) -> None:
    card = tmp_path / "card"
    (card / "2026_03_sep_21").mkdir(parents=True)
    (card / "2026_03_sep_21" / "DEV_000_20260903_213000.wav").write_bytes(b"x")
    (card / "2026_03_sep_21" / "DEV_000_20260903_213500.WAV").write_bytes(b"x")
    (card / ".Spotlight-V100").mkdir()
    (card / "device_settings_20260903_1815.json").write_text("{}")

    body = client.get("/api/folders", params={"path": str(card)}).json()

    assert body["path"] == str(card)
    assert body["parent"] == str(tmp_path)
    assert body["recordings"] == 0
    assert body["folders"] == [
        {"name": "2026_03_sep_21", "path": str(card / "2026_03_sep_21"), "recordings": 2}
    ]


def test_lists_folders_only(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("contents-must-not-leak")

    response = client.get("/api/folders", params={"path": str(tmp_path / "notes.txt")})

    assert response.status_code == 404
    assert "contents-must-not-leak" not in response.text


def test_refuses_a_relative_path(client: TestClient) -> None:
    response = client.get("/api/folders", params={"path": "../.."})

    assert response.status_code == 404
    assert response.json()["error"] == "not-a-folder"


def test_a_missing_folder(client: TestClient, tmp_path: Path) -> None:
    assert client.get("/api/folders", params={"path": str(tmp_path / "gone")}).status_code == 404
