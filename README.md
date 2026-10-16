# Nyctalus

Identify bats from ultrasonic recordings, in your browser.

Insert the memory card from your recorder, and Nyctalus copies the new
recordings, finds the echolocation calls, names the species and shows you
what has been flying past, night by night. It runs on your own computer
(macOS, Windows or Linux) and your recordings never leave it.

> **Status:** early development. Nothing here is usable yet. See
> [docs/roadmap.md](docs/roadmap.md).

## Development

Requires Python 3.11 or newer.

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
```

On Windows, use `.venv\Scripts\` instead of `.venv/bin/`.

## Licence

MIT. See [LICENSE](LICENSE). The species models are downloaded at install
time or on first run and keep their own licences.
