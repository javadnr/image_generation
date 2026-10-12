-- Token-balance billing: per-user remaining output tokens.
-- Backfills premium users with a full plan allowance by tier.
-- Values must match PLAN_TOKENS in .env.
-- Only NULL/zero balances are touched: re-running this file must never
-- reset a live positive balance. Safe to run on existing databases
-- (no data loss, IF NOT EXISTS guard).
-- Run on BOTH databases: imagebot (Telegram) and imagebot_bale (Bale).

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS token_balance INTEGER DEFAULT 0;

UPDATE users SET token_balance = 10000
    WHERE tier = 'bronze' AND (token_balance IS NULL OR token_balance = 0);
UPDATE users SET token_balance = 25000
    WHERE tier = 'silver' AND (token_balance IS NULL OR token_balance = 0);
UPDATE users SET token_balance = 60000
    WHERE tier = 'gold' AND (token_balance IS NULL OR token_balance = 0);
