"""Reading and writing the library's records.

Plain SQL over sqlite3, one method per thing the application needs. Every
write is its own transaction unless the caller groups several in
`transaction()`.
"""

from __future__ import annotations

import json
import sqlite3
import zlib
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import PurePosixPath

from nocek.core import region as regions
from nocek.core.nights import night_of
from nocek.core.pipeline import RecordingResult
from nocek.core.region import Region, Status
from nocek.core.taxonomy import Taxon
from nocek.storage.serialize import result_from_dict, result_to_dict


@dataclass(frozen=True)
class Site:
    id: int
    name: str
    latitude: float | None
    longitude: float | None


@dataclass(frozen=True)
class Device:
    id: int
    kind: str
    uid: str
    label: str | None


@dataclass(frozen=True)
class Import:
    id: int
    source: str
    started_at: str
    finished_at: str | None
    copied: int
    skipped: int
    without_site: int


@dataclass(frozen=True)
class Recording:
    id: int
    sha256: str
    path: PurePosixPath  # inside the library
    file_name: str
    size_bytes: int
    recorded_at: datetime | None
    night: date | None
    duration_s: float | None
    sample_rate: int | None
    device_id: int | None
    site_id: int | None
    import_id: int | None
    device_number: int | None = None  # the number the recorder was set to


@dataclass(frozen=True)
class SiteNumber:
    """One of a recorder's numbers, and the site it stands for."""

    device_id: int
    device_number: int
    site_id: int | None  # None: recordings with this number, but no site for it yet


class Repository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._depth = 0

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group several writes so they are kept together or not at all."""
        if self._depth == 0:
            self.conn.execute("BEGIN")
        self._depth += 1
        try:
            yield
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self.conn.rollback()
            raise
        self._depth -= 1
        if self._depth == 0:
            self.conn.commit()

    # --- Sites -----------------------------------------------------------

    def add_site(
        self, name: str, latitude: float | None = None, longitude: float | None = None
    ) -> Site:
        with self.transaction():
            cur = self.conn.execute(
                "INSERT INTO site (name, latitude, longitude, created_at) VALUES (?, ?, ?, ?)",
                (name, latitude, longitude, _now()),
            )
        return Site(_id(cur), name, latitude, longitude)

    def sites(self) -> list[Site]:
        rows = self.conn.execute("SELECT * FROM site ORDER BY name")
        return [Site(r["id"], r["name"], r["latitude"], r["longitude"]) for r in rows]

    def site(self, site_id: int) -> Site | None:
        r = self.conn.execute("SELECT * FROM site WHERE id = ?", (site_id,)).fetchone()
        return Site(r["id"], r["name"], r["latitude"], r["longitude"]) if r else None

    def update_site(
        self, site_id: int, name: str, latitude: float | None, longitude: float | None
    ) -> Site | None:
        with self.transaction():
            self.conn.execute(
                "UPDATE site SET name = ?, latitude = ?, longitude = ? WHERE id = ?",
                (name, latitude, longitude, site_id),
            )
        return self.site(site_id)

    def species_statuses(self, site_id: int) -> dict[Taxon, Status]:
        """The statuses a site sets itself, over its region's."""
        rows = self.conn.execute(
            "SELECT species, status FROM site_species_status WHERE site_id = ? ORDER BY species",
            (site_id,),
        )
        return {Taxon(r["species"]): Status(r["status"]) for r in rows}

    def assign_site(self, import_id: int, site_id: int, device_number: int | None = None) -> int:
        """Give an import's recordings that have no site this one: all of them, or those
        with one number. Their numbers then stand for the site, so every recording with
        them moves too. Returns how many recordings moved.
        """
        with self.transaction():
            numbers = self.conn.execute(
                "SELECT DISTINCT device_id, device_number FROM recording"
                " WHERE import_id = ? AND site_id IS NULL AND device_id IS NOT NULL"
                " AND device_number IS NOT NULL AND (? IS NULL OR device_number = ?)",
                (import_id, device_number, device_number),
            ).fetchall()
            moved = sum(
                self._set_site_number(n["device_id"], n["device_number"], site_id) for n in numbers
            )
            if device_number is None:  # and those that came without a number
                moved += self.conn.execute(
                    "UPDATE recording SET site_id = ? WHERE import_id = ? AND site_id IS NULL",
                    (site_id, import_id),
                ).rowcount
        return moved

    # --- Numbers -----------------------------------------------------------

    def site_numbers(self) -> list[SiteNumber]:
        """Every number recordings came with, and the site each stands for, if any."""
        rows = self.conn.execute(
            "SELECT DISTINCT r.device_id, r.device_number, n.site_id FROM recording r"
            " LEFT JOIN site_number n"
            "  ON n.device_id = r.device_id AND n.device_number = r.device_number"
            " WHERE r.device_id IS NOT NULL AND r.device_number IS NOT NULL"
            " UNION"
            " SELECT device_id, device_number, site_id FROM site_number"
            " ORDER BY 1, 2"
        )
        return [SiteNumber(r[0], r[1], r[2]) for r in rows]

    def site_for_number(self, device_id: int, device_number: int) -> int | None:
        row = self.conn.execute(
            "SELECT site_id FROM site_number WHERE device_id = ? AND device_number = ?",
            (device_id, device_number),
        ).fetchone()
        return row["site_id"] if row else None

    def set_site_number(self, device_id: int, device_number: int, site_id: int | None) -> int:
        """Let a number stand for a site, or for none, moving its recordings along.
        Returns how many recordings moved.
        """
        with self.transaction():
            return self._set_site_number(device_id, device_number, site_id)

    def _set_site_number(self, device_id: int, device_number: int, site_id: int | None) -> int:
        self.conn.execute(
            "DELETE FROM site_number WHERE device_id = ? AND device_number = ?",
            (device_id, device_number),
        )
        if site_id is not None:
            self.conn.execute(
                "INSERT INTO site_number (device_id, device_number, site_id) VALUES (?, ?, ?)",
                (device_id, device_number, site_id),
            )
        cur = self.conn.execute(
            "UPDATE recording SET site_id = ? WHERE device_id = ? AND device_number = ?"
            " AND site_id IS NOT ?",
            (site_id, device_id, device_number, site_id),
        )
        return cur.rowcount

    def set_species_status(self, site_id: int, species: Taxon, status: Status | None) -> None:
        """Override a species' status at a site; None returns it to the profile's."""
        with self.transaction():
            self.conn.execute(
                "DELETE FROM site_species_status WHERE site_id = ? AND species = ?",
                (site_id, species.name),
            )
            if status is not None:
                self.conn.execute(
                    "INSERT INTO site_species_status (site_id, species, status) VALUES (?, ?, ?)",
                    (site_id, species.name, str(status)),
                )

    def region_of(self, site: Site) -> Region:
        """The profile for the site's location, with the site's own statuses on top."""
        profile = regions.profile_for(site.latitude, site.longitude)
        return profile.region.overridden(self.species_statuses(site.id))

    # --- Devices ---------------------------------------------------------

    def device(self, kind: str, uid: str) -> Device:
        """The device with this identifier, added if it is new."""
        with self.transaction():
            self.conn.execute(
                "INSERT INTO device (kind, uid) VALUES (?, ?) ON CONFLICT (kind, uid) DO NOTHING",
                (kind, uid),
            )
        r = self.conn.execute(
            "SELECT * FROM device WHERE kind = ? AND uid = ?", (kind, uid)
        ).fetchone()
        return Device(r["id"], r["kind"], r["uid"], r["label"])

    def add_device_config(self, device_id: int, written_at: datetime, settings: str) -> bool:
        """Keep a configuration as the recorder wrote it; False if already kept."""
        with self.transaction():
            cur = self.conn.execute(
                "INSERT INTO device_config (device_id, written_at, settings) VALUES (?, ?, ?)"
                " ON CONFLICT (device_id, written_at) DO NOTHING",
                (device_id, written_at.isoformat(), settings),
            )
        return cur.rowcount == 1

    def devices(self, kind: str) -> list[Device]:
        rows = self.conn.execute("SELECT * FROM device WHERE kind = ? ORDER BY id", (kind,))
        return [Device(r["id"], r["kind"], r["uid"], r["label"]) for r in rows]

    def device_configs(self, kind: str) -> list[str]:
        """Every stored configuration of that kind of recorder, as it was written."""
        rows = self.conn.execute(
            "SELECT c.settings FROM device_config c JOIN device d ON d.id = c.device_id"
            " WHERE d.kind = ? ORDER BY c.written_at",
            (kind,),
        )
        return [r["settings"] for r in rows]

    def all_devices(self) -> list[Device]:
        rows = self.conn.execute("SELECT * FROM device ORDER BY kind, id")
        return [Device(r["id"], r["kind"], r["uid"], r["label"]) for r in rows]

    def set_device_label(self, device_id: int, label: str | None) -> None:
        with self.transaction():
            self.conn.execute("UPDATE device SET label = ? WHERE id = ?", (label, device_id))

    def configs_of(self, device_id: int) -> list[str]:
        """One device's stored configurations, oldest first, as written."""
        rows = self.conn.execute(
            "SELECT settings FROM device_config WHERE device_id = ? ORDER BY written_at",
            (device_id,),
        )
        return [r["settings"] for r in rows]

    # --- Imports ---------------------------------------------------------

    def imports(self, limit: int = 50) -> list[Import]:
        """The latest imports, newest first, with how many recordings still have no site."""
        rows = self.conn.execute(
            "SELECT i.*, (SELECT COUNT(*) FROM recording r"
            "  WHERE r.import_id = i.id AND r.site_id IS NULL) AS without_site"
            " FROM import i ORDER BY i.id DESC LIMIT ?",
            (limit,),
        )
        return [
            Import(
                id=r["id"],
                source=r["source"],
                started_at=r["started_at"],
                finished_at=r["finished_at"],
                copied=r["copied"],
                skipped=r["skipped"],
                without_site=r["without_site"],
            )
            for r in rows
        ]

    def start_import(
        self, source: str, device_id: int | None = None, site_id: int | None = None
    ) -> int:
        with self.transaction():
            cur = self.conn.execute(
                "INSERT INTO import (source, device_id, site_id, started_at) VALUES (?, ?, ?, ?)",
                (source, device_id, site_id, _now()),
            )
        return _id(cur)

    def finish_import(self, import_id: int, copied: int, skipped: int) -> None:
        with self.transaction():
            self.conn.execute(
                "UPDATE import SET finished_at = ?, copied = ?, skipped = ? WHERE id = ?",
                (_now(), copied, skipped, import_id),
            )

    # --- Recordings ------------------------------------------------------

    def add_recording(
        self,
        sha256: str,
        path: PurePosixPath,
        size_bytes: int,
        recorded_at: datetime | None = None,
        duration_s: float | None = None,
        sample_rate: int | None = None,
        device_id: int | None = None,
        site_id: int | None = None,
        import_id: int | None = None,
        device_number: int | None = None,
    ) -> Recording:
        night = night_of(recorded_at) if recorded_at else None
        with self.transaction():
            cur = self.conn.execute(
                "INSERT INTO recording (sha256, path, file_name, size_bytes, recorded_at, night,"
                " duration_s, sample_rate, device_id, site_id, import_id, added_at, device_number)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sha256,
                    str(path),
                    path.name,
                    size_bytes,
                    recorded_at.isoformat() if recorded_at else None,
                    night.isoformat() if night else None,
                    duration_s,
                    sample_rate,
                    device_id,
                    site_id,
                    import_id,
                    _now(),
                    device_number,
                ),
            )
        return Recording(
            _id(cur),
            sha256,
            path,
            path.name,
            size_bytes,
            recorded_at,
            night,
            duration_s,
            sample_rate,
            device_id,
            site_id,
            import_id,
            device_number,
        )

    def recording(self, recording_id: int) -> Recording | None:
        r = self.conn.execute("SELECT * FROM recording WHERE id = ?", (recording_id,)).fetchone()
        return _recording(r) if r else None

    def recording_by_sha256(self, sha256: str) -> Recording | None:
        r = self.conn.execute("SELECT * FROM recording WHERE sha256 = ?", (sha256,)).fetchone()
        return _recording(r) if r else None

    def has_file(self, device_id: int | None, file_name: str, size_bytes: int) -> bool:
        """Whether a file of that name and size from that device is already here.

        A quick test that needs no reading of the file; the checksum is still
        what decides for a file that passes it.
        """
        row = self.conn.execute(
            "SELECT 1 FROM recording WHERE file_name = ? AND size_bytes = ?"
            " AND device_id IS ? LIMIT 1",
            (file_name, size_bytes, device_id),
        ).fetchone()
        return row is not None

    def recordings_with_result(self, site_id: int | None = None) -> list[tuple[int, int | None]]:
        """(recording, site) for every analysed recording, or those of one site."""
        rows = self.conn.execute(
            "SELECT r.id, r.site_id FROM recording r JOIN result ON result.recording_id = r.id"
            " WHERE ? IS NULL OR r.site_id = ? ORDER BY r.recorded_at, r.id",
            (site_id, site_id),
        )
        return [(r["id"], r["site_id"]) for r in rows]

    def recordings_without_result(self) -> list[Recording]:
        rows = self.conn.execute(
            "SELECT * FROM recording WHERE id NOT IN (SELECT recording_id FROM result)"
            " ORDER BY recorded_at, id"
        )
        return [_recording(r) for r in rows]

    def delete_recording(self, recording_id: int) -> None:
        """Forget a recording and its result. The file is the library's to remove."""
        with self.transaction():
            self.conn.execute("DELETE FROM recording WHERE id = ?", (recording_id,))

    # --- Results ---------------------------------------------------------

    def save_result(self, recording_id: int, result: RecordingResult) -> None:
        """Store a recording's result, replacing any earlier one."""
        data = zlib.compress(json.dumps(result_to_dict(result), separators=(",", ":")).encode())
        with self.transaction():
            self.conn.execute("DELETE FROM result WHERE recording_id = ?", (recording_id,))
            self.conn.execute(
                "INSERT INTO result (recording_id, analysed_at, versions, data)"
                " VALUES (?, ?, ?, ?)",
                (recording_id, _now(), json.dumps(dict(result.versions), sort_keys=True), data),
            )
            for position, v in enumerate(result.verdict.sources if result.verdict else ()):
                self.conn.execute(
                    "INSERT INTO source_verdict (recording_id, position, model_class, taxa,"
                    " reasons, agreeing, named, best_score, n_calls)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        recording_id,
                        position,
                        v.source.model_class,
                        json.dumps(sorted(t.name for t in v.taxa)) if v.taxa else None,
                        json.dumps([str(r) for r in v.reasons]),
                        v.agreement.agreeing,
                        v.agreement.named,
                        max(c.class_prob for c in v.source.calls),
                        len(v.source.calls),
                    ),
                )

    def result(self, recording_id: int) -> RecordingResult | None:
        r = self.conn.execute(
            "SELECT data FROM result WHERE recording_id = ?", (recording_id,)
        ).fetchone()
        return result_from_dict(json.loads(zlib.decompress(r["data"]))) if r else None

    def results_from_other_versions(self, versions: Mapping[str, str]) -> list[int]:
        """Recordings whose result was produced by different code or models.

        The compute device is left out: a result is not out of date because
        another computer would have used another device.
        """
        current = _without_devices(versions)
        rows = self.conn.execute("SELECT recording_id, versions FROM result ORDER BY recording_id")
        return [
            r["recording_id"]
            for r in rows
            if _without_devices(json.loads(r["versions"])) != current
        ]


def _without_devices(versions: Mapping[str, str]) -> dict[str, str]:
    return {k: v for k, v in versions.items() if not k.endswith("-device")}


def _recording(r: sqlite3.Row) -> Recording:
    return Recording(
        id=r["id"],
        sha256=r["sha256"],
        path=PurePosixPath(r["path"]),
        file_name=r["file_name"],
        size_bytes=r["size_bytes"],
        recorded_at=datetime.fromisoformat(r["recorded_at"]) if r["recorded_at"] else None,
        night=date.fromisoformat(r["night"]) if r["night"] else None,
        duration_s=r["duration_s"],
        sample_rate=r["sample_rate"],
        device_id=r["device_id"],
        site_id=r["site_id"],
        import_id=r["import_id"],
        device_number=r["device_number"],
    )


def _id(cur: sqlite3.Cursor) -> int:
    if cur.lastrowid is None:
        raise RuntimeError("the database did not report the new row's id")
    return cur.lastrowid


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
