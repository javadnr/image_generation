-- Analytics events upgrade: metadata column + query indexes.
-- Safe to run on existing databases (no data loss, IF NOT EXISTS guards).
-- Run on BOTH databases: imagebot (Telegram) and imagebot_bale (Bale).

ALTER TABLE user_events
    ADD COLUMN IF NOT EXISTS event_meta JSON;

ALTER TABLE user_events
    ALTER COLUMN event_type TYPE VARCHAR(40);

CREATE INDEX IF NOT EXISTS ix_user_events_type_created
    ON user_events (event_type, created_at);

CREATE INDEX IF NOT EXISTS ix_user_events_user
    ON user_events (user_id);
