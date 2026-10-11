-- Token-balance billing: per-user remaining output tokens.
-- Backfills premium users with a full plan allowance by tier.
-- Values must match PLAN_TOKENS in .env.
-- Safe to run on existing databases (no data loss, IF NOT EXISTS guard).
-- Run on BOTH databases: imagebot (Telegram) and imagebot_bale (Bale).

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS token_balance INTEGER DEFAULT 0;

UPDATE users SET token_balance = 10000 WHERE tier = 'bronze';
UPDATE users SET token_balance = 25000 WHERE tier = 'silver';
UPDATE users SET token_balance = 60000 WHERE tier = 'gold';
