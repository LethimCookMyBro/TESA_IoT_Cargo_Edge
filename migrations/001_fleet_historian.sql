-- CargoShield central fleet historian, schema version 1.
--
-- Repeatable: every statement is guarded, so re-running this file against an already-migrated
-- database is a no-op. cargo/migrate.py additionally records applied versions in
-- schema_migrations and skips files it has already run.
--
-- Time is stored as bigint epoch milliseconds, matching the wire contract exactly. observed_ms is
-- when the robot saw it; received_ms is when the historian did. Keeping both is what makes
-- out-of-order and stale-sample analysis possible after the fact.

CREATE TABLE IF NOT EXISTS robots (
    robot_id      text PRIMARY KEY CHECK (robot_id ~ '^[a-z0-9][a-z0-9-]{1,31}$'),
    provenance    text NOT NULL CHECK (provenance IN ('SIMULATED', 'DATASET', 'HARDWARE')),
    first_seen_ms bigint NOT NULL CHECK (first_seen_ms >= 0),
    last_seen_ms  bigint NOT NULL CHECK (last_seen_ms >= 0),
    status        text NOT NULL DEFAULT 'IDLE',
    health_state  text NOT NULL DEFAULT 'HEALTHY'
                  CHECK (health_state IN ('HEALTHY', 'DEGRADED', 'UNSAFE', 'OFFLINE'))
);

CREATE TABLE IF NOT EXISTS missions (
    mission_id   text PRIMARY KEY,
    robot_id     text NOT NULL REFERENCES robots (robot_id) ON DELETE CASCADE,
    cargo_type   text NOT NULL CHECK (cargo_type IN ('standard', 'fragile')),
    -- The route as planned at mission start. A snapshot on purpose: the running route never changes,
    -- so this row stays a faithful record of what the robot was told to walk.
    route        jsonb,
    route_cost   double precision,
    route_reason text,
    started_ms   bigint NOT NULL CHECK (started_ms >= 0),
    ended_ms     bigint CHECK (ended_ms IS NULL OR ended_ms >= started_ms)
);

CREATE TABLE IF NOT EXISTS telemetry_samples (
    event_id    text PRIMARY KEY,
    robot_id    text NOT NULL REFERENCES robots (robot_id) ON DELETE CASCADE,
    mission_id  text REFERENCES missions (mission_id) ON DELETE SET NULL,
    seq         bigint CHECK (seq IS NULL OR seq >= 0),
    observed_ms bigint NOT NULL CHECK (observed_ms >= 0),
    received_ms bigint NOT NULL CHECK (received_ms >= 0),
    provenance  text NOT NULL CHECK (provenance IN ('SIMULATED', 'DATASET', 'HARDWARE')),
    source_mode text NOT NULL,
    zone        text,
    channels    jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS derived_features (
    event_id    text PRIMARY KEY,
    robot_id    text NOT NULL REFERENCES robots (robot_id) ON DELETE CASCADE,
    mission_id  text REFERENCES missions (mission_id) ON DELETE SET NULL,
    observed_ms bigint NOT NULL CHECK (observed_ms >= 0),
    provenance  text NOT NULL CHECK (provenance IN ('SIMULATED', 'DATASET', 'HARDWARE')),
    features    jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS model_predictions (
    event_id       text PRIMARY KEY,
    robot_id       text NOT NULL REFERENCES robots (robot_id) ON DELETE CASCADE,
    mission_id     text REFERENCES missions (mission_id) ON DELETE SET NULL,
    observed_ms    bigint NOT NULL CHECK (observed_ms >= 0),
    provenance     text NOT NULL CHECK (provenance IN ('SIMULATED', 'DATASET', 'HARDWARE')),
    label          text,
    confidence     double precision CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    vibration_score double precision,
    vibration_risk text CHECK (vibration_risk IS NULL OR vibration_risk IN ('low', 'medium', 'high')),
    -- Whether the confidence policy accepted this prediction or rejected it into HOLD_UNCERTAIN.
    accepted       boolean
);

-- Safety decisions, health faults and mission events share one table because they share one query
-- pattern: "what happened to this robot, in severity order, over this time range".
CREATE TABLE IF NOT EXISTS fleet_events (
    event_id     text PRIMARY KEY,
    robot_id     text NOT NULL REFERENCES robots (robot_id) ON DELETE CASCADE,
    mission_id   text REFERENCES missions (mission_id) ON DELETE SET NULL,
    kind         text NOT NULL CHECK (kind IN ('safety_decision', 'health_event', 'mission_event')),
    code         text,
    severity     text NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    observed_ms  bigint NOT NULL CHECK (observed_ms >= 0),
    received_ms  bigint NOT NULL CHECK (received_ms >= 0),
    provenance   text NOT NULL CHECK (provenance IN ('SIMULATED', 'DATASET', 'HARDWARE')),
    zone         text,
    status       text,
    health_state text,
    action       text,
    speed_ratio  double precision,
    reason       text,
    payload      jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS maintenance_findings (
    finding_id      bigserial PRIMARY KEY,
    robot_id        text NOT NULL REFERENCES robots (robot_id) ON DELETE CASCADE,
    mission_id      text REFERENCES missions (mission_id) ON DELETE SET NULL,
    opened_ms       bigint NOT NULL CHECK (opened_ms >= 0),
    severity        text NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    reason          text NOT NULL,
    -- NULL means unresolved. Acknowledgement is always a human act; nothing automated writes these.
    acknowledged_ms bigint CHECK (acknowledged_ms IS NULL OR acknowledged_ms >= opened_ms),
    acknowledged_by text,
    note            text
);

CREATE TABLE IF NOT EXISTS export_manifests (
    export_id      text PRIMARY KEY,
    created_ms     bigint NOT NULL CHECK (created_ms >= 0),
    schema_version integer NOT NULL,
    format         text NOT NULL CHECK (format IN ('csv', 'jsonl')),
    row_count      bigint NOT NULL CHECK (row_count >= 0),
    from_ms        bigint,
    to_ms          bigint,
    robot_ids      text[] NOT NULL DEFAULT '{}',
    labels         text[] NOT NULL DEFAULT '{}',
    provenance     text[] NOT NULL DEFAULT '{}',
    filters        jsonb NOT NULL DEFAULT '{}'::jsonb,
    path           text NOT NULL
);

-- Indexes chosen for the four queries the dashboard and the maintenance context actually run.
CREATE INDEX IF NOT EXISTS telemetry_robot_time ON telemetry_samples (robot_id, observed_ms DESC);
CREATE INDEX IF NOT EXISTS telemetry_mission_time ON telemetry_samples (mission_id, observed_ms DESC);
CREATE INDEX IF NOT EXISTS predictions_robot_time ON model_predictions (robot_id, observed_ms DESC);
CREATE INDEX IF NOT EXISTS features_robot_time ON derived_features (robot_id, observed_ms DESC);
CREATE INDEX IF NOT EXISTS events_robot_time ON fleet_events (robot_id, observed_ms DESC);
CREATE INDEX IF NOT EXISTS events_mission_time ON fleet_events (mission_id, observed_ms DESC);
CREATE INDEX IF NOT EXISTS events_severity_time ON fleet_events (severity, observed_ms DESC);
CREATE INDEX IF NOT EXISTS missions_robot_time ON missions (robot_id, started_ms DESC);
-- Partial index: "which robots need inspection" only ever asks for the unresolved rows.
CREATE INDEX IF NOT EXISTS maintenance_unresolved
    ON maintenance_findings (robot_id, opened_ms DESC) WHERE acknowledged_ms IS NULL;
