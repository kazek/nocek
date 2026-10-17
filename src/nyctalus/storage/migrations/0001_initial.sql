-- Sites, recorders, recordings and their latest results.
--
-- Times written by the application are UTC, ISO 8601. Times read from a
-- recorder (recorded_at, device_config.written_at) are its local clock, as
-- it writes them, without a zone. Nights are the date the night began.

CREATE TABLE site (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    latitude    REAL,
    longitude   REAL,
    created_at  TEXT NOT NULL
);

-- A site's own statuses, over the region profile chosen by its location.
CREATE TABLE site_species_status (
    site_id  INTEGER NOT NULL REFERENCES site (id) ON DELETE CASCADE,
    species  TEXT NOT NULL,
    status   TEXT NOT NULL CHECK (status IN ('occurs', 'rare', 'absent')),
    PRIMARY KEY (site_id, species)
);

CREATE TABLE device (
    id     INTEGER PRIMARY KEY,
    kind   TEXT NOT NULL,      -- which recorder, e.g. 'pippyg'
    uid    TEXT NOT NULL,      -- the recorder's own hardware identifier
    label  TEXT,               -- what the user calls it
    UNIQUE (kind, uid)
);

-- Every configuration found on a card, exactly as the recorder wrote it.
CREATE TABLE device_config (
    id          INTEGER PRIMARY KEY,
    device_id   INTEGER NOT NULL REFERENCES device (id) ON DELETE CASCADE,
    written_at  TEXT NOT NULL,
    settings    TEXT NOT NULL,
    UNIQUE (device_id, written_at)
);

CREATE TABLE import (
    id           INTEGER PRIMARY KEY,
    source       TEXT NOT NULL,   -- the card or folder imported from
    device_id    INTEGER REFERENCES device (id),
    site_id      INTEGER REFERENCES site (id),
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    copied       INTEGER NOT NULL DEFAULT 0,
    skipped      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE recording (
    id           INTEGER PRIMARY KEY,
    sha256       TEXT NOT NULL UNIQUE,   -- identity: the same file is the same recording
    path         TEXT NOT NULL UNIQUE,   -- inside the library, with forward slashes
    file_name    TEXT NOT NULL,
    size_bytes   INTEGER NOT NULL,
    recorded_at  TEXT,
    night        TEXT,
    duration_s   REAL,
    sample_rate  INTEGER,
    device_id    INTEGER REFERENCES device (id),
    site_id      INTEGER REFERENCES site (id),
    import_id    INTEGER REFERENCES import (id),
    added_at     TEXT NOT NULL
);

CREATE INDEX recording_site_night ON recording (site_id, night);
CREATE INDEX recording_device_night ON recording (device_id, night);

-- The latest result of analysing a recording.
CREATE TABLE result (
    recording_id  INTEGER PRIMARY KEY REFERENCES recording (id) ON DELETE CASCADE,
    analysed_at   TEXT NOT NULL,
    versions      TEXT NOT NULL,   -- JSON: what produced it
    data          BLOB NOT NULL    -- zlib-compressed JSON, see storage/serialize.py
);

-- One animal in a result, kept apart from the blob so totals are plain SQL.
CREATE TABLE source_verdict (
    recording_id  INTEGER NOT NULL REFERENCES result (recording_id) ON DELETE CASCADE,
    position      INTEGER NOT NULL,
    model_class   TEXT NOT NULL,
    taxa          TEXT,             -- JSON list of names, sorted; NULL when withheld
    reasons       TEXT NOT NULL,    -- JSON list of reason codes
    agreeing      INTEGER NOT NULL,
    named         INTEGER NOT NULL,
    best_score    REAL NOT NULL,
    n_calls       INTEGER NOT NULL,
    PRIMARY KEY (recording_id, position)
);

CREATE INDEX source_verdict_taxa ON source_verdict (taxa);
