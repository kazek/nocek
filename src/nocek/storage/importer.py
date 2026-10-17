"""Bring a folder of a recorder's files into the library.

The folder is only ever read. Each new recording is copied into
recordings/<device>/<night>/, its checksum computed during that one read, and
it lands under its final name only once the copy is complete and its checksum
is new, so an interrupted import never leaves a truncated recording behind.

A file already in the library is recognised by device, name and size before
anything is read, so importing the same card again costs a directory listing.
Recordings made in a non-bat mode are not imported. The configurations on
the card are kept as the recorder wrote them, and used, together with those
from earlier imports, to tell which device and mode each recording comes from.

The site comes from the number the recorder was set to: each number stands for
the site the user gave it. A number without one is reported, with where the
recorder was, so a site can be made for it; only a recording without a number
is placed by its position.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path

import soundfile as sf

from nocek.core.nights import night_of
from nocek.recorders.base import Config, Finding, Location, Recorder, RecordingFile, config_at
from nocek.recorders.checks import ConfigIssue, check
from nocek.recorders.pippyg import Pippyg
from nocek.storage.library import Library
from nocek.storage.repository import Device, Repository, Site

# A recording without a number, within this distance of a site's position, belongs to it.
SITE_RADIUS_M = 200.0
# A recording dated this far beyond the moment of import was made by a clock
# running fast.
CLOCK_TOLERANCE = timedelta(hours=1)
# Smaller files hold a header at most.
MIN_SIZE_BYTES = 1024

Progress = Callable[[int, int, str], None]  # done, total, file name


class Skip(StrEnum):
    KNOWN = "known"  # already in the library
    NOT_BAT_MODE = "not-bat-mode"
    UNREADABLE = "unreadable"  # empty, truncated, or not audio


class Notice(StrEnum):
    NO_DEVICE = "no-device"  # recordings that could not be tied to a recorder
    NO_SITE = "no-site"  # recordings whose number, or position, stands for no site
    CLOCK_AHEAD = "clock-ahead"  # recordings dated in the future


@dataclass(frozen=True)
class ImportNotice:
    notice: Notice
    count: int
    example: Path
    location: Location | None = None  # for NO_SITE: where a new site could go
    device_number: int | None = None  # for NO_SITE: the number without a site


@dataclass(frozen=True)
class ImportReport:
    import_id: int
    copied: int
    skipped: dict[Skip, int] = field(default_factory=dict)
    new_configs: int = 0
    findings: tuple[Finding, ...] = ()
    issues: tuple[ConfigIssue, ...] = ()
    notices: tuple[ImportNotice, ...] = ()


def import_folder(
    library: Library,
    folder: Path,
    recorder: Recorder | None = None,
    site: Site | None = None,
    progress: Progress | None = None,
    now: datetime | None = None,
) -> ImportReport:
    recorder = recorder or Pippyg()
    repo = library.repository
    now = now or datetime.now()
    scan = recorder.scan(folder)
    import_id = repo.start_import(str(folder), site_id=site.id if site else None)

    new: list[Config] = []
    for c in scan.configs:
        owner = repo.device(recorder.kind, c.device_uid)
        if repo.add_device_config(owner.id, c.written_at, c.raw):
            new.append(c)
    configs = [recorder.parse_config(raw) for raw in repo.device_configs(recorder.kind)]
    known = repo.devices(recorder.kind)
    by_uid = {d.uid: d for d in known}
    # Recordings from before any configuration belong to the only recorder,
    # when there is only one.
    sole = known[0] if len(known) == 1 else None
    sites = repo.sites()

    skipped = dict.fromkeys(Skip, 0)
    notices: dict[Notice, list[RecordingFile]] = {n: [] for n in Notice if n is not Notice.NO_SITE}
    # Recordings without a site, by number, with where the recorder was.
    homeless: dict[int | None, tuple[list[RecordingFile], list[Location]]] = {}
    chosen: set[tuple[int, int]] = set()  # numbers the import's given site now stands for
    copied = 0
    total = len(scan.recordings)
    for done, file in enumerate(scan.recordings, 1):
        config = config_at(configs, file.recorded_at, file.device_number)
        device = by_uid.get(config.device_uid) if config else sole
        outcome = _import_one(library, file, config, device, recorder.kind, site, sites, import_id)
        if isinstance(outcome, Skip):
            skipped[outcome] += 1
        else:
            copied += 1
            device_known, site_known = outcome
            if not device_known:
                notices[Notice.NO_DEVICE].append(file)
            if not site_known:
                files, places = homeless.setdefault(file.device_number, ([], []))
                files.append(file)
                if config and config.location:
                    places.append(config.location)
            elif site and device and file.device_number is not None:
                chosen.add((device.id, file.device_number))
            if file.recorded_at > now + CLOCK_TOLERANCE:
                notices[Notice.CLOCK_AHEAD].append(file)
        if progress:
            progress(done, total, file.path.name)

    # A site chosen for the import becomes the site of its numbers that had none.
    for device_id, number in chosen:
        if site is not None and repo.site_for_number(device_id, number) is None:
            repo.set_site_number(device_id, number, site.id)
    repo.finish_import(import_id, copied=copied, skipped=sum(skipped.values()))
    fresh = {id(c) for c in new}
    return ImportReport(
        import_id=import_id,
        copied=copied,
        skipped={k: v for k, v in skipped.items() if v},
        new_configs=len(new),
        findings=scan.findings,
        issues=tuple(i for i in check(scan.configs) if id(i.config) in fresh),
        notices=(
            *(ImportNotice(n, len(files), files[0].path) for n, files in notices.items() if files),
            *(
                ImportNotice(Notice.NO_SITE, len(files), files[0].path, _middle(places), number)
                for number, (files, places) in sorted(
                    homeless.items(), key=lambda item: (item[0] is None, item[0] or 0)
                )
            ),
        ),
    )


def _middle(places: list[Location]) -> Location | None:
    """Where the recorder stood: the middle of its positions, each coordinate apart,
    so one stray reading from a GPS still finding itself does not move it.
    """
    if not places:
        return None
    lat = sorted(p.latitude for p in places)[len(places) // 2]
    lon = sorted(p.longitude for p in places)[len(places) // 2]
    return Location(lat, lon)


def _import_one(
    library: Library,
    file: RecordingFile,
    config: Config | None,
    device: Device | None,
    kind: str,
    site: Site | None,
    sites: list[Site],
    import_id: int,
) -> Skip | tuple[bool, bool]:
    """Copy one recording in, or say why not. Returns whether device and site were found."""
    repo = library.repository
    if config is not None and config.mode_at(file.recorded_at) not in (None, "bat"):
        return Skip.NOT_BAT_MODE

    size = file.path.stat().st_size
    if size < MIN_SIZE_BYTES:
        return Skip.UNREADABLE
    if repo.has_file(device.id if device else None, file.path.name, size):
        return Skip.KNOWN
    try:
        info = sf.info(file.path)
    except (sf.LibsndfileError, RuntimeError):
        return Skip.UNREADABLE

    night = night_of(file.recorded_at)
    folder = library.recordings_dir / _device_folder(kind, device) / night.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / file.path.name
    partial = target.with_name(target.name + ".part")
    try:
        sha256 = _copy(file.path, partial)
        if repo.recording_by_sha256(sha256) is not None:
            return Skip.KNOWN
        if target.exists():  # same name, different content: keep both
            target = target.with_name(f"{target.stem}-{sha256[:8]}{target.suffix}")
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)

    at = _site_for(
        repo, site, sites, device, file.device_number, config.location if config else None
    )
    repo.add_recording(
        sha256,
        library.relative(target),
        size,
        recorded_at=file.recorded_at,
        duration_s=info.duration,
        sample_rate=info.samplerate,
        device_id=device.id if device else None,
        site_id=at.id if at else None,
        import_id=import_id,
        device_number=file.device_number,
    )
    return device is not None, at is not None


def _site_for(
    repo: Repository,
    given: Site | None,
    sites: list[Site],
    device: Device | None,
    number: int | None,
    location: Location | None,
) -> Site | None:
    """The site chosen for the import; else the one the number stands for; else, for a
    recording without a number, the nearest site within SITE_RADIUS_M.
    """
    if given is not None:
        return given
    if device is not None and number is not None:
        site_id = repo.site_for_number(device.id, number)
        return next((s for s in sites if s.id == site_id), None)
    if location is None:
        return None
    near = [
        (location.distance_m(Location(s.latitude, s.longitude)), s)
        for s in sites
        if s.latitude is not None and s.longitude is not None
    ]
    near = [(d, s) for d, s in near if d <= SITE_RADIUS_M]
    return min(near, key=lambda pair: pair[0])[1] if near else None


def _device_folder(kind: str, device: Device | None) -> str:
    return f"{kind}-{device.uid}" if device else f"{kind}-unknown"


def _copy(source: Path, target: Path) -> str:
    """Copy a file, returning the SHA-256 of what was read."""
    digest = hashlib.sha256()
    with source.open("rb") as src, target.open("wb") as dst:
        while chunk := src.read(1 << 20):
            digest.update(chunk)
            dst.write(chunk)
    return digest.hexdigest()
