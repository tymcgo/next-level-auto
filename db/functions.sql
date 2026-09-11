-- db/functions.sql — Supabase stored procedures
-- These are called by tool_gateway.ts and the Python service

-- =============================================================================
-- create_repair_order — Creates an RO with line items and calculates totals
-- =============================================================================
CREATE OR REPLACE FUNCTION create_repair_order(
  p_vehicle_id UUID,
  p_customer_id UUID,
  p_description TEXT DEFAULT NULL,
  p_line_items JSONB DEFAULT '[]',
  p_notes TEXT DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  v_ro_id UUID;
  v_ro_number TEXT;
  v_subtotal NUMERIC := 0;
  v_item JSONB;
  v_labor_rate NUMERIC := 125.00;
BEGIN
  -- Generate RO number: RO-YYYYMMDD-XXXX
  v_ro_number := 'RO-' || TO_CHAR(NOW(), 'YYYYMMDD') || '-' || LPAD(NEXTVAL('ro_number_seq')::TEXT, 4, '0');

  -- Calculate subtotal from line items
  FOR v_item IN SELECT * FROM jsonb_array_elements(p_line_items)
  LOOP
    v_subtotal := v_subtotal + 
      ((v_item->>'labor_hours')::NUMERIC * v_labor_rate) + 
      (v_item->>'parts_cost')::NUMERIC;
  END LOOP;

  -- Insert RO
  INSERT INTO repair_orders (
    ro_number, vehicle_id, customer_id, status, 
    total_labor, total_parts, total_amount, description, notes,
    created_at, updated_at
  ) VALUES (
    v_ro_number, p_vehicle_id, p_customer_id, 'draft',
    v_subtotal * 0.6, v_subtotal * 0.4, v_subtotal,
    p_description, p_notes,
    NOW(), NOW()
  ) RETURNING id INTO v_ro_id;

  RETURN v_ro_id;
END;
$$;

-- Sequence for RO numbers
CREATE SEQUENCE IF NOT EXISTS ro_number_seq START 1;

-- =============================================================================
-- create_estimate — Creates an estimate with approval token
-- =============================================================================
CREATE OR REPLACE FUNCTION create_estimate(
  p_ro_id UUID DEFAULT NULL,
  p_vehicle_id UUID,
  p_customer_id UUID,
  p_line_items JSONB DEFAULT '[]',
  p_notes TEXT DEFAULT NULL,
  p_expires_in_days INT DEFAULT 7
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  v_estimate_id UUID;
  v_token TEXT;
  v_subtotal NUMERIC := 0;
  v_tax NUMERIC := 0;
  v_total NUMERIC := 0;
  v_item JSONB;
  v_labor_rate NUMERIC := 125.00;
  v_tax_rate NUMERIC := 0.05;
BEGIN
  -- Calculate totals
  FOR v_item IN SELECT * FROM jsonb_array_elements(p_line_items)
  LOOP
    v_subtotal := v_subtotal + 
      ((v_item->>'labor_hours')::NUMERIC * v_labor_rate) + 
      (v_item->>'parts_cost')::NUMERIC;
  END LOOP;

  v_tax := v_subtotal * v_tax_rate;
  v_total := v_subtotal + v_tax;

  -- Generate approval token
  v_token = encode(gen_random_bytes(16), 'hex');

  INSERT INTO estimates (
    ro_id, vehicle_id, customer_id, status,
    line_items, subtotal, tax, total,
    customer_approval_token, expires_at,
    created_at, updated_at
  ) VALUES (
    p_ro_id, p_vehicle_id, p_customer_id, 'draft',
    p_line_items, v_subtotal, v_tax, v_total,
    v_token, NOW() + (p_expires_in_days || ' days')::INTERVAL,
    NOW(), NOW()
  ) RETURNING id INTO v_estimate_id;

  RETURN v_estimate_id;
END;
$$;

-- =============================================================================
-- order_parts — Creates part records and updates RO
-- =============================================================================
CREATE OR REPLACE FUNCTION order_parts(
  p_supplier TEXT,
  p_parts JSONB DEFAULT '[]',
  p_ro_id UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
  v_part JSONB;
  v_order_refs JSONB := '[]';
BEGIN
  FOR v_part IN SELECT * FROM jsonb_array_elements(p_parts)
  LOOP
    INSERT INTO parts (
      ro_id, name, sku, supplier, quantity, unit_cost, status,
      created_at
    ) VALUES (
      p_ro_id,
      v_part->>'name',
      v_part->>'sku',
      p_supplier,
      COALESCE((v_part->>'quantity')::INT, 1),
      COALESCE((v_part->>'target_price')::NUMERIC, 0),
      'ordered',
      NOW()
    );
  END LOOP;

  -- Update RO status if provided
  IF p_ro_id IS NOT NULL THEN
    UPDATE repair_orders SET status = 'waiting_parts' WHERE id = p_ro_id;
  END IF;

  RETURN jsonb_build_object('success', true, 'count', jsonb_array_length(p_parts));
END;
$$;

-- =============================================================================
-- list_vehicle — Creates vehicle listing from appraisal
-- =============================================================================
CREATE OR REPLACE FUNCTION list_vehicle(
  p_vehicle_id UUID,
  p_list_price NUMERIC,
  p_description TEXT DEFAULT NULL,
  p_photos JSONB DEFAULT '[]',
  p_condition_notes TEXT DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  v_appraisal_id UUID;
BEGIN
  INSERT INTO vehicle_appraisals (
    vehicle_id, list_price, description, photos, condition_notes,
    status, created_at, updated_at
  ) VALUES (
    p_vehicle_id, p_list_price, p_description, p_photos, p_condition_notes,
    'listed', NOW(), NOW()
  ) RETURNING id INTO v_appraisal_id;

  -- Update vehicle status
  UPDATE vehicles SET metadata = jsonb_set(
    COALESCE(metadata, '{}'::jsonb),
    '{status}',
    '"for_sale"'::jsonb
  ) WHERE id = p_vehicle_id;

  RETURN v_appraisal_id;
END;
$$;

-- =============================================================================
-- check_idempotency — Checks if an idempotency key already exists
-- =============================================================================
CREATE OR REPLACE FUNCTION check_idempotency(p_key TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN EXISTS(SELECT 1 FROM events WHERE idempotency_key = p_key);
END;
$$;

-- =============================================================================
-- update_estimate_status — Status transition with validation
-- =============================================================================
CREATE OR REPLACE FUNCTION update_estimate_status(
  p_estimate_id UUID,
  p_new_status TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
  v_current TEXT;
  v_valid_transitions JSONB := '{
    "draft": ["sent", "cancelled"],
    "sent": ["approved", "declined", "expired"],
    "approved": ["cancelled"],
    "declined": ["sent"],
    "expired": ["sent"]
  }';
BEGIN
  SELECT status INTO v_current FROM estimates WHERE id = p_estimate_id;
  IF v_current IS NULL THEN RETURN FALSE; END IF;

  -- Validate transition
  IF NOT v_valid_transitions->v_current ? p_new_status THEN
    RAISE EXCEPTION 'Invalid transition from % to %', v_current, p_new_status;
  END IF;

  UPDATE estimates SET 
    status = p_new_status, 
    updated_at = NOW(),
    approved_at = CASE WHEN p_new_status = 'approved' THEN NOW() ELSE approved_at END
  WHERE id = p_estimate_id;

  RETURN TRUE;
END;
$$;
