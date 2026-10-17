-- A recorder can be set to a number of its own (pippyg's device_id, which also
-- names its files DEV_000_...); the user moves it from place to place and gives
-- each place a number. So a number, more than a position, says which site a
-- recording comes from: two sites may stand a few metres apart.

ALTER TABLE recording ADD COLUMN device_number INTEGER;

-- Recordings already in a library get their number from the name pippyg gave them.
UPDATE recording SET device_number = CAST(substr(file_name, 5, 3) AS INTEGER)
WHERE file_name GLOB 'DEV_[0-9][0-9][0-9]_*'
  AND device_id IN (SELECT id FROM device WHERE kind = 'pippyg');

CREATE INDEX recording_device_number ON recording (device_id, device_number);

-- Which site each of a recorder's numbers stands for. A site may have several.
CREATE TABLE site_number (
    device_id      INTEGER NOT NULL REFERENCES device (id) ON DELETE CASCADE,
    device_number  INTEGER NOT NULL,
    site_id        INTEGER NOT NULL REFERENCES site (id) ON DELETE CASCADE,
    PRIMARY KEY (device_id, device_number)
);

-- A number whose recordings all sit at one site already stands for it.
INSERT INTO site_number (device_id, device_number, site_id)
SELECT device_id, device_number, MIN(site_id) FROM recording
WHERE device_id IS NOT NULL AND device_number IS NOT NULL
GROUP BY device_id, device_number
HAVING COUNT(site_id) = COUNT(*) AND COUNT(DISTINCT site_id) = 1;
