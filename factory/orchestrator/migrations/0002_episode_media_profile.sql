-- The config/media.yaml profile an episode runs on, pinned at SPEC like its config: a resumed run must
-- not voice with one provider and publish with another. Episodes created before this ran on `fake`.
ALTER TABLE episode ADD COLUMN media_profile text NOT NULL DEFAULT 'fake';
ALTER TABLE episode ALTER COLUMN media_profile DROP DEFAULT;
