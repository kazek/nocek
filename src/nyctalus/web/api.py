"""The API: settings, the library, and browsing folders."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from nyctalus import __version__
from nyctalus.storage import settings as app_settings
from nyctalus.storage.library import Library, LibraryError
from nyctalus.storage.settings import SettingsError
from nyctalus.web import folders, i18n
from nyctalus.web.errors import ApiError
from nyctalus.web.state import AppState

router = APIRouter(prefix="/api")


def state(request: Request) -> AppState:
    s: AppState = request.app.state.nyctalus
    return s


class SettingsChange(BaseModel):
    language: str | None = None
    follow_browser_language: bool = False
    passes: list[str] | None = None
    sieve: bool | None = None
    device: str | None = None


class PathBody(BaseModel):
    path: str


@router.get("/health")
def health() -> dict[str, str]:
    return {"version": __version__}


@router.get("/settings")
def get_settings(request: Request) -> dict[str, Any]:
    return _settings(state(request).settings)


@router.put("/settings")
def put_settings(request: Request, change: SettingsChange) -> dict[str, Any]:
    s = state(request)
    current = s.settings
    language = None if change.follow_browser_language else (change.language or current.language)
    try:
        updated = replace(
            current,
            language=language,
            passes=tuple(change.passes) if change.passes is not None else current.passes,
            sieve=change.sieve if change.sieve is not None else current.sieve,
            device=change.device or current.device,
        )
    except SettingsError as error:
        raise ApiError(422, "invalid-setting", str(error)) from error
    s.update(updated)
    return _settings(updated)


@router.get("/library")
def get_library(request: Request) -> dict[str, Any]:
    s = state(request)
    with s.using() as library:
        return {
            "open": library is not None,
            "path": str(library.root) if library else None,
            "error": s.library_error,
            "default_path": str(app_settings.default_library()),
        }


@router.post("/library/create")
def create_library(request: Request, body: PathBody) -> dict[str, Any]:
    return _switch(request, body.path, Library.create)


@router.post("/library/open")
def open_library(request: Request, body: PathBody) -> dict[str, Any]:
    return _switch(request, body.path, Library.open)


@router.get("/folders")
def get_folders(path: str | None = None, deep: bool = False) -> dict[str, Any]:
    if path is None:
        return {"path": None, "parent": None, "recordings": 0, "folders": _folders(folders.roots())}
    try:
        found = folders.listing(Path(path), deep=deep)
    except NotADirectoryError as error:
        raise ApiError(404, "not-a-folder", str(error)) from error
    except PermissionError as error:
        raise ApiError(403, "folder-not-readable", str(error)) from error
    return {
        "path": str(found.path),
        "parent": str(found.parent) if found.parent else None,
        "recordings": found.recordings,
        "folders": _folders(found.folders),
    }


def _switch(request: Request, path: str, how: Any) -> dict[str, Any]:
    root = Path(path)
    if not root.is_absolute():
        raise ApiError(422, "not-an-absolute-path", path)
    try:
        library = how(root, shared=True)
    except LibraryError as error:
        raise ApiError(409, "library-unavailable", str(error)) from error
    except OSError as error:
        raise ApiError(409, "folder-not-writable", str(error)) from error
    state(request).switch_library(library)
    return get_library(request)


def _settings(s: app_settings.Settings) -> dict[str, Any]:
    return {
        "library": str(s.library) if s.library else None,
        "language": s.language,
        "passes": list(s.passes),
        "sieve": s.sieve,
        "device": s.device,
    }


def _folders(found: Any) -> list[dict[str, Any]]:
    return [{"name": f.name, "path": str(f.path), "recordings": f.recordings} for f in found]


@router.get("/locales")
def get_locales(request: Request) -> dict[str, Any]:
    """The languages available, and the one to show this browser."""
    chosen = i18n.choose(state(request).settings.language, request.headers.get("accept-language"))
    return {"available": i18n.names(), "chosen": chosen}


@router.get("/locales/{language}")
def get_locale(language: str) -> dict[str, Any]:
    try:
        return i18n.texts(language)
    except KeyError as error:
        raise ApiError(404, "no-such-language", language) from error
