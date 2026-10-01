"""One-time generator: creates 200 dummy contract PDFs plus contract and
approval-stage rows in SQLite, then indexes each PDF into ChromaDB.

Run once from the backend folder:
    .venv\\Scripts\\python.exe generate_contracts.py
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import random
import sqlite3

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

import chatbot

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data" / "contracts"
DATABASE = BASE_DIR / "documents.db"
CONTRACT_COUNT = int(os.getenv("CONTRACT_COUNT", "200"))

CONTRACT_TYPES = ["Master Service Agreement", "Statement of Work", "Non-Disclosure Agreement", "Vendor Agreement", "Renewal Contract"]
COMPANIES = [
    "Nimbus Retail Group", "Alderwood Manufacturing", "Cobalt Health Systems", "Prairie Logistics",
    "Beacon Financial Partners", "Summit Cloud Services", "Redwood Analytics", "Harborline Insurance",
    "Fernbridge Energy", "Meridian Telecom", "Ashcroft Materials", "Silverline Media",
    "Greenfield Foods", "Ironbrook Construction", "Willowmere Pharma", "Coastal Transit Authority",
    "Brightpeak Software", "Copper Canyon Mining", "Lakeside University", "Falcon Aerospace",
]
DEPARTMENTS = ["Legal", "Finance", "IT", "Procurement", "Sales"]
STAGE_DEFINITIONS = [
    ("Legal Review", "Legal", 3),
    ("Finance Review", "Finance", 4),
    ("Department Head Approval", None, 3),
    ("Final Sign-off", "Executive", 2),
]


def build_pdf(path: Path, contract_type: str, counterparty: str, department: str,
              effective_date: str, expiry_date: str) -> None:
    doc = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    lines = [
        f"{contract_type}",
        f"Between Contract Desk Inc. and {counterparty}",
        "",
        f"Effective Date: {effective_date}",
        f"Expiry Date: {expiry_date}",
        f"Responsible Department: {department}",
        "",
        "1. Scope of Work",
        f"The supplier, {counterparty}, will provide agreed services and deliverables to Contract",
        "Desk Inc. in accordance with the specifications documented in the attached exhibits.",
        "",
        "2. Payment Terms",
        "Invoices are due within 30 calendar days of receipt. Late payments accrue interest at",
        "1.5 percent per month. All fees are quoted in USD unless otherwise stated.",
        "",
        "3. Term and Termination",
        f"This agreement is effective from {effective_date} through {expiry_date}. Either party",
        "may terminate for convenience with 60 days written notice, or immediately for material",
        "breach that remains uncured after 15 days of written notice.",
        "",
        "4. Confidentiality",
        "Each party will protect the other's confidential information using the same degree of",
        "care it uses for its own confidential information, and no less than reasonable care.",
        "",
        "5. Renewal",
        "This agreement renews automatically for successive one-year terms unless either party",
        "provides notice of non-renewal at least 30 days before the expiry date.",
    ]
    text = doc.beginText(72, height - 72)
    text.setFont("Helvetica", 11)
    for line in lines:
        text.textLine(line)
    doc.drawText(text)
    doc.save()


def build_stage_schedule(status: str) -> list[dict]:
    now = datetime.now(timezone.utc)
    stages = []
    if status == "Pending":
        completed_count = random.randint(0, 2)
        cursor = now - timedelta(days=random.randint(10, 40))
    else:
        completed_count = len(STAGE_DEFINITIONS)
        cursor = now - timedelta(days=random.randint(90, 400))

    for index, (stage_name, fixed_department, expected_days) in enumerate(STAGE_DEFINITIONS):
        department = fixed_department or random.choice(DEPARTMENTS)
        if index < completed_count:
            entered_at = cursor
            actual_days = expected_days + random.choice([-1, 0, 0, 1, 2, 5])
            completed_at = entered_at + timedelta(days=max(actual_days, 1))
            stages.append({
                "stage_order": index,
                "stage_name": stage_name,
                "assigned_department": department,
                "expected_days": expected_days,
                "entered_at": entered_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "stage_status": "Completed",
            })
            cursor = completed_at
        elif index == completed_count and status == "Pending":
            entered_at = cursor
            stages.append({
                "stage_order": index,
                "stage_name": stage_name,
                "assigned_department": department,
                "expected_days": expected_days,
                "entered_at": entered_at.isoformat(),
                "completed_at": None,
                "stage_status": "In Progress",
            })
        else:
            stages.append({
                "stage_order": index,
                "stage_name": stage_name,
                "assigned_department": department,
                "expected_days": expected_days,
                "entered_at": None,
                "completed_at": None,
                "stage_status": "Not Started",
            })
    return stages


def initialize_contract_tables(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS contracts (
            contract_id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            contract_type TEXT NOT NULL,
            counterparty TEXT NOT NULL,
            department TEXT NOT NULL,
            status TEXT NOT NULL,
            effective_date TEXT NOT NULL,
            expiry_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approval_stages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER NOT NULL REFERENCES contracts(contract_id),
            stage_order INTEGER NOT NULL,
            stage_name TEXT NOT NULL,
            assigned_department TEXT NOT NULL,
            expected_days INTEGER NOT NULL,
            entered_at TEXT,
            completed_at TEXT,
            stage_status TEXT NOT NULL
        );
    """)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(DATABASE)
    initialize_contract_tables(database)
    existing = database.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
    if existing:
        print(f"contracts table already has {existing} rows. Delete documents.db to regenerate.")
        database.close()
        return

    now = datetime.now(timezone.utc)
    total_chunks = 0
    for index in range(1, CONTRACT_COUNT + 1):
        contract_type = random.choice(CONTRACT_TYPES)
        counterparty = random.choice(COMPANIES)
        department = random.choice(DEPARTMENTS)

        bucket = random.choices(
            ["pending", "expired", "expiring", "signed"],
            weights=[25, 10, 15, 50],
            k=1,
        )[0]
        if bucket == "pending":
            status = "Pending"
            effective_date = now - timedelta(days=random.randint(5, 30))
            expiry_date = effective_date + timedelta(days=365)
        elif bucket == "expired":
            status = "Expired"
            expiry_date = now - timedelta(days=random.randint(1, 60))
            effective_date = expiry_date - timedelta(days=365)
        elif bucket == "expiring":
            status = "Expiring"
            expiry_date = now + timedelta(days=random.randint(1, 30))
            effective_date = expiry_date - timedelta(days=365)
        else:
            status = "Signed"
            expiry_date = now + timedelta(days=random.randint(60, 700))
            effective_date = expiry_date - timedelta(days=365)

        effective_str = effective_date.strftime("%Y-%m-%d")
        expiry_str = expiry_date.strftime("%Y-%m-%d")
        filename = f"{contract_type.replace(' ', '_')}_{counterparty.split()[0]}_{index:03d}.pdf"
        stored_name = f"contract_{index:03d}.pdf"
        pdf_path = DATA_DIR / stored_name
        build_pdf(pdf_path, contract_type, counterparty, department, effective_str, expiry_str)

        cursor = database.execute(
            "INSERT INTO contracts (filename, stored_name, contract_type, counterparty, department, "
            "status, effective_date, expiry_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (filename, stored_name, contract_type, counterparty, department, status,
             effective_str, expiry_str, now.isoformat()),
        )
        contract_id = cursor.lastrowid

        for stage in build_stage_schedule(status):
            database.execute(
                "INSERT INTO approval_stages (contract_id, stage_order, stage_name, assigned_department, "
                "expected_days, entered_at, completed_at, stage_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (contract_id, stage["stage_order"], stage["stage_name"], stage["assigned_department"],
                 stage["expected_days"], stage["entered_at"], stage["completed_at"], stage["stage_status"]),
            )

        text = chatbot.extract_file_text(pdf_path)
        total_chunks += chatbot.replace_source(f"contract:{contract_id}", None, text)
        if index % 25 == 0:
            print(f"Generated {index}/{CONTRACT_COUNT} contracts...")

    database.commit()
    database.close()
    print(f"Finished. Generated {CONTRACT_COUNT} contracts and indexed {total_chunks} chunks.")


if __name__ == "__main__":
    main()
