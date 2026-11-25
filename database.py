

import mysql.connector
from mysql.connector import Error
from config import Config


def get_connection():
    """Open and return a new MySQL connection."""
    return mysql.connector.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        connection_timeout=5,
    )


def fetch_all(query, params=None):
    """Run a SELECT and return all rows as a list of dicts."""
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        rows = cursor.fetchall()
        cursor.close()
        return rows
    finally:
        conn.close()


def fetch_one(query, params=None):
    """Run a SELECT and return a single row as a dict (or None)."""
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        row = cursor.fetchone()
        cursor.close()
        return row
    finally:
        conn.close()


def execute(query, params=None):
    """
    Run an INSERT/UPDATE/DELETE as its own auto-committed statement.
    Returns (lastrowid, rowcount).
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params or ())
        conn.commit()
        last_id = cursor.lastrowid
        row_count = cursor.rowcount
        cursor.close()
        return last_id, row_count
    except Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_transaction(statements):
    """
    Run a list of (query, params) tuples as a SINGLE transaction.
    If any statement fails, the whole transaction is rolled back.
    Used for operations that must be atomic, e.g. resource allocation
    (check availability -> insert allocation -> update quantities).

    Returns a list of lastrowid values, one per statement.
    """
    conn = get_connection()
    last_ids = []
    try:
        cursor = conn.cursor()
        for query, params in statements:
            cursor.execute(query, params or ())
            last_ids.append(cursor.lastrowid)
        conn.commit()
        cursor.close()
        return last_ids
    except Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_connection():
    """Used by app.py at startup to verify DB connectivity."""
    try:
        conn = get_connection()
        conn.close()
        return True, "Connected to MySQL successfully."
    except Error as e:
        return False, str(e)
