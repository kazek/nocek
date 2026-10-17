"""Every recorder the application can read, by kind."""

from __future__ import annotations

from nocek.recorders.base import Recorder
from nocek.recorders.pippyg import Pippyg

RECORDERS: dict[str, Recorder] = {r.kind: r for r in (Pippyg(),)}
