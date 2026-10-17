from pathlib import Path

from fastapi.testclient import TestClient

from nyctalus import __version__
from nyctalus.storage.library import Library
from nyctalus.web.app import create_app
from nyctalus.web.security import COOKIE
from nyctalus.web.state import AppState
from tests.web.conftest import BASE, TOKEN


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"version": __version__}


def test_about_names_the_versions(client: TestClient) -> None:
    about = client.get("/api/about").json()

    assert about["versions"]["nyctalus"] == __version__
    assert set(about["versions"]) == {"nyctalus", "batdetect2", "battybirdnet"}
    assert about["log"].endswith("nyctalus.log")


def test_quit_stops_the_server(app_state: AppState) -> None:
    stopped: list[bool] = []
    client = TestClient(create_app(app_state, on_quit=lambda: stopped.append(True)), base_url=BASE)
    client.cookies.set(COOKIE, TOKEN)

    assert client.post("/api/quit").status_code == 202
    assert stopped == [True]


def test_settings_start_from_the_defaults(client: TestClient) -> None:
    assert client.get("/api/settings").json() == {
        "library": None,
        "language": None,
        "passes": ["key", "batdetect2", "battybirdnet"],
        "sieve": True,
        "device": "auto",
    }


def test_settings_are_changed_and_kept(client: TestClient, app_state: AppState) -> None:
    changed = client.put(
        "/api/settings", json={"language": "pl", "passes": ["key", "batdetect2"], "device": "cpu"}
    ).json()

    assert changed["language"] == "pl"
    assert changed["passes"] == ["key", "batdetect2"]
    assert changed["sieve"] is True  # untouched
    assert app_state.settings_path.is_file()
    assert (
        client.put("/api/settings", json={"follow_browser_language": True}).json()["language"]
        is None
    )


def test_an_invalid_setting_is_refused(client: TestClient) -> None:
    response = client.put("/api/settings", json={"device": "abacus"})

    assert response.status_code == 422
    assert response.json()["error"] == "invalid-setting"


def test_no_library_at_first(client: TestClient) -> None:
    body = client.get("/api/library").json()

    assert body["open"] is False
    assert body["default_path"].endswith("Nyctalus")


def test_creates_and_remembers_a_library(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "Bats"

    body = client.post("/api/library/create", json={"path": str(root)}).json()

    assert body == {
        "open": True,
        "path": str(root),
        "error": None,
        "default_path": body["default_path"],
    }
    assert client.get("/api/settings").json()["library"] == str(root)


def test_opens_an_existing_library(client: TestClient, tmp_path: Path) -> None:
    Library.create(tmp_path / "Bats").close()

    assert client.post("/api/library/open", json={"path": str(tmp_path / "Bats")}).json()["open"]


def test_reopens_the_remembered_library(tmp_path: Path) -> None:
    Library.create(tmp_path / "Bats").close()
    settings = tmp_path / "config" / "settings.json"
    first = AppState(settings, "t", 6475)
    first.switch_library(Library.open(tmp_path / "Bats", shared=True))
    first.close()

    again = AppState(settings, "t", 6475)

    assert again.library is not None
    assert again.library.root == tmp_path / "Bats"
    again.close()


def test_a_folder_that_is_not_a_library(client: TestClient, tmp_path: Path) -> None:
    response = client.post("/api/library/open", json={"path": str(tmp_path)})

    assert response.status_code == 409
    assert response.json()["error"] == "library-unavailable"


def test_a_relative_library_path_is_refused(client: TestClient) -> None:
    response = client.post("/api/library/create", json={"path": "Bats"})

    assert response.status_code == 422
    assert response.json()["error"] == "not-an-absolute-path"
