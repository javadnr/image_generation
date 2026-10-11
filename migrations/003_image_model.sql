-- Generation model picker: per-user model, default flare (free), sunburst premium-only.
-- Safe to run on existing databases (no data loss, IF NOT EXISTS guard).
-- Run on BOTH databases: imagebot (Telegram) and imagebot_bale (Bale).

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS image_model VARCHAR(50) DEFAULT 'gpt-image-2.5-flare';
