"""The web application: API, security, and the interface's static files."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from nyctalus import __version__
from nyctalus.web import api
from nyctalus.web.errors import ApiError, handle_api_error
from nyctalus.web.security import COOKIE, Guard
from nyctalus.web.state import AppState

STATIC = Path(__file__).parent / "static"


def create_app(state: AppState) -> FastAPI:
    app = FastAPI(title="Nyctalus", version=__version__, docs_url=None, redoc_url=None)
    app.state.nyctalus = state
    app.add_middleware(Guard, token=state.token, port=state.port)
    app.add_exception_handler(ApiError, handle_api_error)
    app.include_router(api.router)

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
