"""Send email alerts for contracts expiring in a configured number of days.

Run from the backend directory:
    .venv\\Scripts\\python.exe alert.py
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from email.message import EmailMessage
import os
from pathlib import Path
import smtplib
import sqlite3
import sys

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
DATABASE = BASE_DIR / "documents.db"
load_dotenv(BASE_DIR / ".env")


class AlertConfigurationError(ValueError):
    pass


def setting(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default or "").strip()
    if not value:
        raise AlertConfigurationError(f"Set {name} in backend/.env before sending alerts.")
    return value


def send_alerts(days: int, recipients: list[str], run_date: date, dry_run: bool) -> int:
    expiry = (run_date + timedelta(days=days)).isoformat()
    with sqlite3.connect(DATABASE) as database:
        database.row_factory = sqlite3.Row
        contracts = database.execute(
            "SELECT filename, contract_type, counterparty, department, expiry_date "
            "FROM contracts WHERE expiry_date = ? ORDER BY contract_id",
            (expiry,),
        ).fetchall()

    if not contracts:
        print(f"No contracts expire in exactly {days} days.")
        return 0

    if dry_run:
        for contract in contracts:
            for recipient in recipients:
                print(f"Would send {contract['filename']} to {recipient}")
        return 0

    username = setting("SMTP_USERNAME")
    sender = os.getenv("SMTP_FROM", username).strip()
    server_type = smtplib.SMTP_SSL if os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes"} else smtplib.SMTP
    sent = 0
    with server_type(setting("SMTP_HOST"), int(os.getenv("SMTP_PORT", "587"))) as server:
        if server_type is smtplib.SMTP:
            server.starttls()
        server.login(username, setting("SMTP_PASSWORD"))
        for contract in contracts:
            for recipient in recipients:
                message = EmailMessage()
                message["Subject"] = f"Contract expiration alert: {contract['filename']}"
                message["From"] = sender
                message["To"] = recipient
                message.set_content(
                    "Contract expiration alert\n\n"
                    f"Contract: {contract['filename']}\n"
                    f"Type: {contract['contract_type']}\n"
                    f"Counterparty: {contract['counterparty']}\n"
                    f"Department: {contract['department']}\n"
                    f"Expiration date: {contract['expiry_date']}\n\n"
                    f"This contract expires in {days} days. Please review it in the contract management system."
                )
                server.send_message(message)
                sent += 1
    print(f"Sent {sent} expiration alert(s).")
    return sent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send contract expiration email alerts.")
    parser.add_argument("--days", type=int, default=int(os.getenv("ALERT_DAYS_BEFORE", "30")))
    parser.add_argument("--to", default=os.getenv("ALERT_RECIPIENT"))
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        if args.days < 0:
            raise AlertConfigurationError("--days must be zero or greater.")
        recipients = [item.strip() for item in (args.to or "").split(",") if item.strip()]
        if not recipients:
            raise AlertConfigurationError("Set ALERT_RECIPIENT or pass --to.")
        send_alerts(args.days, recipients, args.date, args.dry_run)
    except (AlertConfigurationError, OSError, sqlite3.Error, smtplib.SMTPException) as error:
        print(f"Alert failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
