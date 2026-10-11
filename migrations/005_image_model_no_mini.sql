-- Mini removed from the model list: flare becomes the default again.
-- Safe to run on existing databases (no data loss).
-- Run on BOTH databases: imagebot (Telegram) and imagebot_bale (Bale).

ALTER TABLE users
    ALTER COLUMN image_model SET DEFAULT 'gpt-image-2.5-flare';

UPDATE users
    SET image_model = 'gpt-image-2.5-flare'
    WHERE image_model = 'gpt-image-1-mini';
