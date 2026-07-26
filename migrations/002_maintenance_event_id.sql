-- Make maintenance-finding delivery idempotent like every other event table.
ALTER TABLE maintenance_findings
    ADD COLUMN IF NOT EXISTS event_id text;

CREATE UNIQUE INDEX IF NOT EXISTS maintenance_event_id
    ON maintenance_findings (event_id);
