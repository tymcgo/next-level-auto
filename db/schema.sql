-- Next Level Auto — Supabase/Postgres Schema
-- All tables are append-only where noted. Idempotency keys prevent duplicates.

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- EVENTS TABLE (append-only, partitioned by vin_last6)
-- =============================================================================
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    schema_version TEXT NOT NULL DEFAULT '1.0.0',
    idempotency_key TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    vin CHAR(17) NOT NULL,
    vin_last6 CHAR(6) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw JSONB NOT NULL DEFAULT '{}',
    normalized JSONB NOT NULL DEFAULT '{}',
    source TEXT NOT NULL,
    correlation_id UUID,
    actor_id TEXT,
    cost_tokens JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Partitioning by vin_last6 (hash分区)
-- Note: For self-hosted Supabase, use declarative partitioning
-- For free tier, skip partitioning — use index instead
CREATE INDEX idx_events_vin_last6 ON events (vin_last6);
CREATE INDEX idx_events_idempotency ON events (idempotency_key);
CREATE INDEX idx_events_type ON events (event_type);
CREATE INDEX idx_events_timestamp ON events (timestamp DESC);
CREATE INDEX idx_events_correlation ON events (correlation_id);

-- Prevent updates/deletes on append-only table
CREATE OR REPLACE FUNCTION prevent_events_update()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'events table is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_events_append_only
    BEFORE UPDATE OR DELETE ON events
    FOR EACH ROW EXECUTE FUNCTION prevent_events_update();

-- =============================================================================
-- QUEUE TABLE (pgmq-style)
-- =============================================================================
CREATE TABLE event_queue (
    id BIGSERIAL PRIMARY KEY,
    vin_last6 CHAR(6) NOT NULL,
    event_id UUID NOT NULL REFERENCES events(id),
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, processing, completed, failed, dlq
    attempts INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    next_retry_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_queue_status ON event_queue (status, next_retry_at);
CREATE INDEX idx_queue_vin ON event_queue (vin_last6);

-- =============================================================================
-- DLQ (Dead Letter Queue)
-- =============================================================================
CREATE TABLE event_dlq (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES events(id),
    original_event JSONB NOT NULL,
    error_message TEXT,
    error_stack TEXT,
    failed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved BOOLEAN DEFAULT FALSE
);

-- =============================================================================
-- AUDIT LOG (append-only)
-- =============================================================================
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID REFERENCES events(id),
    action TEXT NOT NULL,
    actor_id TEXT,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    before_state JSONB,
    after_state JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_target ON audit_log (target_type, target_id);
CREATE INDEX idx_audit_created ON audit_log (created_at DESC);

-- =============================================================================
-- CUSTOMERS
-- =============================================================================
CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    phone TEXT UNIQUE,
    email TEXT UNIQUE,
    name TEXT NOT NULL,
    telegram_chat_id BIGINT,
    stripe_customer_id TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- VEHICLES
-- =============================================================================
CREATE TABLE vehicles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    vin CHAR(17) NOT NULL UNIQUE,
    vin_last6 CHAR(6) NOT NULL,
    year INT,
    make TEXT,
    model TEXT,
    trim TEXT,
    engine TEXT,
    transmission TEXT,
    color TEXT,
    mileage INT,
    customer_id UUID REFERENCES customers(id),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_vehicles_vin ON vehicles (vin);
CREATE INDEX idx_vehicles_customer ON vehicles (customer_id);

-- =============================================================================
-- REPAIR ORDERS (RO)
-- =============================================================================
CREATE TABLE repair_orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    ro_number TEXT NOT NULL UNIQUE,
    vehicle_id UUID NOT NULL REFERENCES vehicles(id),
    customer_id UUID NOT NULL REFERENCES customers(id),
    status TEXT NOT NULL DEFAULT 'draft',  -- draft, pending_approval, approved, in_progress, completed, closed, cancelled
    total_labor DECIMAL(10,2) NOT NULL DEFAULT 0,
    total_parts DECIMAL(10,2) NOT NULL DEFAULT 0,
    total_tax DECIMAL(10,2) NOT NULL DEFAULT 0,
    total_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
    description TEXT,
    notes TEXT,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    correlation_id UUID,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ro_vehicle ON repair_orders (vehicle_id);
CREATE INDEX idx_ro_customer ON repair_orders (customer_id);
CREATE INDEX idx_ro_status ON repair_orders (status);

-- =============================================================================
-- ESTIMATES
-- =============================================================================
CREATE TABLE estimates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    ro_id UUID REFERENCES repair_orders(id),
    vehicle_id UUID NOT NULL REFERENCES vehicles(id),
    customer_id UUID NOT NULL REFERENCES customers(id),
    status TEXT NOT NULL DEFAULT 'draft',  -- draft, sent, approved, declined, expired
    line_items JSONB NOT NULL DEFAULT '[]',
    subtotal DECIMAL(10,2) NOT NULL DEFAULT 0,
    tax DECIMAL(10,2) NOT NULL DEFAULT 0,
    total DECIMAL(10,2) NOT NULL DEFAULT 0,
    customer_approval_token TEXT UNIQUE,
    approved_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_estimates_ro ON estimates (ro_id);
CREATE INDEX idx_estimates_status ON estimates (status);

-- =============================================================================
-- PARTS
-- =============================================================================
CREATE TABLE parts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    ro_id UUID REFERENCES repair_orders(id),
    sku TEXT,
    name TEXT NOT NULL,
    supplier TEXT,
    quantity INT NOT NULL DEFAULT 1,
    unit_cost DECIMAL(10,2) NOT NULL DEFAULT 0,
    unit_price DECIMAL(10,2) NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, ordered, received, installed, returned
    order_ref TEXT,
    ordered_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- APPROVALS
-- =============================================================================
CREATE TABLE approvals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    target_type TEXT NOT NULL,  -- estimate, parts_order, vehicle_listing
    target_id UUID NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, granted, denied, escalated, expired
    requested_by TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    required_by TEXT NOT NULL DEFAULT 'tyler',
    responded_by TEXT,
    responded_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '3 hours',
    escalation_count INT NOT NULL DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_approvals_status ON approvals (status);
CREATE INDEX idx_approvals_target ON approvals (target_type, target_id);
CREATE INDEX idx_approvals_expires ON approvals (expires_at) WHERE status = 'pending';

-- =============================================================================
-- SUBSCRIPTIONS
-- =============================================================================
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    customer_id UUID NOT NULL REFERENCES customers(id),
    vehicle_id UUID REFERENCES vehicles(id),
    plan_type TEXT NOT NULL,  -- basic, plus, premium
    stripe_subscription_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, active, cancelled, past_due
    monthly_amount DECIMAL(10,2) NOT NULL,
    started_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- CUSTOMER CREDITS (from package purchases)
-- =============================================================================
CREATE TABLE customer_credits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    customer_id UUID NOT NULL REFERENCES customers(id),
    vehicle_id UUID REFERENCES vehicles(id),
    credit_type TEXT NOT NULL,  -- labor, parts, package
    amount_remaining DECIMAL(10,2) NOT NULL,
    amount_original DECIMAL(10,2) NOT NULL,
    stripe_session_id TEXT,
    expires_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- VEHICLE APPRAISALS (Buy/Sell)
-- =============================================================================
CREATE TABLE vehicle_appraisals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    vehicle_id UUID REFERENCES vehicles(id),
    vin CHAR(17) NOT NULL,
    customer_id UUID REFERENCES customers(id),
    condition_rating TEXT,  -- excellent, good, fair, poor
    estimated_value DECIMAL(10,2),
    purchase_price DECIMAL(10,2),
    list_price DECIMAL(10,2),
    sold_price DECIMAL(10,2),
    profit DECIMAL(10,2),
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, approved, listed, sold, rejected
    photos JSONB DEFAULT '[]',
    notes TEXT,
    listed_at TIMESTAMPTZ,
    sold_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- OUTBOX (transactional outbox for reliable delivery)
-- =============================================================================
CREATE TABLE outbox (
    id BIGSERIAL PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    published BOOLEAN DEFAULT FALSE,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_outbox_unpublished ON outbox (published, created_at) WHERE NOT published;

-- =============================================================================
-- IDEMPOTENCY CHECK function (for workers)
-- =============================================================================
CREATE OR REPLACE FUNCTION check_idempotency(key TEXT, OUT already_processed BOOLEAN)
AS $$
BEGIN
    SELECT EXISTS(SELECT 1 FROM events WHERE idempotency_key = key) INTO already_processed;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- UUID v7 helper (if not available in Postgres 16+)
-- =============================================================================
CREATE OR REPLACE FUNCTION uuid_generate_v7()
RETURNS UUID AS $$
DECLARE
    unix_ts_ms BYTEA;
    uuid_bytes BYTEA;
BEGIN
    unix_ts_ms = int8send((EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::BIGINT);
    uuid_bytes = uuid_bytes FROM gen_random_uuid();
    uuid_bytes = overlay(uuid_bytes PLACING unix_ts_ms FROM 1 FOR 6);
    uuid_bytes = set_byte(uuid_bytes, 6, (get_byte(uuid_bytes, 6) & 15 | 96));
    uuid_bytes = set_byte(uuid_bytes, 8, (get_byte(uuid_bytes, 8) & 63 | 128));
    RETURN encode(uuid_bytes, 'hex')::UUID;
END;
$$ LANGUAGE plpgsql;
