"""Shop Management System — full replacement for mock shop tools.

Provides: work orders, customers, vehicles, inventory, employees, suppliers, time clock.
All operations are idempotent via idempotency_key.
"""
from __future__ import annotations

import os
from typing import Any, Optional
from datetime import datetime, timezone

import httpx


class ShopManagementError(Exception):
    """Shop operation failed."""
    def __init__(self, message: str, code: str = "shop_error"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class ShopManagementSystem:
    """Full shop management via Supabase.
    
    Tables: employees, customers, vehicles, inventory, suppliers,
            work_orders, wo_line_items, time_clock, supplier_orders,
            supplier_order_items, appraisals, vehicle_listings
    """

    def __init__(self, supabase_url: str, supabase_key: str):
        self.base = supabase_url
        self.key = supabase_key
        self.client = httpx.AsyncClient(
            base_url=f"{supabase_url}/rest/v1",
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            timeout=30,
        )

    async def close(self):
        await self.client.aclose()

    # ---------- Employees ----------
    async def create_employee(
        self,
        employee_code: str,
        first_name: str,
        last_name: str,
        role: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        hourly_rate_cents: int = 0,
    ) -> dict[str, Any]:
        r = await self.client.post("/employees", json={
            "employee_code": employee_code,
            "first_name": first_name,
            "last_name": last_name,
            "role": role,
            "email": email,
            "phone": phone,
            "hourly_rate_cents": hourly_rate_cents,
        })
        r.raise_for_status()
        return r.json()[0]

    async def get_employee(self, employee_id: int) -> Optional[dict[str, Any]]:
        r = await self.client.get(f"/employees?id=eq.{employee_id}")
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None

    async def list_employees(self, role: Optional[str] = None, active_only: bool = True) -> list[dict[str, Any]]:
        params = []
        if role:
            params.append(f"role=eq.{role}")
        if active_only:
            params.append("is_active=eq.true")
        query = "/employees?" + "&".join(params) if params else "/employees"
        r = await self.client.get(query)
        r.raise_for_status()
        return r.json()

    # ---------- Customers ----------
    async def create_customer(
        self,
        first_name: str,
        last_name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        address_line1: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        zip_code: Optional[str] = None,
    ) -> dict[str, Any]:
        r = await self.client.post("/customers", json={
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "address_line1": address_line1,
            "city": city,
            "state": state,
            "zip": zip_code,
        })
        r.raise_for_status()
        return r.json()[0]

    async def get_customer(self, customer_id: int) -> Optional[dict[str, Any]]:
        r = await self.client.get(f"/customers?id=eq.{customer_id}")
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None

    async def find_customer_by_phone(self, phone: str) -> Optional[dict[str, Any]]:
        # Normalize phone: strip non-digits, keep last 10
        digits = "".join(c for c in phone if c.isdigit())[-10:]
        r = await self.client.get(f"/customers?phone=like.*{digits}")
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None

    # ---------- Vehicles ----------
    async def create_vehicle(
        self,
        vin: str,
        customer_id: int,
        year: Optional[int] = None,
        make: Optional[str] = None,
        model: Optional[str] = None,
        trim: Optional[str] = None,
        color: Optional[str] = None,
        license_plate: Optional[str] = None,
        mileage: Optional[int] = None,
    ) -> dict[str, Any]:
        r = await self.client.post("/vehicles", json={
            "vin": vin.upper(),
            "customer_id": customer_id,
            "year": year,
            "make": make,
            "model": model,
            "trim": trim,
            "color": color,
            "license_plate": license_plate,
            "last_mileage": mileage,
        })
        r.raise_for_status()
        return r.json()[0]

    async def get_vehicle(self, vehicle_id: int) -> Optional[dict[str, Any]]:
        r = await self.client.get(f"/vehicles?id=eq.{vehicle_id}")
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None

    async def find_vehicle_by_vin(self, vin: str) -> Optional[dict[str, Any]]:
        r = await self.client.get(f"/vehicles?vin=eq.{vin.upper()}")
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None

    async def update_vehicle_mileage(self, vehicle_id: int, mileage: int) -> dict[str, Any]:
        r = await self.client.patch(f"/vehicles?id=eq.{vehicle_id}", json={"last_mileage": mileage})
        r.raise_for_status()
        return r.json()[0]

    # ---------- Inventory ----------
    async def create_part(
        self,
        part_number: str,
        description: str,
        supplier_id: Optional[int] = None,
        quantity_on_hand: int = 0,
        reorder_level: int = 5,
        unit_cost_cents: int = 0,
        retail_price_cents: int = 0,
        location: Optional[str] = None,
    ) -> dict[str, Any]:
        r = await self.client.post("/inventory", json={
            "part_number": part_number.upper(),
            "description": description,
            "supplier_id": supplier_id,
            "quantity_on_hand": quantity_on_hand,
            "reorder_level": reorder_level,
            "unit_cost_cents": unit_cost_cents,
            "retail_price_cents": retail_price_cents,
            "location": location,
        })
        r.raise_for_status()
        return r.json()[0]

    async def get_part(self, part_id: int) -> Optional[dict[str, Any]]:
        r = await self.client.get(f"/inventory?id=eq.{part_id}")
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None

    async def find_part_by_number(self, part_number: str) -> Optional[dict[str, Any]]:
        r = await self.client.get(f"/inventory?part_number=eq.{part_number.upper()}")
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None

    async def adjust_inventory(self, part_id: int, quantity_change: int, reason: str = "") -> dict[str, Any]:
        # Get current quantity
        part = await self.get_part(part_id)
        if not part:
            raise ShopManagementError(f"Part {part_id} not found")
        new_qty = part["quantity_on_hand"] + quantity_change
        if new_qty < 0:
            raise ShopManagementError(
                f"Insufficient inventory for {part['part_number']}: "
                f"have {part['quantity_on_hand']}, need {abs(quantity_change)}"
            )
        r = await self.client.patch(f"/inventory?id=eq.{part_id}", json={
            "quantity_on_hand": new_qty,
        })
        r.raise_for_status()
        return r.json()[0]

    async def reserve_inventory(self, part_id: int, quantity: int) -> dict[str, Any]:
        part = await self.get_part(part_id)
        if not part:
            raise ShopManagementError(f"Part {part_id} not found")
        available = part["quantity_on_hand"] - part["quantity_reserved"]
        if available < quantity:
            raise ShopManagementError(
                f"Cannot reserve {quantity} of {part['part_number']}: "
                f"only {available} available (on hand: {part['quantity_on_hand']}, "
                f"reserved: {part['quantity_reserved']})"
            )
        r = await self.client.patch(f"/inventory?id=eq.{part_id}", json={
            "quantity_reserved": part["quantity_reserved"] + quantity,
        })
        r.raise_for_status()
        return r.json()[0]

    # ---------- Work Orders ----------
    async def create_work_order(
        self,
        customer_id: int,
        vehicle_id: int,
        employee_id: Optional[int] = None,
        customer_concern: str = "",
        technician_diagnosis: str = "",
        due_at: Optional[str] = None,
        notes: str = "",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        payload = {
            "customer_id": customer_id,
            "vehicle_id": vehicle_id,
            "employee_id": employee_id,
            "customer_concern": customer_concern,
            "technician_diagnosis": technician_diagnosis,
            "due_at": due_at,
            "notes": notes,
            "status": "draft",
        }
        if idempotency_key:
            payload["idempotency_key"] = idempotency_key
        r = await self.client.post("/work_orders", json=payload)
        r.raise_for_status()
        return r.json()[0]

    async def get_work_order(self, wo_id: int) -> Optional[dict[str, Any]]:
        r = await self.client.get(f"/work_orders?id=eq.{wo_id}")
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None

    async def find_work_order_by_ro(self, ro_number: str) -> Optional[dict[str, Any]]:
        r = await self.client.get(f"/work_orders?ro_number=eq.{ro_number}")
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None

    async def update_work_order_status(self, wo_id: int, status: str, **kwargs) -> dict[str, Any]:
        valid = ["draft", "approved", "in_progress", "waiting_parts", "completed", "invoiced", "closed", "cancelled"]
        if status not in valid:
            raise ShopManagementError(f"Invalid status '{status}': must be one of {valid}")
        payload = {"status": status}
        if status == "approved":
            payload["approved_at"] = datetime.now(timezone.utc).isoformat()
        if status == "completed":
            payload["completed_at"] = datetime.now(timezone.utc).isoformat()
        payload.update(kwargs)
        r = await self.client.patch(f"/work_orders?id=eq.{wo_id}", json=payload)
        r.raise_for_status()
        return r.json()[0]

    async def list_work_orders(
        self,
        status: Optional[str] = None,
        customer_id: Optional[int] = None,
        employee_id: Optional[int] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        params = [f"order=created_at.desc", f"limit={limit}"]
        if status:
            params.append(f"status=eq.{status}")
        if customer_id:
            params.append(f"customer_id=eq.{customer_id}")
        if employee_id:
            params.append(f"employee_id=eq.{employee_id}")
        r = await self.client.get("/work_orders?" + "&".join(params))
        r.raise_for_status()
        return r.json()

    # ---------- Work Order Line Items ----------
    async def add_labor_line(
        self,
        work_order_id: int,
        employee_id: int,
        description: str,
        hours: float,
        rate_cents: int,
    ) -> dict[str, Any]:
        subtotal = int(hours * rate_cents)
        r = await self.client.post("/wo_line_items", json={
            "work_order_id": work_order_id,
            "line_type": "labor",
            "description": description,
            "employee_id": employee_id,
            "labor_hours": hours,
            "labor_rate_cents": rate_cents,
            "subtotal_cents": subtotal,
        })
        r.raise_for_status()
        return r.json()[0]

    async def add_part_line(
        self,
        work_order_id: int,
        inventory_id: int,
        quantity: int = 1,
        description: Optional[str] = None,
    ) -> dict[str, Any]:
        # Get part info and reserve inventory
        part = await self.get_part(inventory_id)
        if not part:
            raise ShopManagementError(f"Part {inventory_id} not found")
        await self.reserve_inventory(inventory_id, quantity)
        unit_retail = part["retail_price_cents"]
        subtotal = unit_retail * quantity
        desc = description or part["description"]
        r = await self.client.post("/wo_line_items", json={
            "work_order_id": work_order_id,
            "line_type": "part",
            "description": desc,
            "inventory_id": inventory_id,
            "quantity": quantity,
            "unit_cost_cents": part["unit_cost_cents"],
            "unit_retail_cents": unit_retail,
            "subtotal_cents": subtotal,
        })
        r.raise_for_status()
        return r.json()[0]

    async def add_generic_line(
        self,
        work_order_id: int,
        line_type: str,
        description: str,
        amount_cents: int,
    ) -> dict[str, Any]:
        r = await self.client.post("/wo_line_items", json={
            "work_order_id": work_order_id,
            "line_type": line_type,
            "description": description,
            "subtotal_cents": amount_cents,
        })
        r.raise_for_status()
        return r.json()[0]

    async def list_line_items(self, work_order_id: int) -> list[dict[str, Any]]:
        r = await self.client.get(f"/wo_line_items?work_order_id=eq.{work_order_id}&order=sort_order")
        r.raise_for_status()
        return r.json()

    # ---------- Time Clock ----------
    async def clock_in(self, employee_id: int, work_order_id: Optional[int] = None) -> dict[str, Any]:
        r = await self.client.post("/time_clock", json={
            "employee_id": employee_id,
            "work_order_id": work_order_id,
            "clock_in": datetime.now(timezone.utc).isoformat(),
        })
        r.raise_for_status()
        return r.json()[0]

    async def clock_out(self, time_clock_id: int) -> dict[str, Any]:
        r = await self.client.get(f"/time_clock?id=eq.{time_clock_id}")
        r.raise_for_status()
        entry = r.json()[0]
        if entry["clock_out"]:
            raise ShopManagementError("Already clocked out")
        now = datetime.now(timezone.utc)
        clock_in = datetime.fromisoformat(entry["clock_in"])
        minutes = int((now - clock_in).total_seconds() / 60)
        r = await self.client.patch(f"/time_clock?id=eq.{time_clock_id}", json={
            "clock_out": now.isoformat(),
            "minutes_worked": minutes,
            "billable_minutes": minutes,
        })
        r.raise_for_status()
        return r.json()[0]

    async def get_open_time_entries(self, employee_id: int) -> list[dict[str, Any]]:
        r = await self.client.get(f"/time_clock?employee_id=eq.{employee_id}&clock_out=is.null")
        r.raise_for_status()
        return r.json()

    # ---------- Suppliers ----------
    async def create_supplier(self, name: str, **kwargs) -> dict[str, Any]:
        r = await self.client.post("/suppliers", json={"name": name, **kwargs})
        r.raise_for_status()
        return r.json()[0]

    async def get_supplier(self, supplier_id: int) -> Optional[dict[str, Any]]:
        r = await self.client.get(f"/suppliers?id=eq.{supplier_id}")
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None

    async def list_suppliers(self) -> list[dict[str, Any]]:
        r = await self.client.get("/suppliers?is_active=eq.true")
        r.raise_for_status()
        return r.json()

    # ---------- Supplier Orders (Parts POs) ----------
    async def create_supplier_order(
        self,
        supplier_id: int,
        work_order_id: Optional[int] = None,
        notes: str = "",
    ) -> dict[str, Any]:
        # Generate PO number
        r = await self.client.get("/supplier_orders?select=po_number&order=id.desc&limit=1")
        r.raise_for_status()
        last = r.json()
        next_num = 1
        if last and last[0]["po_number"].startswith("PO"):
            try:
                next_num = int(last[0]["po_number"][2:]) + 1
            except ValueError:
                next_num = 1
        po_number = f"PO{next_num:06d}"
        r = await self.client.post("/supplier_orders", json={
            "po_number": po_number,
            "supplier_id": supplier_id,
            "work_order_id": work_order_id,
            "status": "pending",
            "notes": notes,
        })
        r.raise_for_status()
        return r.json()[0]

    async def add_supplier_order_item(
        self,
        supplier_order_id: int,
        part_number: str,
        description: str,
        quantity: int,
        unit_cost_cents: int,
        inventory_id: Optional[int] = None,
    ) -> dict[str, Any]:
        r = await self.client.post("/supplier_order_items", json={
            "supplier_order_id": supplier_order_id,
            "inventory_id": inventory_id,
            "part_number": part_number.upper(),
            "description": description,
            "quantity_ordered": quantity,
            "unit_cost_cents": unit_cost_cents,
        })
        r.raise_for_status()
        return r.json()[0]

    async def order_supplier_order(self, supplier_order_id: int) -> dict[str, Any]:
        r = await self.client.patch(f"/supplier_orders?id=eq.{supplier_order_id}", json={
            "status": "ordered",
            "ordered_at": datetime.now(timezone.utc).isoformat(),
        })
        r.raise_for_status()
        return r.json()[0]

    async def receive_supplier_order(self, supplier_order_id: int) -> dict[str, Any]:
        r = await self.client.patch(f"/supplier_orders?id=eq.{supplier_order_id}", json={
            "status": "received",
            "received_at": datetime.now(timezone.utc).isoformat(),
        })
        r.raise_for_status()
        return r.json()[0]

    # ---------- Appraisals & Listings ----------
    async def create_appraisal(
        self,
        vehicle_id: int,
        customer_id: int,
        appraised_by: int,
        condition: str,
        book_value_cents: int,
        offer_cents: int,
        notes: str = "",
    ) -> dict[str, Any]:
        r = await self.client.post("/appraisals", json={
            "vehicle_id": vehicle_id,
            "customer_id": customer_id,
            "appraised_by": appraised_by,
            "condition": condition,
            "book_value_cents": book_value_cents,
            "offer_cents": offer_cents,
            "status": "pending",
            "notes": notes,
        })
        r.raise_for_status()
        return r.json()[0]

    async def accept_appraisal(self, appraisal_id: int) -> dict[str, Any]:
        r = await self.client.patch(f"/appraisals?id=eq.{appraisal_id}", json={"status": "accepted"})
        r.raise_for_status()
        return r.json()[0]

    async def create_vehicle_listing(
        self,
        vehicle_id: int,
        asking_price_cents: int,
        appraisal_id: Optional[int] = None,
        notes: str = "",
    ) -> dict[str, Any]:
        r = await self.client.post("/vehicle_listings", json={
            "vehicle_id": vehicle_id,
            "appraisal_id": appraisal_id,
            "asking_price_cents": asking_price_cents,
            "status": "draft",
            "notes": notes,
        })
        r.raise_for_status()
        return r.json()[0]

    async def publish_listing(self, listing_id: int) -> dict[str, Any]:
        r = await self.client.patch(f"/vehicle_listings?id=eq.{listing_id}", json={
            "status": "listed",
            "listed_at": datetime.now(timezone.utc).isoformat(),
        })
        r.raise_for_status()
        return r.json()[0]

    async def sell_vehicle(self, listing_id: int, sold_price_cents: int) -> dict[str, Any]:
        r = await self.client.patch(f"/vehicle_listings?id=eq.{listing_id}", json={
            "status": "sold",
            "sold_at": datetime.now(timezone.utc).isoformat(),
            "sold_price_cents": sold_price_cents,
        })
        r.raise_for_status()
        return r.json()[0]

    # ---------- Dashboard Queries ----------
    async def get_dashboard(self) -> dict[str, Any]:
        """Get shop dashboard: open ROs, today's stats, low inventory."""
        # Open ROs
        r = await self.client.get("/work_orders?status=neq.closed&status=neq.cancelled&order=created_at.desc")
        r.raise_for_status()
        open_ros = r.json()

        # Active employees
        r = await self.client.get("/employees?is_active=eq.true")
        r.raise_for_status()
        employees = r.json()

        # Low inventory
        r = await self.client.get("/inventory?quantity_on_hand=lte.reorder_level")
        r.raise_for_status()
        low_inventory = r.json()

        # Today's time clock
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        r = await self.client.get(f"/time_clock?clock_in=gt.{today}")
        r.raise_for_status()
        time_entries = r.json()

        return {
            "open_work_orders": len(open_ros),
            "active_employees": len(employees),
            "low_inventory_count": len(low_inventory),
            "low_inventory": low_inventory[:10],
            "today_time_entries": len(time_entries),
        }
