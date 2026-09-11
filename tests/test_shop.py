"""Tests for Shop Management System — async tests."""
import pytest
import os
import pytest_asyncio
import asyncio
import uuid

from src.shop import ShopManagementSystem, ShopManagementError

# Generate unique prefix per test run to avoid collisions
RUN_ID = uuid.uuid4().hex[:8]
COUNTER = 0

def unique_code(prefix: str) -> str:
    global COUNTER
    COUNTER += 1
    return f"{prefix}-{RUN_ID}-{COUNTER}"

def unique_phone() -> str:
    """Generate a 10-digit phone number with no dashes/letters."""
    # Use uuid to avoid counter synchronization issues
    return f"{int(uuid.uuid4().hex[:8], 16):010d}"[-10:]

def unique_vin() -> str:
    return f"WBA3A5C55CF{RUN_ID}{COUNTER:04d}"


# Skip if no Supabase configured
pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_URL"),
    reason="Supabase not configured"
)


@pytest_asyncio.fixture
async def shop():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    s = ShopManagementSystem(url, key)
    yield s
    await s.close()


@pytest.mark.asyncio
class TestShopManagement:
    async def test_create_employee(self, shop):
        emp = await shop.create_employee(
            employee_code=unique_code("TECH"),
            first_name="John",
            last_name="Doe",
            role="technician",
            email=f"john-{RUN_ID}@shop.com",
            hourly_rate_cents=2500,
        )
        assert emp["first_name"] == "John"
        assert emp["role"] == "technician"
        assert emp["hourly_rate_cents"] == 2500

    async def test_create_customer(self, shop):
        cust = await shop.create_customer(
            first_name="Jane",
            last_name="Smith",
            phone=unique_phone(),
        )
        assert cust["first_name"] == "Jane"
        assert cust["phone"] is not None

    async def test_create_vehicle(self, shop):
        cust = await shop.create_customer(
            first_name="Vehicle",
            last_name="Owner",
        )
        veh = await shop.create_vehicle(
            vin=unique_vin(),
            customer_id=cust["id"],
            year=2015,
            make="BMW",
            model="328i",
            mileage=65000,
        )
        assert veh["vin"] is not None
        assert veh["year"] == 2015

    async def test_create_work_order(self, shop):
        cust = await shop.create_customer(first_name="RO", last_name="Test")
        veh = await shop.create_vehicle(vin=unique_vin(), customer_id=cust["id"])
        wo = await shop.create_work_order(
            customer_id=cust["id"],
            vehicle_id=veh["id"],
            customer_concern="Check engine light",
            technician_diagnosis="Diagnosing...",
        )
        assert wo["ro_number"].startswith("RO")
        assert wo["status"] == "draft"

    async def test_add_labor_line(self, shop):
        cust = await shop.create_customer(first_name="Labor", last_name="Test")
        veh = await shop.create_vehicle(vin=unique_vin(), customer_id=cust["id"])
        wo = await shop.create_work_order(
            customer_id=cust["id"],
            vehicle_id=veh["id"],
        )
        emp = await shop.create_employee(
            employee_code=unique_code("TECH"),
            first_name="Tech",
            last_name="Two",
            role="technician",
            hourly_rate_cents=15000,
        )
        line = await shop.add_labor_line(
            work_order_id=wo["id"],
            employee_id=emp["id"],
            description="Diagnose engine light",
            hours=1.5,
            rate_cents=15000,
        )
        assert line["line_type"] == "labor"
        assert line["subtotal_cents"] == 22500  # 1.5 * 15000

    async def test_create_part_and_add_to_wo(self, shop):
        cust = await shop.create_customer(first_name="Parts", last_name="Test")
        veh = await shop.create_vehicle(vin=unique_vin(), customer_id=cust["id"])
        wo = await shop.create_work_order(
            customer_id=cust["id"],
            vehicle_id=veh["id"],
        )
        part = await shop.create_part(
            part_number=unique_code("BRK"),
            description="Front Brake Pads",
            quantity_on_hand=20,
            unit_cost_cents=4500,
            retail_price_cents=8000,
        )
        line = await shop.add_part_line(
            work_order_id=wo["id"],
            inventory_id=part["id"],
            quantity=1,
        )
        assert line["line_type"] == "part"
        assert line["subtotal_cents"] == 8000

    async def test_work_order_total_updates(self, shop):
        cust = await shop.create_customer(first_name="Total", last_name="Test")
        veh = await shop.create_vehicle(vin=unique_vin(), customer_id=cust["id"])
        wo = await shop.create_work_order(
            customer_id=cust["id"],
            vehicle_id=veh["id"],
        )
        emp = await shop.create_employee(
            employee_code=unique_code("TECH"),
            first_name="Tech",
            last_name="Three",
            role="technician",
            hourly_rate_cents=15000,
        )
        await shop.add_labor_line(
            work_order_id=wo["id"],
            employee_id=emp["id"],
            description="Test labor",
            hours=2.0,
            rate_cents=15000,
        )
        wo_updated = await shop.get_work_order(wo["id"])
        assert wo_updated["total_cents"] == 30000

    async def test_clock_in_out(self, shop):
        emp = await shop.create_employee(
            employee_code=unique_code("TECH"),
            first_name="Clock",
            last_name="Test",
            role="technician",
        )
        tc = await shop.clock_in(employee_id=emp["id"])
        assert tc["clock_in"] is not None
        assert tc["clock_out"] is None

    async def test_inventory_reservation(self, shop):
        part = await shop.create_part(
            part_number=unique_code("OIL"),
            description="Oil Filter",
            quantity_on_hand=10,
            reorder_level=5,
        )
        await shop.reserve_inventory(part["id"], 3)
        updated = await shop.get_part(part["id"])
        assert updated["quantity_reserved"] == 3

    async def test_insufficient_inventory_raises(self, shop):
        part = await shop.create_part(
            part_number=unique_code("RARE"),
            description="Rare Part",
            quantity_on_hand=1,
        )
        with pytest.raises(ShopManagementError):
            await shop.reserve_inventory(part["id"], 5)

    async def test_supplier_order_flow(self, shop):
        sup = await shop.create_supplier(
            name=f"Auto Parts Co {RUN_ID}",
            email=f"orders-{RUN_ID}@autoparts.com",
        )
        po = await shop.create_supplier_order(
            supplier_id=sup["id"],
            notes="Urgent order",
        )
        assert po["po_number"].startswith("PO")
        assert po["status"] == "pending"
        po_ordered = await shop.order_supplier_order(po["id"])
        assert po_ordered["status"] == "ordered"

    async def test_appraisal_and_listing(self, shop):
        cust = await shop.create_customer(first_name="Appraisal", last_name="Test")
        veh = await shop.create_vehicle(vin=unique_vin(), customer_id=cust["id"])
        emp = await shop.create_employee(
            employee_code=unique_code("ADV"),
            first_name="Sales",
            last_name="Advisor",
            role="advisor",
        )
        appr = await shop.create_appraisal(
            vehicle_id=veh["id"],
            customer_id=cust["id"],
            appraised_by=emp["id"],
            condition="good",
            book_value_cents=1500000,
            offer_cents=1200000,
        )
        assert appr["status"] == "pending"
        listing = await shop.create_vehicle_listing(
            vehicle_id=veh["id"],
            asking_price_cents=1400000,
            appraisal_id=appr["id"],
        )
        assert listing["status"] == "draft"
        published = await shop.publish_listing(listing["id"])
        assert published["status"] == "listed"

    async def test_find_customer_by_phone(self, shop):
        phone = unique_phone()
        cust = await shop.create_customer(
            first_name="Find",
            last_name="Phone",
            phone=phone,
        )
        found = await shop.find_customer_by_phone(phone)
        assert found is not None
        assert found["first_name"] == "Find"
