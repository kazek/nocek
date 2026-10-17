"""The web application: API, security, background jobs, and the interface's files."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from nyctalus import __version__
from nyctalus.storage import settings as app_settings
from nyctalus.web import api, jobs_api, library_api, media_api
from nyctalus.web.errors import ApiError, handle_api_error
from nyctalus.web.jobs import Environment, JobRunner
from nyctalus.web.security import COOKIE, Guard
from nyctalus.web.state import AppState

STATIC = Path(__file__).parent / "static"


def create_app(state: AppState, runner: JobRunner | None = None) -> FastAPI:
    runner = runner or JobRunner(
        Environment(
            library_root=lambda: state.library.root if state.library else None,
            settings=lambda: state.settings,
            models_dir=app_settings.models_dir(),
        )
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        runner.start()
        try:
            yield
        finally:
            runner.stop()

    app = FastAPI(
        title="Nyctalus", version=__version__, docs_url=None, redoc_url=None, lifespan=lifespan
    )
    app.state.nyctalus = state
    app.state.jobs = runner
    app.add_middleware(Guard, token=state.token, port=state.port)
    app.add_exception_handler(ApiError, handle_api_error)
    app.include_router(api.router)
    app.include_router(jobs_api.router)
    app.include_router(library_api.router)
    app.include_router(media_api.router)

    @app.get("/", include_in_schema=False)
    def index(request: Request, token: str | None = None) -> Response:
        if token is not None:
            # The address the application opened: keep the token, then show a
            # clean address that can be bookmarked.
            response: Response = RedirectResponse("/", status_code=303)
            if token == state.token:
                response.set_cookie(
                    COOKIE,
                    token,
                    httponly=True,
                    samesite="strict",
                    max_age=10 * 365 * 24 * 3600,
                )
            return response
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
