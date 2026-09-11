-- Next Level Auto — Custom Shop Management System
-- Migration 002: replaces mock shop tools with real shop management

-- Employees (technicians, advisors, admins)
CREATE TABLE IF NOT EXISTS employees (
    id BIGSERIAL PRIMARY KEY,
    employee_code TEXT UNIQUE NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('technician', 'advisor', 'admin', 'parts_manager')),
    email TEXT UNIQUE,
    phone TEXT,
    hourly_rate_cents INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Customers
CREATE TABLE IF NOT EXISTS customers (
    id BIGSERIAL PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    address_line1 TEXT,
    address_line2 TEXT,
    city TEXT,
    state TEXT,
    zip TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vehicles
CREATE TABLE IF NOT EXISTS vehicles (
    id BIGSERIAL PRIMARY KEY,
    vin TEXT NOT NULL,
    customer_id BIGINT REFERENCES customers(id),
    year INTEGER,
    make TEXT,
    model TEXT,
    trim TEXT,
    color TEXT,
    license_plate TEXT,
    last_mileage INTEGER,
    notes TEXT,
    created_at TIMESTAMPTZ UNIQUE
);

-- Suppliers (parts sources)
CREATE TABLE IF NOT EXISTS suppliers (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    contact_name TEXT,
    email TEXT,
    phone TEXT,
    address TEXT,
    account_number TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Inventory (parts on hand)
CREATE TABLE IF NOT EXISTS inventory (
    id BIGSERIAL PRIMARY KEY,
    part_number TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    supplier_id BIGINT REFERENCES suppliers(id),
    quantity_on_hand INTEGER DEFAULT 0,
    quantity_reserved INTEGER DEFAULT 0,
    reorder_level INTEGER DEFAULT 5,
    unit_cost_cents INTEGER DEFAULT 0,
    retail_price_cents INTEGER DEFAULT 0,
    location TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Work Orders (the core RO)
CREATE TABLE IF NOT EXISTS work_orders (
    id BIGSERIAL PRIMARY KEY,
    ro_number TEXT UNIQUE NOT NULL,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    vehicle_id BIGINT REFERENCES vehicles(id),
    employee_id BIGINT REFERENCES employees(id),
    -- Status: draft → approved → in_progress → waiting_parts → completed → invoiced → closed
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'in_progress', 'waiting_parts', 'completed', 'invoiced', 'closed', 'cancelled')),
    customer_concern TEXT,
    technician_diagnosis TEXT,
    total_labor_cents INTEGER DEFAULT 0,
    total_parts_cents INTEGER DEFAULT 0,
    total_tax_cents INTEGER DEFAULT 0,
    total_cents INTEGER DEFAULT 0,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    due_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    notes TEXT,
    idempotency_key TEXT UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Work Order Line Items (labor + parts)
CREATE TABLE IF NOT EXISTS wo_line_items (
    id BIGSERIAL PRIMARY KEY,
    work_order_id BIGINT NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
    line_type TEXT NOT NULL CHECK (line_type IN ('labor', 'part', 'sublet', 'fee', 'discount')),
    description TEXT NOT NULL,
    -- For labor: employee_id + hours
    employee_id BIGINT REFERENCES employees(id),
    labor_hours NUMERIC(5,1) DEFAULT 0,
    labor_rate_cents INTEGER DEFAULT 0,
    -- For parts: inventory_id + quantity
    inventory_id BIGINT REFERENCES inventory(id),
    quantity NUMERIC(8,2) DEFAULT 1,
    unit_cost_cents INTEGER DEFAULT 0,
    unit_retail_cents INTEGER DEFAULT 0,
    -- Computed
    subtotal_cents INTEGER DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Time Clock (tech clock in/out on ROs)
CREATE TABLE IF NOT EXISTS time_clock (
    id BIGSERIAL PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES employees(id),
    work_order_id BIGINT REFERENCES work_orders(id),
    clock_in TIMESTAMPTZ NOT NULL,
    clock_out TIMESTAMPTZ,
    minutes_worked INTEGER DEFAULT 0,
    billable_minutes INTEGER DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Supplier Orders (parts POs)
CREATE TABLE IF NOT EXISTS supplier_orders (
    id BIGSERIAL PRIMARY KEY,
    po_number TEXT UNIQUE NOT NULL,
    supplier_id BIGINT NOT NULL REFERENCES suppliers(id),
    work_order_id BIGINT REFERENCES work_orders(id),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'ordered', 'partial', 'received', 'cancelled')),
    total_cents INTEGER DEFAULT 0,
    ordered_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Supplier Order Line Items
CREATE TABLE IF NOT EXISTS supplier_order_items (
    id BIGSERIAL PRIMARY KEY,
    supplier_order_id BIGINT NOT NULL REFERENCES supplier_orders(id) ON DELETE CASCADE,
    inventory_id BIGINT REFERENCES inventory(id),
    part_number TEXT NOT NULL,
    description TEXT,
    quantity_ordered INTEGER DEFAULT 1,
    quantity_received INTEGER DEFAULT 0,
    unit_cost_cents INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vehicle Appraisals (buy/sell)
CREATE TABLE IF NOT EXISTS appraisals (
    id BIGSERIAL PRIMARY KEY,
    vehicle_id BIGINT REFERENCES vehicles(id),
    customer_id BIGINT REFERENCES customers(id),
    appraised_by BIGINT REFERENCES employees(id),
    condition TEXT NOT NULL CHECK (condition IN ('excellent', 'good', 'fair', 'poor')),
    book_value_cents INTEGER DEFAULT 0,
    offer_cents INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected', 'expired')),
    notes TEXT,
    appraised_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

-- Vehicle Listings (for sale)
CREATE TABLE IF NOT EXISTS vehicle_listings (
    id BIGSERIAL PRIMARY KEY,
    vehicle_id BIGINT NOT NULL REFERENCES vehicles(id),
    appraisal_id BIGINT REFERENCES appraisals(id),
    asking_price_cents INTEGER NOT NULL,
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'listed', 'sold', 'withdrawn')),
    listed_at TIMESTAMPTZ,
    sold_at TIMESTAMPTZ,
    sold_price_cents INTEGER,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_work_orders_status ON work_orders(status);
CREATE INDEX IF NOT EXISTS idx_work_orders_customer ON work_orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_work_orders_vehicle ON work_orders(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_wo_line_items_wo ON wo_line_items(work_order_id);
CREATE INDEX IF NOT EXISTS idx_vehicles_vin ON vehicles(vin);
CREATE INDEX IF NOT EXISTS idx_time_clock_emp ON time_clock(employee_id, clock_out);
CREATE INDEX IF NOT EXISTS idx_inventory_part ON inventory(part_number);
CREATE INDEX IF NOT EXISTS idx_customer_phone ON customers(phone);
CREATE INDEX IF NOT EXISTS idx_customer_email ON customers(email);

-- RLS
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE vehicles ENABLE ROW LEVEL SECURITY;
ALTER TABLE suppliers ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory ENABLE ROW LEVEL SECURITY;
ALTER TABLE work_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE wo_line_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE time_clock ENABLE ROW LEVEL SECURITY;
ALTER TABLE supplier_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE supplier_order_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE appraisals ENABLE ROW LEVEL SECURITY;
ALTER TABLE vehicle_listings ENABLE ROW LEVEL SECURITY;

CREATE POLICY service_all ON employees FOR ALL USING (true);
CREATE POLICY service_all ON customers FOR ALL USING (true);
CREATE POLICY service_all ON vehicles FOR ALL USING (true);
CREATE POLICY service_all ON suppliers FOR ALL USING (true);
CREATE POLICY service_all ON inventory FOR ALL USING (true);
CREATE POLICY service_all ON work_orders FOR ALL USING (true);
CREATE POLICY service_all ON wo_line_items FOR ALL USING (true);
CREATE POLICY service_all ON time_clock FOR ALL USING (true);
CREATE POLICY service_all ON supplier_orders FOR ALL USING (true);
CREATE POLICY service_all ON supplier_order_items FOR ALL USING (true);
CREATE POLICY service_all ON appraisals FOR ALL USING (true);
CREATE POLICY service_all ON vehicle_listings FOR ALL USING (true);

-- Functions
-- Auto-generate RO number
CREATE OR REPLACE FUNCTION generate_ro_number()
RETURNS TEXT AS $$
DECLARE
    next_num INTEGER;
    ro_num TEXT;
BEGIN
    SELECT COALESCE(MAX(CAST(SUBSTRING(ro_number, 3) AS INTEGER)), 0) + 1
    INTO next_num
    FROM work_orders
    WHERE ro_number ~ '^RO[0-9]+$';
    ro_num := 'RO' || LPAD(next_num::TEXT, 6, '0');
    RETURN ro_num;
END;
$$ LANGUAGE plpgsql;

-- Compute work order totals from line items
CREATE OR REPLACE FUNCTION compute_work_order_total(wo_id BIGINT)
RETURNS INTEGER AS $$
DECLARE
    total INTEGER;
BEGIN
    SELECT COALESCE(SUM(subtotal_cents), 0)
    INTO total
    FROM wo_line_items
    WHERE work_order_id = wo_id;
    RETURN total;
END;
$$ LANGUAGE plpgsql;

-- Trigger: auto-set RO number on insert
CREATE OR REPLACE FUNCTION set_ro_number()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.ro_number IS NULL THEN
        NEW.ro_number := generate_ro_number();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_set_ro_number
    BEFORE INSERT ON work_orders
    FOR EACH ROW
    EXECUTE FUNCTION set_ro_number();

-- Trigger: update work_order total when line items change
CREATE OR REPLACE FUNCTION update_work_order_total()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE work_orders
    SET total_cents = compute_work_order_total(NEW.work_order_id),
        total_labor_cents = (SELECT COALESCE(SUM(subtotal_cents), 0) FROM wo_line_items WHERE work_order_id = NEW.work_order_id AND line_type = 'labor'),
        total_parts_cents = (SELECT COALESCE(SUM(subtotal_cents), 0) FROM wo_line_items WHERE work_order_id = NEW.work_order_id AND line_type = 'part')
    WHERE id = NEW.work_order_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_wo_total
    AFTER INSERT OR UPDATE OR DELETE ON wo_line_items
    FOR EACH ROW
    EXECUTE FUNCTION update_work_order_total();
