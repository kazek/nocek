"""What the server holds between requests: the settings and the open library."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from nocek.storage import settings as app_settings
from nocek.storage.library import Library, LibraryError
from nocek.storage.settings import Settings

log = logging.getLogger(__name__)


class AppState:
    def __init__(self, settings_path: Path, token: str, port: int) -> None:
        self.settings_path = settings_path
        self.token = token
        self.port = port
        # Requests are served from a pool of threads; the library's one
        # database connection is used by one of them at a time.
        self.lock = threading.RLock()
        self.settings = app_settings.load(settings_path)
        self.library: Library | None = None
        self.library_error: str | None = None
        if self.settings.library:
            try:
                self.library = Library.open(self.settings.library, shared=True)
            except LibraryError as error:
                log.warning("cannot open the library: %s", error)
                self.library_error = str(error)

    @contextmanager
    def using(self) -> Iterator[Library | None]:
        with self.lock:
            yield self.library

    def update(self, settings: Settings) -> None:
        with self.lock:
            app_settings.save(settings, self.settings_path)
            self.settings = settings

    def switch_library(self, library: Library) -> None:
        """Make another library the open one, and remember it."""
        with self.lock:
            if self.library is not None:
                self.library.close()
            self.library = library
            self.library_error = None
            self.update(replace(self.settings, library=library.root))

    def close(self) -> None:
        with self.lock:
            if self.library is not None:
                self.library.close()
                self.library = None
