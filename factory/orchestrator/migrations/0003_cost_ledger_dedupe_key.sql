-- A charge that can reach the ledger more than once (a speech line billed with a failed attempt's costs and
-- again with the finished artifact) carries a key; the ledger keeps one row per key and episode.
-- Rows without a key are recorded as before.
ALTER TABLE cost_ledger ADD COLUMN dedupe_key text;
CREATE UNIQUE INDEX cost_ledger_episode_dedupe_key ON cost_ledger (episode, dedupe_key) WHERE dedupe_key IS NOT NULL;
