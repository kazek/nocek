import sqlite3
from datetime import date, datetime
from pathlib import Path, PurePosixPath

import pytest

from nyctalus.core.pipeline import RecordingResult
from nyctalus.core.region import Status
from nyctalus.core.taxonomy import Taxon
from nyctalus.storage import database
from nyctalus.storage.repository import Repository
from nyctalus.storage.serialize import result_to_dict

HORSESHOE = Taxon("Rhinolophus hipposideros")


@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    return Repository(database.connect(tmp_path / "db.sqlite"))


def add(repo: Repository, sha: str = "a" * 64, at: datetime | None = None) -> int:
    path = PurePosixPath(f"pippyg-0/{sha[:8]}.wav")
    return repo.add_recording(sha, path, size_bytes=1000, recorded_at=at).id


def test_a_site_region_follows_location_and_overrides(repo: Repository) -> None:
    krakow = repo.add_site("Balcony", 50.09, 19.99)
    repo.set_species_status(krakow.id, HORSESHOE, Status.RARE)

    region = repo.region_of(krakow)

    assert region.name == "Central Europe"
    assert region.status(HORSESHOE) is Status.RARE
    repo.set_species_status(krakow.id, HORSESHOE, None)
    assert repo.region_of(krakow).status(HORSESHOE) is Status.OCCURS


def test_site_names_are_unique(repo: Repository) -> None:
    repo.add_site("Balcony")

    with pytest.raises(sqlite3.IntegrityError):
        repo.add_site("Balcony")


def test_a_device_is_found_again_by_its_identifier(repo: Repository) -> None:
    first = repo.device("pippyg", "e6659854e7389631")
    again = repo.device("pippyg", "e6659854e7389631")

    assert again == first
    assert repo.device("pippyg", "other").id != first.id


def test_a_configuration_is_kept_once(repo: Repository) -> None:
    device = repo.device("pippyg", "e6659854e7389631")
    written = datetime(2026, 10, 7, 21, 22)

    assert repo.add_device_config(device.id, written, '{"trigger_sensitivity": 48}')
    assert not repo.add_device_config(device.id, written, '{"trigger_sensitivity": 48}')


def test_a_recording_knows_its_night(repo: Repository) -> None:
    recording_id = add(repo, at=datetime(2026, 9, 3, 2, 0))

    recording = repo.recording(recording_id)

    assert recording is not None
    assert recording.night == date(2026, 9, 2)
    assert recording.recorded_at == datetime(2026, 9, 3, 2, 0)
    assert repo.recording_by_sha256("a" * 64) == recording


def test_the_same_file_is_the_same_recording(repo: Repository) -> None:
    add(repo, sha="a" * 64)

    with pytest.raises(sqlite3.IntegrityError):
        repo.add_recording("a" * 64, PurePosixPath("elsewhere/copy.wav"), size_bytes=1000)


def test_a_result_is_stored_and_read_back(repo: Repository, two_bats: RecordingResult) -> None:
    recording_id = add(repo)

    repo.save_result(recording_id, two_bats)

    stored = repo.result(recording_id)
    assert stored is not None
    assert result_to_dict(stored) == result_to_dict(two_bats)
    assert repo.recordings_without_result() == []


def test_a_result_writes_one_row_per_animal(repo: Repository, two_bats: RecordingResult) -> None:
    recording_id = add(repo)

    repo.save_result(recording_id, two_bats)
    repo.save_result(recording_id, two_bats)  # replaced, not added

    rows = repo.conn.execute(
        "SELECT model_class, taxa, n_calls FROM source_verdict WHERE recording_id = ?"
        " ORDER BY position",
        (recording_id,),
    ).fetchall()
    assert [(r["model_class"], r["n_calls"]) for r in rows] == [
        ("Pipistrellus pipistrellus", 10),
        ("Nyctalus noctula", 10),
    ]
    assert rows[0]["taxa"] == '["Pipistrellus pipistrellus"]'


def test_finds_results_from_other_versions(repo: Repository, two_bats: RecordingResult) -> None:
    recording_id = add(repo)
    repo.save_result(recording_id, two_bats)
    same = dict(two_bats.versions)

    on_another_device = {**same, "batdetect2-device": "cpu"}
    newer_model = {**same, "batdetect2": "2.0.0"}

    assert repo.results_from_other_versions(same) == []
    assert repo.results_from_other_versions(on_another_device) == []
    assert repo.results_from_other_versions(newer_model) == [recording_id]


def test_deleting_a_recording_deletes_its_result(
    repo: Repository, two_bats: RecordingResult
) -> None:
    recording_id = add(repo)
    repo.save_result(recording_id, two_bats)

    repo.delete_recording(recording_id)

    assert repo.recording(recording_id) is None
    assert repo.result(recording_id) is None
    assert repo.conn.execute("SELECT COUNT(*) FROM source_verdict").fetchone()[0] == 0


def test_a_failed_transaction_keeps_nothing(repo: Repository) -> None:
    with pytest.raises(sqlite3.IntegrityError), repo.transaction():
        add(repo, sha="b" * 64)
        add(repo, sha="b" * 64)

    assert repo.recording_by_sha256("b" * 64) is None
