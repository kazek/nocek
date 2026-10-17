"""The API for background jobs and the model files they need."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from nocek.core import battybird
from nocek.web.errors import ApiError
from nocek.web.jobs import JobRunner, Kind

router = APIRouter(prefix="/api")


def runner(request: Request) -> JobRunner:
    r: JobRunner = request.app.state.jobs
    return r


class ImportBody(BaseModel):
    folder: str
    site_id: int | None = None


class AnalyseBody(BaseModel):
    # new: recordings never analysed; stale: also those analysed by older models.
    scope: Literal["new", "stale"] = "new"


@router.get("/jobs")
def list_jobs(request: Request) -> list[dict[str, Any]]:
    return runner(request).jobs()


@router.get("/jobs/{job_id}")
def get_job(request: Request, job_id: int) -> dict[str, Any]:
    job = runner(request).get(job_id)
    if job is None:
        raise ApiError(404, "no-such-job", str(job_id))
    return job


@router.post("/jobs/import")
def start_import(request: Request, body: ImportBody) -> dict[str, Any]:
    return runner(request).submit(Kind.IMPORT, folder=body.folder, site_id=body.site_id)


@router.post("/jobs/analyse")
def start_analysis(request: Request, body: AnalyseBody) -> dict[str, Any]:
    return runner(request).submit(Kind.ANALYSE, scope=body.scope)


@router.post("/jobs/models")
def start_download(request: Request) -> dict[str, Any]:
    return runner(request).submit(Kind.MODELS)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(request: Request, job_id: int) -> dict[str, Any]:
    if not runner(request).cancel(job_id):
        raise ApiError(409, "job-not-running", str(job_id))
    return get_job(request, job_id)


@router.get("/models")
def get_models(request: Request) -> dict[str, Any]:
    directory = runner(request).env.models_dir
    files = battybird.files_for(battybird.DEFAULT_PARAMS.head)
    missing = [f.name for f in files if not (directory / f.name).is_file()]
    return {"directory": str(directory), "present": not missing, "missing": missing}
