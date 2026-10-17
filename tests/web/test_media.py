import io
from pathlib import Path, PurePosixPath

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from nyctalus.core.audio import Samples
from nyctalus.storage.library import Library
from nyctalus.web import media
from nyctalus.web.state import AppState
from tests import synth


@pytest.fixture
def library(app_state: AppState, tmp_path: Path) -> Library:
    app_state.switch_library(Library.create(tmp_path / "library", shared=True))
    assert app_state.library is not None
    return app_state.library


def add(library: Library, samples: Samples, name: str = "a.wav") -> int:
    inside = PurePosixPath(f"pippyg/{name}")
    path = library.path_of(inside)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, samples, synth.SAMPLE_RATE, subtype="PCM_16")
    return library.repository.add_recording(name.ljust(64, "0"), inside, path.stat().st_size).id


def test_slows_the_sound_down_without_touching_it(client: TestClient, library: Library) -> None:
    samples = synth.tone(40, 0.05)
    recording = add(library, samples)

    response = client.get(f"/api/recordings/{recording}/audio")

    assert response.headers["content-type"] == "audio/wav"
    data, rate = sf.read(io.BytesIO(response.content), dtype="float32")
    assert rate == 38_400
    np.testing.assert_allclose(data, samples, atol=1 / 32768)


def test_another_slowdown(client: TestClient, library: Library) -> None:
    recording = add(library, synth.tone(40, 0.05))

    response = client.get(f"/api/recordings/{recording}/audio", params={"slowdown": 20})

    assert sf.info(io.BytesIO(response.content)).samplerate == 19_200
    assert (
        client.get(f"/api/recordings/{recording}/audio", params={"slowdown": 0}).status_code == 422
    )


def test_serves_parts_of_the_sound_for_seeking(client: TestClient, library: Library) -> None:
    recording = add(library, synth.tone(40, 0.05))
    whole = client.get(f"/api/recordings/{recording}/audio").content

    part = client.get(f"/api/recordings/{recording}/audio", headers={"range": "bytes=100-199"})
    tail = client.get(f"/api/recordings/{recording}/audio", headers={"range": "bytes=-50"})
    beyond = client.get(
        f"/api/recordings/{recording}/audio", headers={"range": f"bytes={len(whole)}-"}
    )

    assert part.status_code == 206
    assert part.content == whole[100:200]
    assert part.headers["content-range"] == f"bytes 100-199/{len(whole)}"
    assert tail.content == whole[-50:]
    assert beyond.status_code == 416


def test_a_missing_file_or_recording(client: TestClient, library: Library) -> None:
    recording = add(library, synth.tone(40, 0.05))
    library.path_of(PurePosixPath("pippyg/a.wav")).unlink()

    assert client.get(f"/api/recordings/{recording}/audio").json()["error"] == "file-missing"
    assert client.get("/api/recordings/999/audio").json()["error"] == "no-such-recording"


def test_a_path_outside_the_library_is_never_served(client: TestClient, library: Library) -> None:
    secret = library.root.parent / "secret.wav"
    sf.write(secret, synth.tone(40, 0.05), synth.SAMPLE_RATE)
    recording = library.repository.add_recording("b" * 64, PurePosixPath("../../secret.wav"), 1)

    assert client.get(f"/api/recordings/{recording.id}/audio").status_code == 404


def test_the_spectrogram_shows_a_tone_where_it_is(client: TestClient, library: Library) -> None:
    recording = add(library, synth.audio(synth.silence(0.05), synth.tone(40, 0.05)).samples)

    response = client.get(f"/api/recordings/{recording}/spectrogram", params={"width": 50})

    columns, rows = int(response.headers["x-columns"]), int(response.headers["x-rows"])
    pixels = np.frombuffer(response.content, np.uint8).reshape(columns, rows)
    min_khz = float(response.headers["x-min-khz"])
    khz_per_row = float(response.headers["x-khz-per-row"])
    assert columns <= 50
    brightest = min_khz + khz_per_row * int(np.argmax(pixels[-5:].max(axis=0)))
    assert brightest == pytest.approx(40, abs=1)
    # Silence first, the tone after it.
    assert np.max(pixels[: columns // 3]) < np.max(pixels[-columns // 3 :])
    assert float(response.headers["x-duration-s"]) == pytest.approx(0.1, abs=0.001)


def test_the_spectrogram_keeps_short_calls_when_squeezed(tmp_path: Path) -> None:
    # One 3 ms call in a second of silence, squeezed to 20 columns.
    samples = synth.calls_at(synth.sweep(55, 45, 0.003), [0.5], duration_s=1.0)
    path = tmp_path / "call.wav"
    sf.write(path, samples, synth.SAMPLE_RATE)

    picture = media.image(path, width=20)

    loudest = picture.pixels.max(axis=1)
    assert picture.pixels.shape[0] <= 20
    assert np.max(loudest) == 255
    assert loudest[int(np.argmax(loudest))] - np.median(loudest) > 100


def test_the_spectrogram_covers_the_frequencies_asked_for(
    client: TestClient, library: Library
) -> None:
    recording = add(library, synth.tone(40, 0.05))

    response = client.get(
        f"/api/recordings/{recording}/spectrogram", params={"min_khz": 20, "max_khz": 60}
    )

    rows = int(response.headers["x-rows"])
    top = float(response.headers["x-min-khz"]) + (rows - 1) * float(
        response.headers["x-khz-per-row"]
    )
    assert float(response.headers["x-min-khz"]) >= 20
    assert top <= 60


def test_a_long_recording_is_drawn_in_blocks(tmp_path: Path) -> None:
    samples = synth.calls_at(synth.sweep(55, 45, 0.005), [1.0, 30.0], duration_s=32.0)
    path = tmp_path / "long.wav"
    sf.write(path, samples, synth.SAMPLE_RATE)

    picture = media.image(path, width=400)

    loud = np.flatnonzero(picture.pixels.max(axis=1) > 200) * picture.seconds_per_column
    assert picture.pixels.shape[0] <= 400
    assert min(loud) == pytest.approx(1.0, abs=0.2)
    assert max(loud) == pytest.approx(30.0, abs=0.2)


def test_a_damaged_recording_is_reported(client: TestClient, library: Library) -> None:
    recording = add(library, synth.tone(40, 0.05))
    library.path_of(PurePosixPath("pippyg/a.wav")).write_bytes(b"RIFF" + b"x" * 100)

    for media_kind in ("spectrogram", "audio"):
        response = client.get(f"/api/recordings/{recording}/{media_kind}")

        assert response.status_code == 422
        assert response.json()["error"] == "unreadable-recording"


def test_the_spectrogram_of_a_stretch(client: TestClient, library: Library) -> None:
    # A tone in the second half only: the first half drawn alone stays dark.
    recording = add(library, synth.audio(synth.noise(0.05), synth.tone(40, 0.05)).samples)
    url = f"/api/recordings/{recording}/spectrogram"

    quiet = client.get(url, params={"start_s": 0, "end_s": 0.04, "width": 50})
    loud = client.get(url, params={"start_s": 0.06, "end_s": 0.1, "width": 50})

    assert float(quiet.headers["x-start-s"]) == 0
    assert float(loud.headers["x-start-s"]) == pytest.approx(0.06, abs=1e-4)
    assert float(loud.headers["x-duration-s"]) == pytest.approx(0.1, abs=1e-3)
    columns = int(loud.headers["x-columns"])
    assert columns * float(loud.headers["x-seconds-per-column"]) == pytest.approx(0.04, abs=0.005)
    assert client.get(url, params={"start_s": 0.05, "end_s": 0.01}).status_code == 422
