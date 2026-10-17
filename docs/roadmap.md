# Roadmap

Nocek is a rewrite of a single-station research setup as an application
anyone with a recorder can install and use. Work proceeds in stages; each
stage is small enough to review in one sitting.

| # | Stage | Content | Done |
| --- | --- | --- | --- |
| 0 | Skeleton | Package layout, tooling, tests, licence | ✓ |
| 1 | Core library | Pulse detection, the three classifiers behind one interface, cross-checking between them, tested against reference calls | ✓ |
| 2 | Storage | SQLite model: site, device, import, night, recording, per-classifier result. Species identified by scientific name | ✓ |
| 3 | Recorders | Safe, read-only import from a folder the user picks. Device adapters, starting with pippyg: device number, location, schedule and settings read from the card and respected | ✓ |
| 4 | Web backend | HTTP API, background jobs with progress, first-run model download, localisation plumbing | ✓ |
| 5 | Interface | One page: import, sites by recorder number, a calendar of nights, the night as one bar from sunset to sunrise, the recording with its spectrogram and slowed playback. Web Awesome components, light and dark themes | ✓ |
| 6 | Translations | English, Polish, German. Local species names, always shown with the scientific name | ✓ |
| 7 | Distribution | Install from the repository with `uv tool install`, a shortcut in the system's menu, the browser opens on start | ✓ |
| 8 | Documentation | User guide, translator guide, architecture notes | |

Later: manual verification of identifications; other recorders (AudioMoth).

## Decisions

- Python 3.11+, macOS, Windows and Linux.
- Backend: FastAPI. Frontend: plain JavaScript modules, no build step.
- Storage: one SQLite database inside the library, the folder the user chose.
- Web interface only; the command line just starts it and makes its shortcut.
- Translations: JSON files, one per language.
- Recordings and their metadata are kept as the recorder wrote them.
