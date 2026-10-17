"""The API that serves a recording's sound and spectrogram."""

from __future__ import annotations

import re
from pathlib import Path

import soundfile as sf
from fastapi import APIRouter, Request
from fastapi.responses import Response

from nocek.core.audio import AudioError
from nocek.web import media
from nocek.web.errors import ApiError
from nocek.web.library_api import opened

router = APIRouter(prefix="/api")

RANGE = re.compile(r"bytes=(\d*)-(\d*)")


@router.get("/recordings/{recording_id}/audio")
def get_audio(request: Request, recording_id: int, slowdown: int = 10) -> Response:
    if not 1 <= slowdown <= media.MAX_SLOWDOWN:
        raise ApiError(422, "invalid-slowdown", str(slowdown))
    try:
        content = media.slowed_wav(_file(request, recording_id), slowdown)
    except sf.LibsndfileError as error:
        raise ApiError(422, "unreadable-recording", str(error)) from error
    return _ranged(request, content, "audio/wav")


@router.get("/recordings/{recording_id}/spectrogram")
def get_spectrogram(
    request: Request,
    recording_id: int,
    width: int = 1600,
    min_khz: float = 10.0,
    max_khz: float | None = None,
    range_db: float = 30.0,
    start_s: float = 0.0,
    end_s: float | None = None,
) -> Response:
    """Pixels as bytes, one column after another, each from low to high frequency.

    start_s and end_s draw only that stretch of the recording, at full detail.
    """
    valid_range = start_s >= 0 and (end_s is None or end_s > start_s)
    if not (1 <= width <= 20_000 and min_khz >= 0 and 10 <= range_db <= 150 and valid_range):
        raise ApiError(422, "invalid-spectrogram", "")
    try:
        picture = media.image(
            _file(request, recording_id), width, min_khz, max_khz, range_db, start_s, end_s
        )
    except AudioError as error:
        raise ApiError(422, "unreadable-recording", str(error)) from error
    columns, rows = picture.pixels.shape
    return Response(
        picture.pixels.tobytes(),
        media_type="application/octet-stream",
        headers={
            "X-Columns": str(columns),
            "X-Rows": str(rows),
            "X-Seconds-Per-Column": repr(picture.seconds_per_column),
            "X-Min-Khz": repr(picture.min_khz),
            "X-Khz-Per-Row": repr(picture.khz_per_row),
            "X-Duration-S": repr(picture.duration_s),
            "X-Start-S": repr(picture.start_s),
            "X-Top-Db": repr(picture.top_db),
            "X-Range-Db": repr(picture.range_db),
        },
    )


def _file(request: Request, recording_id: int) -> Path:
    """The recording's file, which must lie inside the library."""
    with opened(request) as library:
        recording = library.repository.recording(recording_id)
        if recording is None:
            raise ApiError(404, "no-such-recording", str(recording_id))
        path = library.path_of(recording.path).resolve()
        if not path.is_relative_to(library.recordings_dir.resolve()):
            raise ApiError(404, "no-such-recording", str(recording_id))
    if not path.is_file():
        raise ApiError(404, "file-missing", recording.path.name)
    return path


def _ranged(request: Request, content: bytes, media_type: str) -> Response:
    """The content, or the part of it asked for: browsers seek audio this way."""
    headers = {"Accept-Ranges": "bytes"}
    asked = RANGE.fullmatch(request.headers.get("range", "").strip())
    if not asked:
        return Response(content, media_type=media_type, headers=headers)
    size = len(content)
    start_text, end_text = asked.groups()
    if start_text:
        start = int(start_text)
        end = min(int(end_text), size - 1) if end_text else size - 1
    else:  # the last n bytes
        start, end = max(0, size - int(end_text or 0)), size - 1
    if start >= size or start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return Response(content[start : end + 1], 206, media_type=media_type, headers=headers)
