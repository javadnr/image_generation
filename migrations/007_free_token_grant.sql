-- Free credit grant: every free-tier user receives the configured
-- one-time FREE_USAGE_TOKEN allowance (default 1000).
-- Only touches zero-balance free users; premium balances are paid for
-- and never modified here.
-- Run on BOTH databases: imagebot (Telegram) and imagebot_bale (Bale).

UPDATE users
    SET token_balance = 1000
    WHERE tier = 'free' AND (token_balance IS NULL OR token_balance = 0);
