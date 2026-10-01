"""Send email alerts for contracts expiring in a configured number of days.

Run from the backend directory:
    .venv\\Scripts\\python.exe alert.py
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import os
from pathlib import Path
import sqlite3
import sys

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
DATABASE = BASE_DIR / "documents.db"
load_dotenv(BASE_DIR / ".env")


class AlertConfigurationError(ValueError):
    pass


class AlertDeliveryError(RuntimeError):
    pass


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

    try:
        import win32com.client as win32com
        import pywintypes
    except ImportError as error:
        raise AlertConfigurationError("Install pywin32 before sending alerts.") from error

    try:
        outlook = win32com.Dispatch("Outlook.Application")
        sent = 0
        for contract in contracts:
            for recipient in recipients:
                message = outlook.CreateItem(0)
                message.Subject = f"Contract expiration alert: {contract['filename']}"
                message.To = recipient
                message.Body = (
                    "Contract expiration alert\n\n"
                    f"Contract: {contract['filename']}\n"
                    f"Type: {contract['contract_type']}\n"
                    f"Counterparty: {contract['counterparty']}\n"
                    f"Department: {contract['department']}\n"
                    f"Expiration date: {contract['expiry_date']}\n\n"
                    f"This contract expires in {days} days. Please review it in the contract management system."
                )
                message.Send()
                sent += 1
    except pywintypes.com_error as error:
        raise AlertDeliveryError(f"Outlook could not send the alert: {error}") from error
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
    except (AlertConfigurationError, AlertDeliveryError, OSError, sqlite3.Error) as error:
        print(f"Alert failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
