-- Picture quality setting: per-user output quality, default low.
-- Safe to run on existing databases (no data loss, IF NOT EXISTS guard).
-- Run on BOTH databases: imagebot (Telegram) and imagebot_bale (Bale).

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS image_quality VARCHAR(10) DEFAULT 'low';
