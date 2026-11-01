-- An upload in flight: written and committed before the first byte goes to the platform, removed in the
-- same transaction that stores the receipt. A row without a receipt means a video may exist that the
-- factory has no id for, so a retry looks for it instead of uploading a second copy.
CREATE TABLE publish_attempt (
    episode    text        NOT NULL REFERENCES episode (id),
    platform   text        NOT NULL,
    started_at timestamptz NOT NULL,
    PRIMARY KEY (episode, platform)
);
