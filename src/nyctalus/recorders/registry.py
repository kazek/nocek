"""Every recorder the application can read, by kind."""

from __future__ import annotations

from nyctalus.recorders.base import Recorder
from nyctalus.recorders.pippyg import Pippyg

RECORDERS: dict[str, Recorder] = {r.kind: r for r in (Pippyg(),)}
