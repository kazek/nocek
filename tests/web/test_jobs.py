from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nyctalus.core import battybird, pipeline
from nyctalus.core.batdetect import interpret
from nyctalus.core.pipeline import Analyser, RecordingResult
from nyctalus.core.region import Region
from nyctalus.storage.library import Library
from nyctalus.storage.settings import Settings
from nyctalus.web.app import create_app
from nyctalus.web.jobs import Environment, JobRunner, Kind
from nyctalus.web.security import COOKIE
from nyctalus.web.state import AppState
from tests.core.factories import FakeBatDetect, FakeBattyBird, calls, opinion
from tests.recorders.test_pippyg import settings as pippyg_settings
from tests.storage.test_importer import wav
from tests.web.conftest import BASE, PORT, TOKEN

NOCTULES = interpret(calls("Nyctalus noctula", low_khz=20))
SECOND = battybird.Analysis(
    opinion=opinion("Nyctalus noctula", score=0.9), not_a_bat=(), windows=()
)


class Setup:
    """A library, a card, and a runner whose models are stand-ins."""

    def __init__(self, tmp_path: Path) -> None:
        self.library_root = tmp_path / "library"
        Library.create(self.library_root).close()
        self.card = tmp_path / "card"
        wav(self.card / "2026_03_sep_21" / "DEV_000_20260903_213000.wav", seed=40)
        wav(self.card / "2026_04_sep_02" / "DEV_000_20260904_021500.wav", seed=45)
        (self.card / "device_settings_20260903_1815.json").write_text(pippyg_settings())
        self.settings = Settings(library=self.library_root)
        self.downloads: list[str] = []
        self.analysers = 0
        self.on_analyse: Callable[[], object] = lambda: None
        self.runner = JobRunner(
            Environment(
                library_root=lambda: self.library_root,
                settings=lambda: self.settings,
                models_dir=tmp_path / "models",
                make_analyser=self.make_analyser,
                ensure_models=self.ensure_models,
            )
        )

    def make_analyser(self, models: Path, s: pipeline.Settings) -> Analyser:
        self.analysers += 1
        setup = self

        class Watched(FakeBatDetect):
            def analyse(self, path: Path) -> Any:
                setup.on_analyse()
                return super().analyse(path)

        return Analyser(
            models,
            Region("anywhere"),
            s,
            batdetect_model=Watched(NOCTULES),
            battybird_model=FakeBattyBird(SECOND),
        )

    def ensure_models(self, directory: Path, head: str, progress: Any) -> None:
        self.downloads.append(head)
        progress("weights.tflite", 5, 10)

    def run(self, kind: Kind, **params: Any) -> dict[str, Any]:
        job = self.runner.submit(kind, **params)
        finished = self.runner.wait(job["id"])
        assert finished is not None
        return finished

    def results(self) -> list[RecordingResult]:
        with Library.open(self.library_root) as library:
            repo = library.repository
            ids = [r[0] for r in repo.conn.execute("SELECT recording_id FROM result")]
            return [r for i in ids if (r := repo.result(i)) is not None]


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[Setup]:
    s = Setup(tmp_path)
    s.runner.start()
    yield s
    s.runner.stop()


def test_an_import_is_followed_by_its_analysis(setup: Setup) -> None:
    imported = setup.run(Kind.IMPORT, folder=str(setup.card))

    assert imported["status"] == "done"
    assert imported["result"]["copied"] == 2
    analysis = setup.runner.wait(imported["result"]["analysis_job"])
    assert analysis is not None
    assert analysis["status"] == "done"
    assert analysis["result"] == {"analysed": 2, "failed": 0}
    assert len(setup.results()) == 2


def test_analysis_fetches_missing_models_first(setup: Setup) -> None:
    setup.run(Kind.IMPORT, folder=str(setup.card))

    assert setup.downloads == ["Bavaria"]


def test_without_battybird_no_models_are_needed(setup: Setup) -> None:
    setup.settings = replace(setup.settings, passes=("key", "batdetect2"))

    setup.run(Kind.IMPORT, folder=str(setup.card))

    assert setup.downloads == []


def test_the_models_are_loaded_once(setup: Setup) -> None:
    setup.run(Kind.IMPORT, folder=str(setup.card))
    setup.run(Kind.ANALYSE, scope="new")

    assert setup.analysers == 1


def test_a_download_job_reports_bytes(setup: Setup) -> None:
    job = setup.run(Kind.MODELS)

    assert job["status"] == "done"
    assert (job["phase"], job["done"], job["total"]) == ("models", 5, 10)


def test_cancelling_stops_at_a_file_boundary(setup: Setup) -> None:
    def cancel_the_running_analysis() -> None:
        for job in setup.runner.jobs():
            if job["kind"] == "analyse" and job["status"] == "running":
                setup.runner.cancel(job["id"])

    setup.on_analyse = cancel_the_running_analysis
    # The test tones hold no pulses; without the sieve the network still sees them.
    setup.settings = replace(setup.settings, sieve=False)
    imported = setup.run(Kind.IMPORT, folder=str(setup.card))

    analysis = setup.runner.wait(imported["result"]["analysis_job"])

    assert analysis is not None
    assert analysis["status"] == "cancelled"
    assert len(setup.results()) == 1  # the file being analysed was finished and kept


def test_a_job_cancelled_before_it_starts_does_nothing(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    job = s.runner.submit(Kind.IMPORT, folder=str(s.card))
    s.runner.cancel(job["id"])
    s.runner.start()

    finished = s.runner.wait(job["id"])
    s.runner.stop()

    assert finished is not None
    assert finished["status"] == "cancelled"
    assert s.results() == []


def test_stale_results_are_analysed_again(setup: Setup) -> None:
    setup.run(Kind.IMPORT, folder=str(setup.card))
    with Library.open(setup.library_root) as library:
        repo = library.repository
        first = repo.result(1)
        assert first is not None
        repo.save_result(1, replace(first, versions={"nyctalus": "0.0.1"}))

    assert setup.run(Kind.ANALYSE, scope="new")["result"]["analysed"] == 0
    assert setup.run(Kind.ANALYSE, scope="stale")["result"]["analysed"] == 1


def test_no_library_no_job(setup: Setup) -> None:
    setup.runner.env = replace(setup.runner.env, library_root=lambda: None)

    job = setup.run(Kind.ANALYSE)

    assert (job["status"], job["error"]) == ("failed", "no-library")


def test_importing_a_missing_folder(setup: Setup) -> None:
    job = setup.run(Kind.IMPORT, folder=str(setup.card / "gone"))

    assert (job["status"], job["error"]) == ("failed", "not-a-folder")


def test_importing_to_an_unknown_site(setup: Setup) -> None:
    job = setup.run(Kind.IMPORT, folder=str(setup.card), site_id=99)

    assert (job["status"], job["error"]) == ("failed", "no-such-site")


@pytest.fixture
def api(setup: Setup, tmp_path: Path) -> Iterator[TestClient]:
    state = AppState(tmp_path / "config" / "settings.json", TOKEN, PORT)
    setup.runner.stop()  # the app starts its own copy of the runner
    runner = JobRunner(setup.runner.env)
    with TestClient(create_app(state, runner), base_url=BASE) as client:
        client.cookies.set(COOKIE, TOKEN)
        yield client
    state.close()


def test_the_api_starts_and_reports_jobs(api: TestClient, setup: Setup) -> None:
    job = api.post("/api/jobs/import", json={"folder": str(setup.card)}).json()

    assert job["kind"] == "import" and job["status"] in {"queued", "running", "done"}
    assert api.app.state.jobs.wait(job["id"])["status"] == "done"  # type: ignore[attr-defined]
    assert {j["kind"] for j in api.get("/api/jobs").json()} >= {"import"}
    assert api.get(f"/api/jobs/{job['id']}").json()["result"]["copied"] == 2


def test_the_api_reports_unknown_and_finished_jobs(api: TestClient, setup: Setup) -> None:
    job = api.post("/api/jobs/models").json()
    api.app.state.jobs.wait(job["id"])  # type: ignore[attr-defined]

    assert api.get("/api/jobs/999").status_code == 404
    assert api.post(f"/api/jobs/{job['id']}/cancel").json()["error"] == "job-not-running"


def test_the_api_says_which_models_are_missing(api: TestClient) -> None:
    body = api.get("/api/models").json()

    assert body["present"] is False
    assert "BirdNET_GLOBAL_6K_V2.4_Model_FP32.tflite" in body["missing"]
