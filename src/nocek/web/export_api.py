"""Downloading what the library holds as CSV, for spreadsheets and other tools."""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from nocek.storage import summaries
from nocek.storage.summaries import Filter
from nocek.web import i18n
from nocek.web.library_api import opened
from nocek.web.state import AppState

router = APIRouter(prefix="/api/export")


@router.get("/species.csv")
def species_csv(
    request: Request,
    site_id: int | None = None,
    device_id: int | None = None,
    first_night: date | None = None,
    last_night: date | None = None,
) -> Response:
    names = _names(request)
    with opened(request) as library:
        totals = summaries.totals(library.conn, Filter(site_id, device_id, first_night, last_night))
    return _csv(
        "nocek-species.csv",
        [
            "scientific_name",
            "name",
            "recordings",
            "nights",
            "first_night",
            "last_night",
            "best_score",
        ],
        [
            [
                _scientific(sorted(t.name for t in s.taxa)),
                names(sorted(t.name for t in s.taxa)),
                s.recordings,
                s.nights,
                s.first_night.isoformat(),
                s.last_night.isoformat(),
                round(s.best_score, 3),
            ]
            for s in totals.species
        ],
    )


@router.get("/recordings.csv")
def recordings_csv(
    request: Request,
    site_id: int | None = None,
    device_id: int | None = None,
    first_night: date | None = None,
    last_night: date | None = None,
) -> Response:
    names = _names(request)
    with opened(request) as library:
        rows = summaries.verdict_rows(
            library.conn, Filter(site_id, device_id, first_night, last_night)
        )
    return _csv(
        "nocek-recordings.csv",
        [
            "file",
            "recorded_at",
            "night",
            "site",
            "recorder",
            "status",
            "scientific_name",
            "name",
            "model_class",
            "reasons",
            "agreeing",
            "named_by",
            "best_score",
            "calls",
        ],
        [
            [
                r.file_name,
                r.recorded_at,
                r.night,
                r.site,
                r.device,
                _status(r),
                _scientific(list(r.taxa)) if r.taxa else "",
                names(list(r.taxa)) if r.taxa else "",
                r.model_class,
                " ".join(r.reasons),
                r.agreeing,
                r.named,
                round(r.best_score, 3) if r.best_score is not None else None,
                r.n_calls,
            ]
            for r in rows
        ],
    )


def _status(r: summaries.VerdictRow) -> str:
    if not r.analysed:
        return "not-analysed"
    if r.model_class is None:
        return "no-calls"
    return "named" if r.taxa else "withheld"


def _scientific(taxa: list[str]) -> str:
    return " / ".join(t if " " in t else f"{t} sp." for t in taxa)


def _names(request: Request) -> Any:
    """Local names in the interface's language."""
    state: AppState = request.app.state.nocek
    language = i18n.choose(state.settings.language, request.headers.get("accept-language"))
    texts = i18n.texts(language)

    def local(taxa: list[str]) -> str:
        return " / ".join(
            texts["species"].get(t, t) if " " in t else texts["genus"].get(t, t) for t in taxa
        )

    return local


def _csv(filename: str, header: list[str], rows: list[list[Any]]) -> Response:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerows(rows)
    # A byte-order mark, so spreadsheet programs read the names as UTF-8.
    return Response(
        "﻿" + out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
