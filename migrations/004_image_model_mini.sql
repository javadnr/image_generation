-- Mini becomes the default model and the free-tier model.
-- Safe to run on existing databases (no data loss).
-- Run on BOTH databases: imagebot (Telegram) and imagebot_bale (Bale).

ALTER TABLE users
    ALTER COLUMN image_model SET DEFAULT 'gpt-image-1-mini';

UPDATE users
    SET image_model = 'gpt-image-1-mini'
    WHERE tier = 'free';
