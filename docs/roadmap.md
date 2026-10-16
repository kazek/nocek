# Roadmap

Nyctalus is a rewrite of a single-station research setup as an application
anyone with a recorder can install and use. Work proceeds in stages; each
stage is small enough to review in one sitting.

| # | Stage | Content |
| --- | --- | --- |
| 0 | Skeleton | Package layout, tooling, tests, licence |
| 1 | Core library | Pulse detection, the three classifiers behind one interface, cross-checking between them, tested against reference calls |
| 2 | Storage | SQLite model: site, device, import, night, recording, per-classifier result. Species identified by scientific name |
| 3 | Recorders | Card detection and safe, read-only import. Device adapters, starting with pippyg: device ID, location, schedule and settings read from the card and respected |
| 4 | Web backend | HTTP API, background jobs with progress, first-run model download, localisation plumbing |
| 5 | Interface | First-run setup, import from card, nights and recordings, spectrogram, slowed playback, species totals, device view |
| 6 | Translations | English, Polish, German. Local species names, always shown with the scientific name |
| 7 | Distribution | One-command install (`pipx install nyctalus`), the browser opens on start |
| 8 | Documentation | User guide, translator guide, architecture notes |

Later: manual verification of identifications; other recorders (AudioMoth).

## Decisions

- Python 3.11+, macOS, Windows and Linux.
- Backend: FastAPI. Frontend: plain JavaScript modules, no build step.
- Storage: one SQLite database in the user's data directory.
- Web interface only; the command line just starts it.
- Translations: JSON files, one per language.
- Recordings and their metadata are kept as the recorder wrote them.
