"""Long work done in the background: importing, analysing, downloading models.

One worker thread takes jobs from a queue, one at a time, so the models are
loaded once and kept, and only one job writes to the library at a time. The
worker has its own database connection; the server keeps reading through
its own while a job writes. The page asks for progress by polling.

A cancelled job stops at the next file boundary, so nothing is left half
done: every file copied or analysed before that is kept.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from nyctalus.core import battybird, pipeline
from nyctalus.core.pipeline import Analyser, Pass
from nyctalus.core.region import Region, profile_for
from nyctalus.storage.importer import ImportReport, import_folder
from nyctalus.storage.library import Library, LibraryError
from nyctalus.storage.settings import Settings

log = logging.getLogger(__name__)


class Kind(StrEnum):
    IMPORT = "import"
    ANALYSE = "analyse"
    MODELS = "models"


class Status(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Phase(StrEnum):
    MODELS = "models"  # downloading model weights
    COPYING = "copying"
    ANALYSING = "analysing"


class JobError(Exception):
    """A job that cannot go on, with a code for the interface."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


class Cancelled(Exception):
    pass


@dataclass
class Job:
    id: int
    kind: Kind
    params: dict[str, Any]
    status: Status = Status.QUEUED
    phase: Phase | None = None
    done: int = 0
    total: int = 0
    item: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    detail: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": str(self.kind),
            "params": self.params,
            "status": str(self.status),
            "phase": str(self.phase) if self.phase else None,
            "done": self.done,
            "total": self.total,
            "item": self.item,
            "result": self.result,
            "error": self.error,
            "detail": self.detail,
            "created_at": self.created_at.isoformat(timespec="seconds"),
            "started_at": self.started_at.isoformat(timespec="seconds")
            if self.started_at
            else None,
            "finished_at": self.finished_at.isoformat(timespec="seconds")
            if self.finished_at
            else None,
        }


AnalyserFactory = Callable[[Path, pipeline.Settings], Analyser]
EnsureModels = Callable[[Path, str, Callable[[str, int, int], None]], None]


@dataclass(frozen=True)
class Environment:
    """What the worker needs from the application, so tests can supply their own."""

    library_root: Callable[[], Path | None]
    settings: Callable[[], Settings]
    models_dir: Path
    make_analyser: AnalyserFactory = lambda models, s: Analyser(
        models, profile_for(None, None).region, s
    )
    ensure_models: EnsureModels = lambda d, head, progress: battybird.ensure_models(
        d, head, progress
    )


class JobRunner:
    def __init__(self, environment: Environment, history: int = 50) -> None:
        self.env = environment
        self.history = history
        self._jobs: dict[int, Job] = {}
        self._queue: queue.Queue[Job | None] = queue.Queue()
        self._lock = threading.Lock()
        self._next_id = 1
        self._thread: threading.Thread | None = None
        self._analyser: tuple[pipeline.Settings, Analyser] | None = None

    # --- Control ---------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._work, name="nyctalus-jobs", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Cancel what is running, drop what is queued, and wait for the worker."""
        with self._lock:
            for job in self._jobs.values():
                job.cancel.set()
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=30)

    def submit(self, kind: Kind, **params: Any) -> dict[str, Any]:
        with self._lock:
            job = Job(id=self._next_id, kind=kind, params=params)
            self._next_id += 1
            self._jobs[job.id] = job
            for old in sorted(self._jobs)[: max(0, len(self._jobs) - self.history)]:
                if self._jobs[old].finished_at is not None:
                    del self._jobs[old]
            snapshot = job.to_dict()
        self._queue.put(job)
        return snapshot

    def get(self, job_id: int) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.to_dict() if job else None

    def jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [j.to_dict() for j in sorted(self._jobs.values(), key=lambda j: -j.id)]

    def cancel(self, job_id: int) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.finished_at is not None:
                return False
            job.cancel.set()
            return True

    def wait(self, job_id: int, timeout: float = 10.0) -> dict[str, Any] | None:
        """Block until a job has finished; for tests and the command line."""
        deadline = threading.Event()
        timer = threading.Timer(timeout, deadline.set)
        timer.start()
        try:
            while not deadline.is_set():
                job = self.get(job_id)
                if job is None or job["finished_at"] is not None:
                    return job
                deadline.wait(0.01)
            return self.get(job_id)
        finally:
            timer.cancel()

    # --- The worker ------------------------------------------------------

    def _work(self) -> None:
        while (job := self._queue.get()) is not None:
            self._run(job)

    def _run(self, job: Job) -> None:
        self._set(job, status=Status.RUNNING, started_at=datetime.now(UTC))
        try:
            if job.cancel.is_set():
                raise Cancelled
            handler = {
                Kind.IMPORT: self._import,
                Kind.ANALYSE: self._analyse,
                Kind.MODELS: self._models,
            }
            result = handler[job.kind](job)
            self._set(job, status=Status.DONE, result=result)
        except Cancelled:
            self._set(job, status=Status.CANCELLED)
        except JobError as error:
            self._set(job, status=Status.FAILED, error=error.code, detail=error.detail)
        except (LibraryError, battybird.ModelError, OSError) as error:
            log.warning("job %d failed: %s", job.id, error)
            self._set(job, status=Status.FAILED, error="failed", detail=str(error))
        except Exception as error:
            log.exception("job %d failed unexpectedly", job.id)
            self._set(job, status=Status.FAILED, error="internal-error", detail=str(error))
        finally:
            self._set(job, finished_at=datetime.now(UTC), item=None)

    def _set(self, job: Job, **changes: Any) -> None:
        with self._lock:
            for name, value in changes.items():
                setattr(job, name, value)

    def _progress(self, job: Job, phase: Phase) -> Callable[[int, int, str], None]:
        def report(done: int, total: int, item: str) -> None:
            self._set(job, phase=phase, done=done, total=total, item=item)
            if job.cancel.is_set():
                raise Cancelled

        return report

    def _library(self) -> Library:
        root = self.env.library_root()
        if root is None:
            raise JobError("no-library")
        return Library.open(root)

    # --- Jobs ------------------------------------------------------------

    def _import(self, job: Job) -> dict[str, Any]:
        folder = Path(job.params["folder"])
        if not folder.is_absolute() or not folder.is_dir():
            raise JobError("not-a-folder", str(folder))
        with self._library() as library:
            site = None
            if job.params.get("site_id") is not None:
                site = next(
                    (s for s in library.repository.sites() if s.id == job.params["site_id"]), None
                )
                if site is None:
                    raise JobError("no-such-site", str(job.params["site_id"]))
            report = import_folder(
                library, folder, site=site, progress=self._progress(job, Phase.COPYING)
            )
        result = report_to_dict(report)
        if report.copied:
            result["analysis_job"] = self.submit(Kind.ANALYSE, scope="new")["id"]
        return result

    def _analyse(self, job: Job) -> dict[str, Any]:
        settings = self._pipeline_settings()
        if Pass.BATTYBIRDNET in settings.passes:
            self._fetch_models(job, settings.battybird.head)
        analyser = self._analyser_for(settings)
        with self._library() as library:
            repo = library.repository
            todo = repo.recordings_without_result()
            if job.params.get("scope") == "stale":
                stale = set(repo.results_from_other_versions(analyser.versions))
                todo += [r for i in sorted(stale) if (r := repo.recording(i)) is not None]
            regions: dict[int | None, Region] = {}
            sites = {s.id: s for s in repo.sites()}
            report = self._progress(job, Phase.ANALYSING)
            failed = 0
            for done, recording in enumerate(todo):
                report(done, len(todo), recording.file_name)
                if recording.site_id not in regions:
                    site = sites.get(recording.site_id) if recording.site_id else None
                    regions[recording.site_id] = (
                        repo.region_of(site) if site else profile_for(None, None).region
                    )
                try:
                    result = analyser.analyse(
                        library.path_of(recording.path), regions[recording.site_id]
                    )
                    repo.save_result(recording.id, result)
                except Exception:
                    log.exception("could not analyse %s", recording.path)
                    failed += 1
            report(len(todo), len(todo), "")
        return {"analysed": len(todo) - failed, "failed": failed}

    def _models(self, job: Job) -> dict[str, Any]:
        self._fetch_models(job, self._pipeline_settings().battybird.head)
        return {"directory": str(self.env.models_dir)}

    def _fetch_models(self, job: Job, head: str) -> None:
        progress = self._progress(job, Phase.MODELS)
        # The download reports (file, bytes done, bytes total).
        self.env.ensure_models(
            self.env.models_dir, head, lambda name, done, total: progress(done, total, name)
        )

    def _pipeline_settings(self) -> pipeline.Settings:
        s = self.env.settings()
        return pipeline.Settings(
            passes=frozenset(Pass(p) for p in s.passes),
            sieve=s.sieve,
            device=None if s.device == "auto" else s.device,
        )

    def _analyser_for(self, settings: pipeline.Settings) -> Analyser:
        """The analyser for these settings; the same one while they do not change."""
        if self._analyser is None or self._analyser[0] != settings:
            self._analyser = (settings, self.env.make_analyser(self.env.models_dir, settings))
        return self._analyser[1]


def report_to_dict(r: ImportReport) -> dict[str, Any]:
    return {
        "import_id": r.import_id,
        "copied": r.copied,
        "skipped": {str(k): v for k, v in r.skipped.items()},
        "new_configs": r.new_configs,
        "findings": [{"problem": str(f.problem), "file": f.path.name} for f in r.findings],
        "issues": [
            {
                "issue": str(i.issue),
                "details": list(i.details),
                "written_at": i.config.written_at.isoformat(),
            }
            for i in r.issues
        ],
        "notices": [
            {
                "notice": str(n.notice),
                "count": n.count,
                "example": n.example.name,
                "location": {"latitude": n.location.latitude, "longitude": n.location.longitude}
                if n.location
                else None,
            }
            for n in r.notices
        ],
    }
