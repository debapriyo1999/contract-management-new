from datetime import date, datetime, timezone
import base64
import hmac
import json
import os
from pathlib import Path
import hashlib
import secrets
import sqlite3
import uvicorn

from chatbot import answer_question, extract_file_text, initialize_index, replace_source
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

app = FastAPI(title="Contract Management Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
DATABASE = BASE_DIR / "documents.db"
CONTRACTS_DIR = BASE_DIR / "data" / "contracts"
load_dotenv(BASE_DIR / ".env")
SHARE_SECRET = os.getenv("SECRET_KEY", "development-contract-share-secret").encode()
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")

ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
UPLOAD_STAGE_DEFINITIONS = [
    ("Legal Review", "Legal", 3),
    ("Finance Review", "Finance", 4),
    ("Department Head Approval", None, 3),
    ("Final Sign-off", "Executive", 2),
]

def db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection

def initialize_database() -> None:
    with db_connection() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
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

initialize_database()
initialize_index()

class LoginRequest(BaseModel):
    email: str
    password: str

class ChatRequest(BaseModel):
    question: str
    conversation: str = ""

class ApprovalSubmitRequest(BaseModel):
    contract_id: int
    stage_name: str

class ApprovalShareRequest(ApprovalSubmitRequest):
    pass

def password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100_000
    ).hex()

@app.post("/auth/signup")
def signup(request: LoginRequest) -> dict[str, str]:
    email = request.email.strip().lower()
    salt = secrets.token_hex(16)
    try:
        with db_connection() as connection:
            connection.execute(
                "INSERT INTO users (email, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
                (email, password_hash(request.password, salt), salt, datetime.now(timezone.utc).isoformat()),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="An account already exists for this email")
    return {"user": email}

@app.post("/auth/login")
def login(request: LoginRequest) -> dict[str, str]:
    email = request.email.strip().lower()
    with db_connection() as connection:
        user = connection.execute(
            "SELECT email, password_hash, salt FROM users WHERE email = ?", (email,)
        ).fetchone()
    if not user or not secrets.compare_digest(
        password_hash(request.password, user["salt"]), user["password_hash"]
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"user": user["email"]}

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

def require_user(x_user: str | None) -> str:
    if not x_user:
        raise HTTPException(status_code=401, detail="User header is required")
    return x_user

def encode_share_token(contract_id: int, stage_name: str) -> str:
    payload = json.dumps({"contract_id": contract_id, "stage_name": stage_name}, separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=")
    signature = hmac.new(SHARE_SECRET, encoded, hashlib.sha256).digest()
    return f"{encoded.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"

def decode_share_token(token: str) -> dict:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(SHARE_SECRET, encoded.encode(), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        if not hmac.compare_digest(expected, supplied):
            raise ValueError
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        data = json.loads(payload)
        if not isinstance(data.get("contract_id"), int) or not isinstance(data.get("stage_name"), str):
            raise ValueError
        return data
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, base64.binascii.Error):
        raise HTTPException(status_code=400, detail="Invalid approval link")

@app.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    contract_type: str = Form("Uploaded Document"),
    counterparty: str = Form("Unspecified"),
    department: str = Form("Legal"),
    expiry_date: str | None = Form(None),
    x_user: str | None = Header(default=None),
) -> dict:
    require_user(x_user)
    suffix = Path(file.filename or "upload").suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF, DOC, DOCX, or TXT files are supported")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 10 MB upload limit")

    now = datetime.now(timezone.utc)
    effective_str = now.strftime("%Y-%m-%d")
    if expiry_date:
        try:
            expiry_str = date.fromisoformat(expiry_date).isoformat()
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Expiry date must use YYYY-MM-DD format") from error
        if expiry_str < effective_str:
            raise HTTPException(status_code=400, detail="Expiry date cannot be before today")
    else:
        expiry_str = (now.replace(year=now.year + 1)).strftime("%Y-%m-%d")

    with db_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO contracts (filename, stored_name, contract_type, counterparty, department, "
            "status, effective_date, expiry_date, created_at) VALUES (?, ?, ?, ?, ?, 'Pending', ?, ?, ?)",
            (file.filename, "", contract_type, counterparty, department, effective_str, expiry_str, now.isoformat()),
        )
        contract_id = cursor.lastrowid
        stored_name = f"contract_{contract_id}{suffix}"
        connection.execute(
            "UPDATE contracts SET stored_name = ? WHERE contract_id = ?", (stored_name, contract_id)
        )
        for index, (stage_name, fixed_department, expected_days) in enumerate(UPLOAD_STAGE_DEFINITIONS):
            connection.execute(
                "INSERT INTO approval_stages (contract_id, stage_order, stage_name, assigned_department, "
                "expected_days, entered_at, completed_at, stage_status) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)",
                (
                    contract_id, index, stage_name, fixed_department or department, expected_days,
                    now.isoformat() if index == 0 else None,
                    "In Progress" if index == 0 else "Not Started",
                ),
            )

    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = CONTRACTS_DIR / stored_name
    file_path.write_bytes(contents)

    try:
        replace_source(f"contract:{contract_id}", None, extract_file_text(file_path))
    except Exception:
        pass  # indexing failures should not block the upload

    return {
        "contract_id": contract_id,
        "filename": file.filename,
        "status": "Pending",
        "message": "Uploaded and queued for verification",
    }

@app.get("/documents")
def list_contracts(x_user: str | None = Header(default=None)) -> list[dict]:
    require_user(x_user)
    with db_connection() as connection:
        rows = connection.execute(
            "SELECT contract_id, filename, contract_type, counterparty, department, status, "
            "effective_date, expiry_date FROM contracts ORDER BY expiry_date ASC"
        ).fetchall()
        contracts = []
        for row in rows:
            current = connection.execute(
                "SELECT stage_name, stage_status, entered_at, expected_days FROM approval_stages "
                "WHERE contract_id = ? AND stage_status = 'In Progress'",
                (row["contract_id"],),
            ).fetchone()
            if current is None:
                current = connection.execute(
                    "SELECT stage_name, stage_status, entered_at, expected_days FROM approval_stages "
                    "WHERE contract_id = ? ORDER BY stage_order DESC LIMIT 1",
                    (row["contract_id"],),
                ).fetchone()
            entry = dict(row)
            entry["current_stage"] = current["stage_name"] if current else None
            entry["stage_status"] = current["stage_status"] if current else None
            days_in_stage = None
            delayed = False
            if current and current["stage_status"] == "In Progress" and current["entered_at"]:
                elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(current["entered_at"])).days
                days_in_stage = elapsed
                delayed = elapsed > current["expected_days"]
            entry["days_in_stage"] = days_in_stage
            entry["delayed"] = delayed
            contracts.append(entry)
    return contracts

@app.get("/documents/{contract_id}/download")
def download_contract(contract_id: int) -> FileResponse:
    with db_connection() as connection:
        row = connection.execute(
            "SELECT filename, stored_name FROM contracts WHERE contract_id = ?", (contract_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contract not found")
    file_path = CONTRACTS_DIR / row["stored_name"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Contract file not found")
    return FileResponse(file_path, media_type="application/pdf", filename=row["filename"])

@app.get("/approvals/report")
def approval_report(x_user: str | None = Header(default=None)) -> list[dict]:
    require_user(x_user)
    with db_connection() as connection:
        contracts = connection.execute(
            "SELECT contract_id, filename, counterparty, department, status FROM contracts "
            "ORDER BY contract_id"
        ).fetchall()
        report = []
        for contract in contracts:
            stages = connection.execute(
                "SELECT stage_order, stage_name, assigned_department, expected_days, entered_at, "
                "completed_at, stage_status FROM approval_stages WHERE contract_id = ? ORDER BY stage_order",
                (contract["contract_id"],),
            ).fetchall()
            stage_list = []
            for stage in stages:
                actual_days = None
                delayed = False
                if stage["entered_at"] and stage["completed_at"]:
                    actual_days = (datetime.fromisoformat(stage["completed_at"]) - datetime.fromisoformat(stage["entered_at"])).days
                    delayed = actual_days > stage["expected_days"]
                elif stage["entered_at"] and stage["stage_status"] == "In Progress":
                    actual_days = (datetime.now(timezone.utc) - datetime.fromisoformat(stage["entered_at"])).days
                    delayed = actual_days > stage["expected_days"]
                stage_list.append({
                    "stage_name": stage["stage_name"],
                    "assigned_department": stage["assigned_department"],
                    "expected_days": stage["expected_days"],
                    "stage_status": stage["stage_status"],
                    "actual_days": actual_days,
                    "delayed": delayed,
                })
            report.append({
                "contract_id": contract["contract_id"],
                "filename": contract["filename"],
                "counterparty": contract["counterparty"],
                "department": contract["department"],
                "status": contract["status"],
                "stages": stage_list,
            })
    return report

def complete_approval(connection: sqlite3.Connection, contract_id: int, stage_name: str) -> dict[str, str | int | None]:
    now = datetime.now(timezone.utc).isoformat()
    stage = connection.execute(
        "SELECT id, stage_order, stage_status FROM approval_stages "
        "WHERE contract_id = ? AND stage_name = ?",
        (contract_id, stage_name),
    ).fetchone()
    if stage is None:
        raise HTTPException(status_code=404, detail="Approval stage not found")
    if stage["stage_status"] != "In Progress":
        raise HTTPException(status_code=409, detail="Only the current in-progress stage can be submitted")

    connection.execute(
        "UPDATE approval_stages SET stage_status = 'Completed', completed_at = ? WHERE id = ?",
        (now, stage["id"]),
    )
    next_stage = connection.execute(
        "SELECT id, stage_name FROM approval_stages "
        "WHERE contract_id = ? AND stage_order > ? AND stage_status = 'Not Started' "
        "ORDER BY stage_order LIMIT 1",
        (contract_id, stage["stage_order"]),
    ).fetchone()
    if next_stage:
        connection.execute(
            "UPDATE approval_stages SET stage_status = 'In Progress', entered_at = ? WHERE id = ?",
            (now, next_stage["id"]),
        )
    else:
        connection.execute(
            "UPDATE contracts SET status = 'Signed' WHERE contract_id = ?",
            (contract_id,),
        )
    return {
        "message": "Approval stage submitted",
        "contract_id": contract_id,
        "completed_stage": stage_name,
        "next_stage": next_stage["stage_name"] if next_stage else None,
    }

@app.post("/approvals/submit")
def submit_approval(
    request: ApprovalSubmitRequest,
    x_user: str | None = Header(default=None),
) -> dict[str, str | int | None]:
    require_user(x_user)
    with db_connection() as connection:
        return complete_approval(connection, request.contract_id, request.stage_name)

@app.post("/approvals/share")
def create_approval_share(
    request: ApprovalShareRequest,
    x_user: str | None = Header(default=None),
) -> dict[str, str | int]:
    require_user(x_user)
    with db_connection() as connection:
        stage = connection.execute(
            "SELECT c.filename, s.stage_status FROM contracts c "
            "JOIN approval_stages s ON s.contract_id = c.contract_id "
            "WHERE c.contract_id = ? AND s.stage_name = ?",
            (request.contract_id, request.stage_name),
        ).fetchone()
    if stage is None:
        raise HTTPException(status_code=404, detail="Approval stage not found")
    if stage["stage_status"] != "In Progress":
        raise HTTPException(status_code=409, detail="Only the current in-progress stage can be shared")
    token = encode_share_token(request.contract_id, request.stage_name)
    return {
        "contract_id": request.contract_id,
        "stage_name": request.stage_name,
        "filename": stage["filename"],
        "url": f"{FRONTEND_URL}/?approval={token}",
    }

def shared_approval_details(token: str) -> dict[str, str | int]:
    data = decode_share_token(token)
    with db_connection() as connection:
        stage = connection.execute(
            "SELECT c.contract_id, c.filename, c.counterparty, s.stage_name, s.assigned_department "
            "FROM contracts c JOIN approval_stages s ON s.contract_id = c.contract_id "
            "WHERE c.contract_id = ? AND s.stage_name = ? AND s.stage_status = 'In Progress'",
            (data["contract_id"], data["stage_name"]),
        ).fetchone()
    if stage is None:
        raise HTTPException(status_code=409, detail="This approval stage is no longer available")
    return dict(stage)

@app.get("/approvals/share/{token}")
def get_shared_approval(token: str) -> dict[str, str | int]:
    return shared_approval_details(token)

@app.post("/approvals/share/{token}/submit")
def submit_shared_approval(token: str) -> dict[str, str | int | None]:
    data = decode_share_token(token)
    with db_connection() as connection:
        shared_approval_details(token)
        return complete_approval(connection, data["contract_id"], data["stage_name"])

@app.post("/chat/question")
def chat_question(
    request: ChatRequest,
    x_user: str | None = Header(default=None),
) -> dict:
    require_user(x_user)
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")
    try:
        return answer_question(x_user, question, request.conversation)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Chat service unavailable: {error}")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
