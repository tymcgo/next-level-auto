-- Next Level Auto — Supabase schema
-- Migration 001: core tables for the agentic OS

-- Canonical moments table
CREATE TABLE IF NOT EXISTS moments (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key TEXT UNIQUE NOT NULL,
    vin TEXT NOT NULL,
    mileage INTEGER,
    dtcs JSONB DEFAULT '[]',
    diag TEXT,
    parts JSONB DEFAULT '[]',
    labor_hours NUMERIC DEFAULT 0,
    labor_rate_cents INTEGER DEFAULT 0,
    estimate_total_cents INTEGER DEFAULT 0,
    approval_status TEXT DEFAULT 'pending',
    subscription_plan TEXT,
    moment_type TEXT NOT NULL,
    raw TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Idempotency tracking — prevents double-processing
CREATE TABLE IF NOT EXISTS processed_moments (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key TEXT UNIQUE NOT NULL,
    tool TEXT NOT NULL,
    result JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Transactional outbox — for verification worker
CREATE TABLE IF NOT EXISTS outbox (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key TEXT NOT NULL,
    tool TEXT NOT NULL,
    result JSONB,
    status TEXT DEFAULT 'pending',
    verified BOOLEAN DEFAULT FALSE,
    verification_note TEXT,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Dead Letter Queue — failed moments
CREATE TABLE IF NOT EXISTS failed_moments (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key TEXT NOT NULL,
    tool TEXT NOT NULL,
    args JSONB,
    error TEXT,
    retry_count INTEGER DEFAULT 0,
    last_retry_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Customer credits for subscriptions
CREATE TABLE IF NOT EXISTS customer_credits (
    id BIGSERIAL PRIMARY KEY,
    customer_email TEXT NOT NULL,
    vin TEXT NOT NULL,
    plan TEXT NOT NULL,
    credits_remaining INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vehicle appraisals (buy/sell)
CREATE TABLE IF NOT EXISTS vehicle_appraisals (
    id BIGSERIAL PRIMARY KEY,
    vin TEXT NOT NULL,
    mileage INTEGER,
    condition TEXT,
    base_value_cents INTEGER,
    offer_cents INTEGER,
    status TEXT DEFAULT 'appraised',
    idempotency_key TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audit log — append-only
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    event TEXT NOT NULL,
    idempotency_key TEXT,
    actor TEXT,
    data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_moments_vin ON moments(vin);
CREATE INDEX IF NOT EXISTS idx_moments_created ON moments(created_at);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox(status, verified);
CREATE INDEX IF NOT EXISTS idx_failed_moments_retry ON failed_moments(retry_count);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);

-- Row Level Security
ALTER TABLE moments ENABLE ROW LEVEL SECURITY;
ALTER TABLE processed_moments ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE failed_moments ENABLE ROW LEVEL SECURITY;
ALTER TABLE customer_credits ENABLE ROW LEVEL SECURITY;
ALTER TABLE vehicle_appraisals ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

-- Service role bypass (agent runs as service role)
CREATE POLICY service_all ON moments FOR ALL USING (true);
CREATE POLICY service_all ON processed_moments FOR ALL USING (true);
CREATE POLICY service_all ON outbox FOR ALL USING (true);
CREATE POLICY service_all ON failed_moments FOR ALL USING (true);
CREATE POLICY service_all ON customer_credits FOR ALL USING (true);
CREATE POLICY service_all ON vehicle_appraisals FOR ALL USING (true);
CREATE POLICY service_all ON audit_log FOR ALL USING (true);
