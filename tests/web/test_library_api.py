import csv
import io
from datetime import datetime
from pathlib import Path, PurePosixPath

import pytest
from fastapi.testclient import TestClient

from nyctalus.core.batdetect import interpret
from nyctalus.core.consensus import combine
from nyctalus.core.pipeline import RecordingResult
from nyctalus.core.region import Region
from nyctalus.storage.library import Library
from nyctalus.web.state import AppState
from tests.core.factories import calls, measured
from tests.recorders.test_pippyg import settings as pippyg_settings


def result(model_class: str, low_khz: float) -> RecordingResult:
    found = interpret(calls(model_class, low_khz))
    return RecordingResult(
        path=Path("x.wav"),
        versions={"nyctalus": "test"},
        batdetect=found,
        verdict=combine(Region("anywhere"), found, measured(end_khz=low_khz)),
    )


@pytest.fixture
def library(client: TestClient, app_state: AppState, tmp_path: Path) -> Library:
    """Balcony with a noctule night and a pipistrelle, a device, and one unplaced recording."""
    app_state.switch_library(Library.create(tmp_path / "library", shared=True))
    library = app_state.library
    assert library is not None
    repo = library.repository
    balcony = repo.add_site("Balcony", 50.0944, 19.9921)
    device = repo.device("pippyg", "e6659854e7389631")
    repo.add_device_config(
        device.id,
        datetime(2026, 9, 7, 19, 30),
        pippyg_settings(
            activity=[{"wake": "19:30", "sleep": "7:30", "mode": "bat"}],
            current_time={"year": 2026, "month": 9, "day": 7, "hour": 19, "minute": 30},
        ),
    )
    first = repo.start_import("/Volumes/CARD")
    for i, (at, cls, low, site) in enumerate(
        [
            (datetime(2026, 9, 7, 21, 0), "Nyctalus noctula", 20, balcony.id),
            (datetime(2026, 9, 8, 1, 0), "Pipistrellus pipistrellus", 45, balcony.id),
            (datetime(2026, 9, 8, 22, 0), "Nyctalus noctula", 20, None),
        ]
    ):
        rec = repo.add_recording(
            f"{i:064d}",
            PurePosixPath(f"pippyg/{i}.wav"),
            1000,
            recorded_at=at,
            device_id=device.id,
            site_id=site,
            import_id=first,
        )
        repo.save_result(rec.id, result(cls, low))
    repo.finish_import(first, copied=3, skipped=0)
    return library


def test_everything_needs_a_library(client: TestClient) -> None:
    response = client.get("/api/sites")

    assert response.status_code == 409
    assert response.json()["error"] == "no-library"


def test_the_catalogue_and_profiles(client: TestClient) -> None:
    assert "Nyctalus noctula" in client.get("/api/taxa").json()["species"]
    assert [p["id"] for p in client.get("/api/profiles").json()] == ["central-europe", "europe"]


def test_lists_sites_with_their_region(client: TestClient, library: Library) -> None:
    (site,) = client.get("/api/sites").json()

    assert site["name"] == "Balcony"
    assert site["profile"] == "central-europe"
    assert site["statuses"] == {}


def test_adds_and_edits_a_site(client: TestClient, library: Library) -> None:
    added = client.post("/api/sites", json={"name": "Allotment", "latitude": 50.11}).json()
    edited = client.put(
        f"/api/sites/{added['id']}", json={"name": "Garden", "latitude": 40.4, "longitude": -3.7}
    ).json()

    assert edited["name"] == "Garden"
    assert edited["profile"] == "europe"  # Madrid
    assert client.post("/api/sites", json={"name": "Garden"}).json()["error"] == "site-exists"


def test_sets_and_clears_a_species_status(client: TestClient, library: Library) -> None:
    site_id = client.get("/api/sites").json()[0]["id"]
    body = {"species": "Rhinolophus hipposideros", "status": "rare"}

    assert client.put(f"/api/sites/{site_id}/species", json=body).json()["statuses"] == {
        "Rhinolophus hipposideros": "rare"
    }
    cleared = client.put(f"/api/sites/{site_id}/species", json={**body, "status": None}).json()
    assert cleared["statuses"] == {}


def test_a_status_is_for_a_known_species(client: TestClient, library: Library) -> None:
    site_id = client.get("/api/sites").json()[0]["id"]

    unknown = client.put(
        f"/api/sites/{site_id}/species", json={"species": "Pteropus", "status": "rare"}
    )
    genus = client.put(
        f"/api/sites/{site_id}/species", json={"species": "Myotis", "status": "rare"}
    )

    assert unknown.json()["error"] == "unknown-species"
    assert genus.json()["error"] == "not-a-species"


def test_lists_imports_and_places_their_recordings(client: TestClient, library: Library) -> None:
    (imported,) = client.get("/api/imports").json()
    site_id = client.get("/api/sites").json()[0]["id"]

    assert imported["without_site"] == 1
    assigned = client.post(f"/api/imports/{imported['id']}/site", json={"site_id": site_id})
    assert assigned.json() == {"assigned": 1}
    assert client.get("/api/imports").json()[0]["without_site"] == 0


def test_lists_devices_with_their_configurations_and_issues(
    client: TestClient, library: Library
) -> None:
    (device,) = client.get("/api/devices").json()

    assert device["uid"] == "e6659854e7389631"
    (config,) = device["configs"]
    assert config["schedules"] == [{"wake": "19:30", "sleep": "07:30", "mode": "bat"}]
    assert [i["issue"] for i in config["issues"]] == ["starts-after-sunset"]


def test_names_a_device(client: TestClient, library: Library) -> None:
    device_id = client.get("/api/devices").json()[0]["id"]

    assert (
        client.put(f"/api/devices/{device_id}", json={"label": "Balcony pippyg"}).json()["label"]
        == "Balcony pippyg"
    )


def test_lists_recordings_with_filters(client: TestClient, library: Library) -> None:
    every = client.get("/api/recordings").json()
    noctules = client.get("/api/recordings", params={"taxa": "Nyctalus noctula"}).json()
    one_night = client.get(
        "/api/recordings", params={"first_night": "2026-09-07", "last_night": "2026-09-07"}
    ).json()

    assert every["total"] == 3
    assert [r["named"] for r in every["rows"]] == [
        [["Nyctalus noctula"]],
        [["Pipistrellus pipistrellus"]],
        [["Nyctalus noctula"]],
    ]
    assert noctules["total"] == 2
    assert one_night["total"] == 2  # 21:00 and 01:00 belong to the same night


def test_pages_through_recordings(client: TestClient, library: Library) -> None:
    page = client.get("/api/recordings", params={"offset": 1, "limit": 1}).json()

    assert page["total"] == 3
    assert [r["file_name"] for r in page["rows"]] == ["1.wav"]


def test_one_recording_with_its_result(client: TestClient, library: Library) -> None:
    first = client.get("/api/recordings").json()["rows"][0]["id"]

    body = client.get(f"/api/recordings/{first}").json()

    assert body["night"] == "2026-09-07"
    assert body["result"]["verdict"][0]["taxa"] == ["Nyctalus noctula"]
    assert client.get("/api/recordings/999").status_code == 404


def test_deletes_a_recording(client: TestClient, library: Library) -> None:
    first = client.get("/api/recordings").json()["rows"][0]["id"]

    assert client.delete(f"/api/recordings/{first}").json() == {"deleted": True}
    assert client.get("/api/recordings").json()["total"] == 2


def test_totals_and_nights(client: TestClient, library: Library) -> None:
    totals = client.get("/api/totals").json()
    nights = client.get("/api/nights").json()

    assert (totals["recordings"], totals["with_calls"], totals["nights"]) == (3, 3, 2)
    assert {tuple(s["taxa"]): s["recordings"] for s in totals["species"]} == {
        ("Nyctalus noctula",): 2,
        ("Pipistrellus pipistrellus",): 1,
    }
    assert nights == [
        {"night": "2026-09-07", "recordings": 2, "with_calls": 2, "named": 2},
        {"night": "2026-09-08", "recordings": 1, "with_calls": 1, "named": 1},
    ]


def test_totals_for_one_site(client: TestClient, library: Library) -> None:
    site_id = client.get("/api/sites").json()[0]["id"]

    assert client.get("/api/totals", params={"site_id": site_id}).json()["recordings"] == 2


def test_exports_species_as_csv(client: TestClient, library: Library) -> None:
    response = client.get("/api/export/species.csv")

    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="nyctalus-species.csv"' in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.text.lstrip("﻿"))))
    assert rows[0][:4] == ["scientific_name", "name", "recordings", "nights"]
    assert rows[1][:4] == ["Nyctalus noctula", "Common noctule", "2", "2"]


def test_exports_every_recording_as_csv(client: TestClient, library: Library) -> None:
    site_id = client.get("/api/sites").json()[0]["id"]

    every = list(
        csv.DictReader(io.StringIO(client.get("/api/export/recordings.csv").text.lstrip("﻿")))
    )
    one_site = client.get("/api/export/recordings.csv", params={"site_id": site_id}).text

    assert [r["status"] for r in every] == ["named", "named", "named"]
    assert every[1]["scientific_name"] == "Pipistrellus pipistrellus"
    assert every[1]["name"] == "Common pipistrelle"
    assert every[0]["site"] == "Balcony" and every[2]["site"] == ""
    assert one_site.count("\n") == 3  # header and two recordings


def test_nights_follow_the_date_filter(client: TestClient, library: Library) -> None:
    nights = client.get("/api/nights", params={"first_night": "2026-09-08"}).json()

    assert [n["night"] for n in nights] == ["2026-09-08"]
