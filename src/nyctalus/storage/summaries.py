"""Which bats have been recorded, how often, and over how many nights.

Counts are of recordings, not calls: a bat crossing the microphone leaves
anything from one call to two hundred depending on how long it stayed, so
counting calls measures how obliging the bat was. Every named animal in a
recording counts once, so a recording with a noctule and a pipistrelle is
one appearance of each. A withheld name leaves the recording counted as one
with calls, but not as any species.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Any

from nyctalus.core.taxonomy import Taxon


@dataclass(frozen=True)
class Filter:
    site_id: int | None = None
    device_id: int | None = None
    first_night: date | None = None
    last_night: date | None = None


@dataclass(frozen=True)
class SpeciesTotal:
    taxa: frozenset[Taxon]
    recordings: int
    nights: int
    first_night: date
    last_night: date
    # The best class probability the model ever gave this animal. A species
    # met often whose best is still mediocre is probably something else being
    # mistaken for it, over and over.
    best_score: float


@dataclass(frozen=True)
class Totals:
    species: tuple[SpeciesTotal, ...]
    recordings: int
    analysed: int
    with_calls: int
    nights: int


@dataclass(frozen=True)
class NightActivity:
    night: date
    recordings: int
    with_calls: int
    named: int  # recordings with at least one named animal


@dataclass(frozen=True)
class RecordingRow:
    """One line of the recordings list: what is needed without opening the result."""

    id: int
    file_name: str
    recorded_at: str | None
    night: date | None
    site_id: int | None
    device_id: int | None
    duration_s: float | None
    analysed: bool
    sources: int
    named: tuple[frozenset[Taxon], ...]


@dataclass(frozen=True)
class Page:
    rows: tuple[RecordingRow, ...]
    total: int  # rows matching, across all pages


def recordings(
    conn: sqlite3.Connection,
    where: Filter | None = None,
    taxa: frozenset[Taxon] | None = None,
    with_calls: bool = False,
    offset: int = 0,
    limit: int = 100,
) -> Page:
    """Recordings in time order. taxa keeps those naming exactly that animal."""
    condition, params = _condition(where or Filter())
    if taxa is not None:
        condition += (
            " AND EXISTS (SELECT 1 FROM source_verdict v"
            " WHERE v.recording_id = r.id AND v.taxa = ?)"
        )
        params.append(json.dumps(sorted(t.name for t in taxa)))
    if with_calls:
        condition += " AND EXISTS (SELECT 1 FROM source_verdict v WHERE v.recording_id = r.id)"
    total = conn.execute(f"SELECT COUNT(*) FROM recording r WHERE {condition}", params).fetchone()[
        0
    ]
    rows = conn.execute(
        "SELECT r.*,"
        " EXISTS (SELECT 1 FROM result WHERE recording_id = r.id) AS analysed,"
        " (SELECT COUNT(*) FROM source_verdict v WHERE v.recording_id = r.id) AS sources,"
        " (SELECT json_group_array(v.taxa) FROM source_verdict v"
        "  WHERE v.recording_id = r.id AND v.taxa IS NOT NULL) AS named"
        f" FROM recording r WHERE {condition}"
        " ORDER BY r.recorded_at, r.id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return Page(rows=tuple(_recording_row(r) for r in rows), total=total)


def nights(conn: sqlite3.Connection, where: Filter | None = None) -> list[NightActivity]:
    condition, params = _condition(where or Filter())
    rows = conn.execute(
        "SELECT r.night, COUNT(*) AS recordings,"
        " SUM(EXISTS (SELECT 1 FROM source_verdict v WHERE v.recording_id = r.id)) AS with_calls,"
        " SUM(EXISTS (SELECT 1 FROM source_verdict v"
        "  WHERE v.recording_id = r.id AND v.taxa IS NOT NULL)) AS named"
        f" FROM recording r WHERE r.night IS NOT NULL AND {condition}"
        " GROUP BY r.night ORDER BY r.night",
        params,
    ).fetchall()
    return [
        NightActivity(date.fromisoformat(r["night"]), r["recordings"], r["with_calls"], r["named"])
        for r in rows
    ]


def totals(conn: sqlite3.Connection, where: Filter | None = None) -> Totals:
    condition, params = _condition(where or Filter())
    species = conn.execute(
        "SELECT v.taxa, COUNT(DISTINCT r.id) AS recordings, COUNT(DISTINCT r.night) AS nights,"
        " MIN(r.night) AS first_night, MAX(r.night) AS last_night,"
        " MAX(v.best_score) AS best_score"
        " FROM source_verdict v JOIN recording r ON r.id = v.recording_id"
        f" WHERE v.taxa IS NOT NULL AND {condition}"
        " GROUP BY v.taxa ORDER BY recordings DESC, v.taxa",
        params,
    ).fetchall()
    overall = conn.execute(
        "SELECT COUNT(*) AS recordings, COUNT(DISTINCT r.night) AS nights,"
        " SUM(EXISTS (SELECT 1 FROM result WHERE recording_id = r.id)) AS analysed,"
        " SUM(EXISTS (SELECT 1 FROM source_verdict WHERE recording_id = r.id)) AS with_calls"
        f" FROM recording r WHERE {condition}",
        params,
    ).fetchone()
    return Totals(
        species=tuple(_species_total(row) for row in species),
        recordings=overall["recordings"],
        analysed=overall["analysed"] or 0,
        with_calls=overall["with_calls"] or 0,
        nights=overall["nights"],
    )


def _condition(f: Filter) -> tuple[str, list[Any]]:
    clauses: list[str] = ["1 = 1"]
    params: list[Any] = []
    if f.site_id is not None:
        clauses.append("r.site_id = ?")
        params.append(f.site_id)
    if f.device_id is not None:
        clauses.append("r.device_id = ?")
        params.append(f.device_id)
    if f.first_night is not None:
        clauses.append("r.night >= ?")
        params.append(f.first_night.isoformat())
    if f.last_night is not None:
        clauses.append("r.night <= ?")
        params.append(f.last_night.isoformat())
    return " AND ".join(clauses), params


def _species_total(row: sqlite3.Row) -> SpeciesTotal:
    return SpeciesTotal(
        taxa=frozenset(Taxon(n) for n in json.loads(row["taxa"])),
        recordings=row["recordings"],
        nights=row["nights"],
        first_night=date.fromisoformat(row["first_night"]),
        last_night=date.fromisoformat(row["last_night"]),
        best_score=row["best_score"],
    )


def _recording_row(r: sqlite3.Row) -> RecordingRow:
    return RecordingRow(
        id=r["id"],
        file_name=r["file_name"],
        recorded_at=r["recorded_at"],
        night=date.fromisoformat(r["night"]) if r["night"] else None,
        site_id=r["site_id"],
        device_id=r["device_id"],
        duration_s=r["duration_s"],
        analysed=bool(r["analysed"]),
        sources=r["sources"],
        named=tuple(
            frozenset(Taxon(n) for n in json.loads(taxa)) for taxa in json.loads(r["named"])
        ),
    )


@dataclass(frozen=True)
class VerdictRow:
    """One animal in one recording, or the recording alone when it has none."""

    file_name: str
    recorded_at: str | None
    night: str | None
    site: str | None
    device: str | None
    analysed: bool
    model_class: str | None
    taxa: tuple[str, ...] | None
    reasons: tuple[str, ...]
    agreeing: int | None
    named: int | None
    best_score: float | None
    n_calls: int | None


def verdict_rows(conn: sqlite3.Connection, where: Filter | None = None) -> list[VerdictRow]:
    condition, params = _condition(where or Filter())
    rows = conn.execute(
        "SELECT r.file_name, r.recorded_at, r.night, s.name AS site,"
        " COALESCE(d.label, d.uid) AS device,"
        " EXISTS (SELECT 1 FROM result WHERE recording_id = r.id) AS analysed,"
        " v.model_class, v.taxa, v.reasons, v.agreeing, v.named, v.best_score, v.n_calls"
        " FROM recording r"
        " LEFT JOIN site s ON s.id = r.site_id"
        " LEFT JOIN device d ON d.id = r.device_id"
        " LEFT JOIN source_verdict v ON v.recording_id = r.id"
        f" WHERE {condition}"
        " ORDER BY r.recorded_at, r.id, v.position",
        params,
    ).fetchall()
    return [
        VerdictRow(
            file_name=r["file_name"],
            recorded_at=r["recorded_at"],
            night=r["night"],
            site=r["site"],
            device=r["device"],
            analysed=bool(r["analysed"]),
            model_class=r["model_class"],
            taxa=tuple(json.loads(r["taxa"])) if r["taxa"] else None,
            reasons=tuple(json.loads(r["reasons"])) if r["reasons"] else (),
            agreeing=r["agreeing"],
            named=r["named"],
            best_score=r["best_score"],
            n_calls=r["n_calls"],
        )
        for r in rows
    ]
