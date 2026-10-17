"""The API over the library's contents: what was recorded, where, by what, and what it was."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from nocek.core import region as regions
from nocek.core import taxonomy
from nocek.core.region import Status
from nocek.core.taxonomy import Taxon
from nocek.recorders import sun
from nocek.recorders.base import Config
from nocek.recorders.checks import check
from nocek.recorders.registry import RECORDERS
from nocek.storage import summaries
from nocek.storage.library import Library
from nocek.storage.repository import Site
from nocek.storage.serialize import result_to_dict
from nocek.storage.summaries import Filter
from nocek.web.errors import ApiError
from nocek.web.jobs import Kind
from nocek.web.state import AppState

router = APIRouter(prefix="/api")


def rejudge(request: Request, site_id: int | None) -> None:
    """Have the stored opinions combined again for a site's recordings."""
    request.app.state.jobs.submit(Kind.VERDICTS, site_id=site_id)


@contextmanager
def opened(request: Request) -> Iterator[Library]:
    state: AppState = request.app.state.nocek
    with state.using() as library:
        if library is None:
            raise ApiError(409, "no-library")
        yield library


class SiteBody(BaseModel):
    name: str
    latitude: float | None = None
    longitude: float | None = None


class StatusBody(BaseModel):
    species: str
    # None returns the species to the region's status.
    status: Status | None


class AssignBody(BaseModel):
    site_id: int
    # Only the recordings with this number; None: all the import's without a site.
    device_number: int | None = None


class NumberBody(BaseModel):
    device_id: int
    device_number: int
    site_id: int | None  # None: the number stands for no site


class LabelBody(BaseModel):
    label: str | None


# --- Reference ---------------------------------------------------------------


@router.get("/taxa")
def get_taxa() -> dict[str, list[str]]:
    return {
        "species": [t.name for t in taxonomy.species()],
        "genera": [t.name for t in taxonomy.genera()],
    }


@router.get("/profiles")
def get_profiles() -> list[dict[str, Any]]:
    return [
        {
            "id": p.id,
            "name": p.region.name,
            "bounds": vars(p.bounds) if p.bounds else None,
            "default": str(p.region.default),
            "statuses": {t.name: str(s) for t, s in p.region.statuses.items()},
        }
        for p in regions.profiles()
    ]


# --- Sites -------------------------------------------------------------------


@router.get("/sites")
def get_sites(request: Request) -> list[dict[str, Any]]:
    with opened(request) as library:
        return [_site(library, s) for s in library.repository.sites()]


@router.get("/numbers")
def get_numbers(request: Request) -> dict[str, Any]:
    """Every number a recorder was set to, the site it stands for, and how many
    recordings it brought; and how many recordings have no site at all.
    """
    with opened(request) as library:
        counts = summaries.number_use(library.conn)
        numbers = library.repository.site_numbers()
        without = summaries.site_use(library.conn).get(None)
    return {
        "numbers": [
            {
                "device_id": n.device_id,
                "device_number": n.device_number,
                "site_id": n.site_id,
                "recordings": counts.get((n.device_id, n.device_number), 0),
            }
            for n in numbers
        ],
        "without_site": without.recordings if without else 0,
    }


@router.put("/numbers")
def set_number(request: Request, body: NumberBody) -> dict[str, int]:
    """Let a recorder's number stand for a site, or for none; its recordings move along."""
    with opened(request) as library:
        if body.site_id is not None and library.repository.site(body.site_id) is None:
            raise ApiError(404, "no-such-site", str(body.site_id))
        moved = library.repository.set_site_number(body.device_id, body.device_number, body.site_id)
    # The site picks the region, and so what may be named in what moved.
    if moved:
        rejudge(request, None)
    return {"moved": moved}


@router.post("/sites")
def add_site(request: Request, body: SiteBody) -> dict[str, Any]:
    with opened(request) as library:
        try:
            site = library.repository.add_site(body.name, body.latitude, body.longitude)
        except sqlite3.IntegrityError as error:
            raise ApiError(409, "site-exists", body.name) from error
        return _site(library, site)


@router.put("/sites/{site_id}")
def update_site(request: Request, site_id: int, body: SiteBody) -> dict[str, Any]:
    with opened(request) as library:
        before = library.repository.site(site_id)
        try:
            site = library.repository.update_site(site_id, body.name, body.latitude, body.longitude)
        except sqlite3.IntegrityError as error:
            raise ApiError(409, "site-exists", body.name) from error
        if site is None or before is None:
            raise ApiError(404, "no-such-site", str(site_id))
        moved = (before.latitude, before.longitude) != (site.latitude, site.longitude)
        answer = _site(library, site)
    # The position picks the region, and so what may be named there.
    if moved:
        rejudge(request, site_id)
    return answer


@router.put("/sites/{site_id}/species")
def set_status(request: Request, site_id: int, body: StatusBody) -> dict[str, Any]:
    try:
        species = taxonomy.get(body.species)
    except taxonomy.UnknownTaxonError as error:
        raise ApiError(422, "unknown-species", body.species) from error
    if species.rank is not taxonomy.Rank.SPECIES:
        raise ApiError(422, "not-a-species", body.species)
    with opened(request) as library:
        site = library.repository.site(site_id)
        if site is None:
            raise ApiError(404, "no-such-site", str(site_id))
        library.repository.set_species_status(site_id, species, body.status)
        answer = _site(library, site)
    rejudge(request, site_id)
    return answer


def _site(library: Library, site: Site) -> dict[str, Any]:
    profile = regions.profile_for(site.latitude, site.longitude)
    use = summaries.site_use(library.conn).get(site.id)
    return {
        "id": site.id,
        "name": site.name,
        "latitude": site.latitude,
        "longitude": site.longitude,
        "recordings": use.recordings if use else 0,
        "first_night": _iso(use.first_night) if use else None,
        "last_night": _iso(use.last_night) if use else None,
        "numbers": [
            {"device_id": n.device_id, "device_number": n.device_number}
            for n in library.repository.site_numbers()
            if n.site_id == site.id
        ],
        "profile": profile.id,
        "statuses": {
            t.name: str(s) for t, s in library.repository.species_statuses(site.id).items()
        },
    }


# --- Imports and devices -----------------------------------------------------


@router.get("/imports")
def get_imports(request: Request) -> list[dict[str, Any]]:
    with opened(request) as library:
        return [vars(i) for i in library.repository.imports()]


@router.post("/imports/{import_id}/site")
def assign_site(request: Request, import_id: int, body: AssignBody) -> dict[str, int]:
    with opened(request) as library:
        if library.repository.site(body.site_id) is None:
            raise ApiError(404, "no-such-site", str(body.site_id))
        assigned = library.repository.assign_site(import_id, body.site_id, body.device_number)
    if assigned:
        rejudge(request, body.site_id)
    return {"assigned": assigned}


@router.get("/devices")
def get_devices(request: Request) -> list[dict[str, Any]]:
    with opened(request) as library:
        repo = library.repository
        use = summaries.device_use(library.conn)
        out = []
        for d in repo.all_devices():
            recorder = RECORDERS.get(d.kind)
            configs = (
                tuple(recorder.parse_config(raw) for raw in repo.configs_of(d.id))
                if recorder
                else ()
            )
            issues: dict[int, list[dict[str, Any]]] = {}
            for i in check(configs):
                issues.setdefault(id(i.config), []).append(
                    {"issue": str(i.issue), "details": list(i.details)}
                )
            out.append(
                {
                    "id": d.id,
                    "kind": d.kind,
                    "uid": d.uid,
                    "label": d.label,
                    "recordings": use[d.id].recordings if d.id in use else 0,
                    "first_night": _iso(use[d.id].first_night) if d.id in use else None,
                    "last_night": _iso(use[d.id].last_night) if d.id in use else None,
                    "last_site_id": use[d.id].last_site_id if d.id in use else None,
                    "configs": [_config(c, issues.get(id(c), [])) for c in configs],
                }
            )
        return out


@router.put("/devices/{device_id}")
def set_label(request: Request, device_id: int, body: LabelBody) -> dict[str, Any]:
    with opened(request) as library:
        library.repository.set_device_label(device_id, body.label or None)
    devices = get_devices(request)
    found = next((d for d in devices if d["id"] == device_id), None)
    if found is None:
        raise ApiError(404, "no-such-device", str(device_id))
    return found


def _config(c: Config, issues: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "written_at": c.written_at.isoformat(),
        "number": c.device_number,
        "firmware": c.firmware,
        "trigger_sensitivity": c.trigger_sensitivity,
        "location": vars(c.location) if c.location else None,
        "schedules": [
            {"wake": s.wake.strftime("%H:%M"), "sleep": s.sleep.strftime("%H:%M"), "mode": s.mode}
            for s in c.schedules
        ],
        "issues": issues,
    }


# --- Recordings and totals ---------------------------------------------------


def _filter(
    site_id: int | None,
    device_id: int | None,
    first_night: date | None,
    last_night: date | None,
    without_site: bool = False,
) -> Filter:
    return Filter(
        site_id=site_id,
        device_id=device_id,
        first_night=first_night,
        last_night=last_night,
        without_site=without_site,
    )


@router.get("/recordings")
def get_recordings(
    request: Request,
    site_id: int | None = None,
    device_id: int | None = None,
    first_night: date | None = None,
    last_night: date | None = None,
    without_site: bool = False,
    taxa: str | None = None,
    with_calls: bool = False,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """taxa: the scientific names of one named animal, separated by commas."""
    wanted = frozenset(Taxon(n.strip()) for n in taxa.split(",")) if taxa else None
    with opened(request) as library:
        page = summaries.recordings(
            library.conn,
            _filter(site_id, device_id, first_night, last_night, without_site),
            taxa=wanted,
            with_calls=with_calls,
            offset=max(0, offset),
            limit=min(max(1, limit), 1000),
        )
    return {
        "total": page.total,
        "rows": [
            {
                "id": r.id,
                "file_name": r.file_name,
                "recorded_at": r.recorded_at,
                "night": r.night.isoformat() if r.night else None,
                "site_id": r.site_id,
                "device_id": r.device_id,
                "duration_s": r.duration_s,
                "analysed": r.analysed,
                "sources": r.sources,
                "named": [_names(t) for t in r.named],
            }
            for r in page.rows
        ],
    }


@router.get("/recordings/{recording_id}")
def get_recording(request: Request, recording_id: int) -> dict[str, Any]:
    with opened(request) as library:
        recording = library.repository.recording(recording_id)
        if recording is None:
            raise ApiError(404, "no-such-recording", str(recording_id))
        result = library.repository.result(recording_id)
    return {
        "id": recording.id,
        "file_name": recording.file_name,
        "path": str(recording.path),
        "recorded_at": recording.recorded_at.isoformat() if recording.recorded_at else None,
        "night": recording.night.isoformat() if recording.night else None,
        "duration_s": recording.duration_s,
        "sample_rate": recording.sample_rate,
        "site_id": recording.site_id,
        "device_id": recording.device_id,
        "result": result_to_dict(result) if result else None,
    }


@router.delete("/recordings/{recording_id}")
def delete_recording(request: Request, recording_id: int) -> dict[str, bool]:
    with opened(request) as library:
        if library.repository.recording(recording_id) is None:
            raise ApiError(404, "no-such-recording", str(recording_id))
        library.delete_recording(recording_id)
    return {"deleted": True}


@router.get("/totals")
def get_totals(
    request: Request,
    site_id: int | None = None,
    device_id: int | None = None,
    first_night: date | None = None,
    last_night: date | None = None,
    without_site: bool = False,
) -> dict[str, Any]:
    with opened(request) as library:
        t = summaries.totals(
            library.conn, _filter(site_id, device_id, first_night, last_night, without_site)
        )
    return {
        "recordings": t.recordings,
        "analysed": t.analysed,
        "with_calls": t.with_calls,
        "nights": t.nights,
        "species": [
            {
                "taxa": _names(s.taxa),
                "recordings": s.recordings,
                "nights": s.nights,
                "first_night": s.first_night.isoformat(),
                "last_night": s.last_night.isoformat(),
                "best_score": s.best_score,
            }
            for s in t.species
        ],
    }


@router.get("/nights")
def get_nights(
    request: Request,
    site_id: int | None = None,
    device_id: int | None = None,
    first_night: date | None = None,
    last_night: date | None = None,
    without_site: bool = False,
) -> list[dict[str, Any]]:
    with opened(request) as library:
        found = summaries.nights(
            library.conn, _filter(site_id, device_id, first_night, last_night, without_site)
        )
    return [
        {
            "night": n.night.isoformat(),
            "recordings": n.recordings,
            "with_calls": n.with_calls,
            "named": n.named,
        }
        for n in found
    ]


def _iso(day: date | None) -> str | None:
    return day.isoformat() if day else None


def _names(taxa: frozenset[Taxon]) -> list[str]:
    return sorted(t.name for t in taxa)


@router.get("/sun")
def get_sun(request: Request, night: date, site_id: int) -> dict[str, str | None]:
    """When the sun set and rose around a night at a site, in local time."""
    with opened(request) as library:
        site = library.repository.site(site_id)
    if site is None:
        raise ApiError(404, "no-such-site", str(site_id))
    if site.latitude is None or site.longitude is None:
        return {"sunset": None, "sunrise": None}
    dusk, dawn = sun.local_night(night, site.latitude, site.longitude)
    return {
        "sunset": dusk.isoformat(timespec="minutes") if dusk else None,
        "sunrise": dawn.isoformat(timespec="minutes") if dawn else None,
    }
