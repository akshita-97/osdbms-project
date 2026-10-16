
import argparse
import sys
from pathlib import Path

import mysql.connector
from mysql.connector import Error

from config import Config

BASE_DIR = Path(__file__).resolve().parent
SCHEMA_FILE = BASE_DIR / "database" / "schema.sql"
SEED_FILE = BASE_DIR / "database" / "seed.sql"


def strip_line_comment(line):
    in_quote = None
    i = 0
    while i < len(line):
        ch = line[i]
        if in_quote:
            if ch == in_quote:
                in_quote = None
        elif ch in ("'", '"'):
            in_quote = ch
        elif ch == "-" and line[i:i + 2] == "--":
            return line[:i]
        i += 1
    return line


def split_sql(text):
  
    statements = []
    buffer = []
    delimiter = ";"

    for raw_line in text.splitlines():
        line = strip_line_comment(raw_line)

        if line.strip().upper().startswith("DELIMITER "):
            delimiter = line.strip().split(None, 1)[1].strip()
            continue

        buffer.append(line)
        joined = "\n".join(buffer).rstrip()
        if joined.endswith(delimiter):
            statement = joined[: -len(delimiter)].strip()
            if statement:
                statements.append(statement)
            buffer = []

    leftover = "\n".join(buffer).strip()
    if leftover:
        statements.append(leftover)
    return statements


def run_script(cursor, path):
    text = path.read_text(encoding="utf-8").replace("smartlab_db", Config.DB_NAME)
    statements = split_sql(text)
    for number, statement in enumerate(statements, start=1):
        try:
            cursor.execute(statement)
        except Error as exc:
            preview = " ".join(statement.split())[:120]
            print(f"\n[setup_db] FAILED on statement {number} of {path.name}:\n  {preview}...")
            print(f"[setup_db] MySQL said: {exc}")
            raise
    return len(statements)


def backup_users(cursor):
    """Return all rows of the existing users table (or [] if there is none)."""
    try:
        cursor.execute(f"SELECT user_id, username, full_name, password_hash, created_at, "
                       f"last_login_at FROM `{Config.DB_NAME}`.users")
        return cursor.fetchall()
    except Error:
        return []  # database or table doesn't exist yet


def restore_users(cursor, rows):
    cursor.execute(f"USE `{Config.DB_NAME}`")
    for row in rows:
        cursor.execute(
            "INSERT INTO users (user_id, username, full_name, password_hash, created_at, "
            "last_login_at) VALUES (%s, %s, %s, %s, %s, %s)", row)


def main():
    parser = argparse.ArgumentParser(description="Create and seed the SmartLab database.")
    parser.add_argument("--yes", "-y", action="store_true", help="skip the confirmation prompt")
    parser.add_argument("--no-seed", action="store_true", help="create tables only, no demo data")
    args = parser.parse_args()

    for f in (SCHEMA_FILE, SEED_FILE):
        if not f.exists():
            sys.exit(f"[setup_db] Missing file: {f}")

    print(f"[setup_db] MySQL server : {Config.DB_HOST}:{Config.DB_PORT} (user '{Config.DB_USER}')")
    print(f"[setup_db] Database     : {Config.DB_NAME}")

    if not args.yes:
        answer = input(f"This will DROP and recreate database '{Config.DB_NAME}'. Continue? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            sys.exit("[setup_db] Cancelled. Nothing was changed.")

    try:
        # Connect WITHOUT a database name: schema.sql creates it.
        conn = mysql.connector.connect(
            host=Config.DB_HOST, port=Config.DB_PORT,
            user=Config.DB_USER, password=Config.DB_PASSWORD,
            connection_timeout=10,
        )
    except Error as exc:
        print(f"\n[setup_db] Could not connect to MySQL: {exc}\n")
        print("Things to check:")
        print("  1. Is the MySQL service running? (Windows: Services app -> MySQL80 -> Start)")
        print("  2. Did you copy .env.example to .env and set DB_PASSWORD to your MySQL root password?")
        print("  3. Are DB_HOST / DB_PORT / DB_USER in .env correct?")
        sys.exit(1)

    try:
        cursor = conn.cursor()
        saved_users = backup_users(cursor)
        count = run_script(cursor, SCHEMA_FILE)
        print(f"[setup_db] schema.sql : {count} statements OK (tables, indexes, triggers)")
        if not args.no_seed:
            count = run_script(cursor, SEED_FILE)
            print(f"[setup_db] seed.sql   : {count} statements OK (demo data)")
        if saved_users:
            restore_users(cursor, saved_users)
            print(f"[setup_db] users      : kept {len(saved_users)} existing login account(s)")
        conn.commit()
        cursor.close()
    except Error:
        sys.exit(1)
    finally:
        conn.close()

    print("\n[setup_db] Done. Start the app with:  python app.py")
    print("[setup_db] Then open http://127.0.0.1:5000")


if __name__ == "__main__":
    main()
