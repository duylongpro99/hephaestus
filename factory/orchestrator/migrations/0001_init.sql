-- The tables the walking skeleton needs, with the column names of architecture §10.
-- Artifacts live in the content-addressed store; these rows hold pointers and state.

CREATE TABLE channel (
    id                 text PRIMARY KEY,
    bible_version      integer NOT NULL,
    pack               text NOT NULL,
    framework          text NOT NULL,
    audience           text NOT NULL,
    youtube_channel_id text,
    cadence            text,
    timezone           text NOT NULL DEFAULT 'UTC',
    budget_usd         numeric(10, 4) NOT NULL DEFAULT 3,
    paused             boolean NOT NULL DEFAULT false
);

CREATE TABLE episode (
    id                text PRIMARY KEY,
    channel           text NOT NULL REFERENCES channel (id),
    season            text,
    source            text NOT NULL CHECK (source IN ('season', 'adhoc')),
    status            text NOT NULL CHECK (status IN (
        'SPEC', 'DRAFTED', 'LEVEL_OK', 'ENRICHED', 'QA_OK', 'SCRIPT_APPROVED', 'VOICED',
        'VISUALS_READY', 'RENDERED', 'VISUAL_QA_OK', 'PACKAGED', 'COMPLIANT', 'FINAL_APPROVED',
        'UPLOADED', 'SCHEDULED', 'ESCALATED', 'BUDGET_EXCEEDED', 'CANCELLED')),
    status_changed_at timestamptz NOT NULL,
    config_hash       text NOT NULL,
    ordering          text NOT NULL CHECK (ordering IN ('strict', 'loose')),
    publish_slot      timestamptz,
    budget_usd        numeric(10, 4) NOT NULL,
    supersedes        text REFERENCES episode (id),
    superseded_by     text REFERENCES episode (id),
    -- The work order and the ResolvedConfig pinned at SPEC (§4.5); stations never read live config.
    spec              jsonb NOT NULL,
    resolved_config   jsonb NOT NULL
);

CREATE TABLE artifact (
    id             bigserial PRIMARY KEY,
    episode        text NOT NULL REFERENCES episode (id),
    station        text NOT NULL,
    station_version text NOT NULL,
    hash           text NOT NULL,
    uri            text NOT NULL,  -- relative to the artifact store root
    schema_version text NOT NULL,
    artifact_type  text NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (episode, station, hash)
);

CREATE TABLE job (
    id          bigserial PRIMARY KEY,
    episode     text NOT NULL REFERENCES episode (id),
    station     text NOT NULL,
    from_status text NOT NULL,
    to_status   text,  -- null while the step is retried
    attempt     integer NOT NULL,
    status      text NOT NULL CHECK (status IN ('succeeded', 'retrying', 'escalated', 'failed', 'rejected')),
    started_at  timestamptz NOT NULL,
    finished_at timestamptz NOT NULL,
    error       text
);
CREATE INDEX job_episode ON job (episode, id);

CREATE TABLE gate_decision (
    id       bigserial PRIMARY KEY,
    episode  text REFERENCES episode (id),
    season   text,
    gate     integer NOT NULL CHECK (gate IN (0, 1, 2)),
    "user"   text NOT NULL,
    decision text NOT NULL CHECK (decision IN ('approve', 'edit-and-approve', 'reject')),
    diff     text,
    notes    text NOT NULL DEFAULT '',
    ts       timestamptz NOT NULL,
    CHECK (episode IS NOT NULL OR season IS NOT NULL)
);

CREATE TABLE cost_ledger (
    id      bigserial PRIMARY KEY,
    episode text NOT NULL REFERENCES episode (id),
    station text NOT NULL,
    vendor  text NOT NULL,
    model   text NOT NULL,
    units   jsonb NOT NULL,  -- tokens, characters or seconds, as the vendor bills them
    usd     numeric(12, 6) NOT NULL,
    priced  boolean NOT NULL,
    ts      timestamptz NOT NULL
);
CREATE INDEX cost_ledger_episode ON cost_ledger (episode);

CREATE TABLE publish_receipt (
    id          bigserial PRIMARY KEY,
    episode     text NOT NULL REFERENCES episode (id),
    platform    text NOT NULL,
    external_id text NOT NULL,
    upload_ts   timestamptz NOT NULL,
    publish_at  timestamptz,
    status      text NOT NULL,
    quota_units integer NOT NULL DEFAULT 0,
    UNIQUE (episode, platform)
);
