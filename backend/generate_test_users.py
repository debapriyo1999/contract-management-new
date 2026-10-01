"""One-time generator: creates N dummy user accounts in SQLite for local testing.

Run once from the backend folder:
    .venv\\Scripts\\python.exe generate_test_users.py
Override the count and password with environment variables:
    $env:USER_COUNT = "50"
    $env:USER_PASSWORD = "Password123!"
"""
from datetime import datetime, timezone
import hashlib
import os
import secrets
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATABASE = BASE_DIR / "documents.db"
USER_COUNT = int(os.getenv("USER_COUNT", "50"))
USER_PASSWORD = os.getenv("USER_PASSWORD", "Password123!")


def password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


def main() -> None:
    connection = sqlite3.connect(DATABASE)
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    now = datetime.now(timezone.utc).isoformat()
    created = 0
    for index in range(1, USER_COUNT + 1):
        email = f"testuser{index:02d}@example.com"
        salt = secrets.token_hex(16)
        try:
            connection.execute(
                "INSERT INTO users (email, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
                (email, password_hash(USER_PASSWORD, salt), salt, now),
            )
            created += 1
        except sqlite3.IntegrityError:
            pass  # account already exists, skip
    connection.commit()
    connection.close()
    print(f"Created {created} new user accounts (requested {USER_COUNT}). Password for all: {USER_PASSWORD}")


if __name__ == "__main__":
    main()
