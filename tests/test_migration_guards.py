"""The 006 backfill must never reset a live positive balance.

Runs the actual UPDATE statements from migrations/006_token_billing.sql
(the ALTER TABLE line is PostgreSQL-only and skipped on SQLite).
"""
import sqlite3


def _updates_only(sql_path: str) -> str:
    with open(sql_path) as f:
        content = f.read()
    return ";\n".join(
        stmt for stmt in content.split(";")
        if stmt.strip().upper().startswith("UPDATE")
    ) + ";"


def test_backfill_preserves_positive_balances(tmp_path):
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, tier VARCHAR(20), "
        "token_balance INTEGER)"
    )
    db.executemany(
        "INSERT INTO users (tier, token_balance) VALUES (?, ?)",
        [
            ("bronze", 21278),   # live balance: must be preserved
            ("bronze", 0),       # unset: gets the allowance
            ("bronze", None),    # unset: gets the allowance
            ("silver", 5000),    # live balance: must be preserved
            ("gold", 0),         # unset: gets the allowance
            ("free", 300),       # untouched by this file
        ],
    )

    db.executescript(_updates_only("migrations/006_token_billing.sql"))

    rows = {
        (tier, bal)
        for tier, bal in db.execute("SELECT tier, token_balance FROM users")
    }
    assert ("bronze", 21278) in rows
    assert ("bronze", 10000) in rows
    assert ("silver", 5000) in rows
    assert ("gold", 60000) in rows
    assert ("free", 300) in rows
    # re-running must be a no-op for everyone
    db.executescript(_updates_only("migrations/006_token_billing.sql"))
    assert set(db.execute("SELECT tier, token_balance FROM users")) == rows
    db.close()
