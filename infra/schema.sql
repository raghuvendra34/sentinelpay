-- SentinelPay PostgreSQL schema (Blueprint section 2)
-- Monetary amounts are BIGINT minor units (cents) to avoid floating-point bugs.

CREATE TABLE accounts (
    account_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_name    VARCHAR(120) NOT NULL,
    email         VARCHAR(160) UNIQUE NOT NULL,
    balance_cents BIGINT NOT NULL DEFAULT 0 CHECK (balance_cents >= 0),
    status        VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE transactions (
    tx_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key VARCHAR(100) UNIQUE NOT NULL,
    sender_id       UUID NOT NULL REFERENCES accounts(account_id),
    receiver_id     UUID NOT NULL REFERENCES accounts(account_id),
    amount_cents    BIGINT NOT NULL CHECK (amount_cents > 0),
    merchant_cat    VARCHAR(50) NOT NULL DEFAULT 'P2P_TRANSFER',
    status          VARCHAR(25) NOT NULL DEFAULT 'COMPLETED',
    risk_score      NUMERIC(4,3) DEFAULT 0.000,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE ledger_entries (
    entry_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tx_id        UUID NOT NULL REFERENCES transactions(tx_id),
    account_id   UUID NOT NULL REFERENCES accounts(account_id),
    entry_type   VARCHAR(10) NOT NULL CHECK (entry_type IN ('DEBIT', 'CREDIT')),
    amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE dispute_resolutions (
    dispute_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tx_id           UUID NOT NULL REFERENCES transactions(tx_id),
    reason          TEXT NOT NULL,
    decision        VARCHAR(30) NOT NULL,
    confidence      NUMERIC(4,3) NOT NULL,
    reasoning_trace JSONB NOT NULL,
    resolved_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for the hot queries. IF NOT EXISTS makes this block safe to run on an existing database.
-- (idempotency_key and email are UNIQUE, so Postgres already indexes them.)

-- Ledger history (sender OR receiver, newest first, LIMIT 15) and the agent's last-10 / 30-day baseline queries.
CREATE INDEX IF NOT EXISTS idx_transactions_sender_created   ON transactions (sender_id,   created_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_receiver_created ON transactions (receiver_id, created_at DESC);

-- Joining entries back to a transaction and checking double-entry pairs.
CREATE INDEX IF NOT EXISTS idx_ledger_entries_tx      ON ledger_entries (tx_id);
CREATE INDEX IF NOT EXISTS idx_ledger_entries_account ON ledger_entries (account_id, created_at DESC);

-- Latest dispute per transaction (LATERAL join), the worker's "already resolved?" check, and prior-dispute counts.
CREATE INDEX IF NOT EXISTS idx_dispute_resolutions_tx ON dispute_resolutions (tx_id, resolved_at DESC);

-- Seed: two test accounts with 100000 cents ($1,000.00) each.
-- Fixed UUIDs so the console and tests can reference them without a lookup endpoint.
INSERT INTO accounts (account_id, owner_name, email, balance_cents) VALUES
    ('11111111-1111-4111-8111-111111111111', 'Alice Nguyen', 'alice@sentinelpay.dev', 100000),
    ('22222222-2222-4222-8222-222222222222', 'Ben Carter',   'ben@sentinelpay.dev',   100000)
ON CONFLICT DO NOTHING;
