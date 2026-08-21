from datetime import date, timedelta

TODAY = date.today()

ADMIN_EMAILS = {"erdi.aydin@yemeksepeti.com", "erdi@opex.com"}

MOCK_USER_SUPPLIERS = {
    "erdi@opex.com": ["Eti", "Ülker", "Pınar", "Coca Cola"],
    "erdi.aydin@yemeksepeti.com": ["Eti", "Ülker", "Pınar", "Coca Cola", "Pepsi"],
    "pepsi@demo.com": ["Pepsi"],
    "eti@demo.com": ["Eti"],
    "ulker@demo.com": ["Ülker"],
}

MOCK_SUPPLIER_ACCESS = [
    {
        "email": email,
        "supplier_names": suppliers,
        "warehouse_names": [],
        "all_warehouses": True,
        "active": True,
        "locale": "tr",
    }
    for email, suppliers in MOCK_USER_SUPPLIERS.items()
]

MOCK_WAREHOUSES = [
    {"warehouse_name": "Ankara DC"},
    {"warehouse_name": "İstanbul Avrupa DC"},
    {"warehouse_name": "İstanbul Anadolu DC"},
    {"warehouse_name": "İzmir DC"},
]

# Test boyunca her tedarikçi/depo kombinasyonunda PO görülebilsin.
MOCK_PURCHASE_ORDERS = [
    {"po_number":"PO-PEPSI-ANK-001","supplier_name":"Pepsi","warehouse_name":"Ankara DC","delivery_date":str(TODAY + timedelta(days=6)),"status":"OPEN","sku_count":195,"pallet_count":18,"source":"MOCK"},
    {
        "po_number": "PO-ETI-ANK-001",
        "supplier_name": "Eti",
        "warehouse_name": "Ankara DC",
        "delivery_date": str(TODAY + timedelta(days=7)),
        "status": "OPEN",
        "sku_count": 350,
    },
    {
        "po_number": "PO-ETI-EUR-002",
        "supplier_name": "Eti",
        "warehouse_name": "İstanbul Avrupa DC",
        "delivery_date": str(TODAY + timedelta(days=8)),
        "status": "OPEN",
        "sku_count": 240,
    },
    {
        "po_number": "PO-ETI-ASIA-003",
        "supplier_name": "Eti",
        "warehouse_name": "İstanbul Anadolu DC",
        "delivery_date": str(TODAY + timedelta(days=9)),
        "status": "OPEN",
        "sku_count": 190,
    },
    {
        "po_number": "PO-ULKER-EUR-001",
        "supplier_name": "Ülker",
        "warehouse_name": "İstanbul Avrupa DC",
        "delivery_date": str(TODAY + timedelta(days=7)),
        "status": "OPEN",
        "sku_count": 420,
    },
    {
        "po_number": "PO-PINAR-IZM-001",
        "supplier_name": "Pınar",
        "warehouse_name": "İzmir DC",
        "delivery_date": str(TODAY + timedelta(days=8)),
        "status": "OPEN",
        "sku_count": 180,
    },
    {
        "po_number": "PO-CCI-ANK-001",
        "supplier_name": "Coca Cola",
        "warehouse_name": "Ankara DC",
        "delivery_date": str(TODAY + timedelta(days=9)),
        "status": "OPEN",
        "sku_count": 210,
    },
]

MOCK_SLOT_CAPACITY = []
for offset in range(0, 31):
    date_key = str(TODAY + timedelta(days=offset))
    for warehouse in [row["warehouse_name"] for row in MOCK_WAREHOUSES]:
        for hour in range(6, 24):
            end_hour = 0 if hour == 23 else hour + 1
            slot_name = f"{hour:02d}:00 - {end_hour:02d}:00"
            MOCK_SLOT_CAPACITY.append(
                {
                    "warehouse_name": warehouse,
                    "date": date_key,
                    "slot": slot_name,
                    "max_pallet": 40,
                    "max_sku": 500,
                    "remaining_pallet": 40,
                    "remaining_sku": 500,
                }
            )

MOCK_RESERVATIONS = []
MOCK_SLOT_HOLDS = []
MOCK_SUPPLIER_CAPACITY = []
MOCK_SUPPLIER_DAILY_LIMITS = []
MOCK_AUDIT_LOG = []
MOCK_NOTIFICATION_OUTBOX = []

DOCKOS_SETTINGS = {
    "supplier_cancel_hours": 24,
    "deleted_slots": [],
}
