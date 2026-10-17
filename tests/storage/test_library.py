from pathlib import Path, PurePosixPath

import pytest

from nyctalus.storage import settings
from nyctalus.storage.library import DATABASE, Library, LibraryError


def test_creates_a_library_in_a_new_folder(tmp_path: Path) -> None:
    with Library.create(tmp_path / "Nyctalus") as library:
        assert library.recordings_dir.is_dir()
        assert (library.root / DATABASE).is_file()


def test_will_not_create_over_an_existing_library(tmp_path: Path) -> None:
    Library.create(tmp_path).close()

    with pytest.raises(LibraryError, match="already"):
        Library.create(tmp_path)


def test_opens_an_existing_library(tmp_path: Path) -> None:
    with Library.create(tmp_path) as library:
        library.repository.add_site("Balcony")

    with Library.open(tmp_path) as library:
        assert [s.name for s in library.repository.sites()] == ["Balcony"]


def test_a_folder_without_a_database_is_not_a_library(tmp_path: Path) -> None:
    with pytest.raises(LibraryError, match="missing"):
        Library.open(tmp_path)


def test_a_damaged_database_is_reported(tmp_path: Path) -> None:
    (tmp_path / DATABASE).write_bytes(b"this is not sqlite" * 100)

    with pytest.raises(LibraryError):
        Library.open(tmp_path)


def test_maps_paths_inside_the_library(tmp_path: Path) -> None:
    with Library.create(tmp_path) as library:
        inside = PurePosixPath("pippyg-0/2026-09-02/DEV_000_20260902_213000.wav")

        on_disk = library.path_of(inside)

        assert on_disk == library.recordings_dir / "pippyg-0" / "2026-09-02" / inside.name
        assert library.relative(on_disk) == inside


def test_deleting_a_recording_removes_its_file(tmp_path: Path) -> None:
    with Library.create(tmp_path) as library:
        inside = PurePosixPath("pippyg-0/a.wav")
        file = library.path_of(inside)
        file.parent.mkdir(parents=True)
        file.write_bytes(b"audio")
        recording = library.repository.add_recording("a" * 64, inside, size_bytes=5)

        library.delete_recording(recording.id)

        assert not file.exists()
        assert library.repository.recording(recording.id) is None


def test_settings_remember_the_library(tmp_path: Path) -> None:
    path = tmp_path / "config" / "settings.json"

    assert settings.load(path) == settings.Settings()
    settings.save(settings.Settings(library=tmp_path / "Nyctalus"), path)

    assert settings.load(path).library == tmp_path / "Nyctalus"
    assert not path.with_name("settings.json.part").exists()


def test_application_folders_are_named_after_the_application() -> None:
    assert settings.models_dir().parent.name.lower() == "nyctalus"
    assert settings.default_library().name == "Nyctalus"
