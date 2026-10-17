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
