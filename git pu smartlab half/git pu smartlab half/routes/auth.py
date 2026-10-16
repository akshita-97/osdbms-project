

import re
from urllib.parse import urlparse

from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)
from mysql.connector import Error as MySQLError
from werkzeug.security import check_password_hash, generate_password_hash

from db.database import execute, fetch_one

auth_bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
MIN_PASSWORD_LENGTH = 8

# Endpoints that may be opened without logging in.
PUBLIC_ENDPOINTS = {"auth.login", "auth.signup", "static"}

USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id        INT AUTO_INCREMENT PRIMARY KEY,
    username       VARCHAR(30)  NOT NULL UNIQUE,
    full_name      VARCHAR(100) NULL,
    password_hash  VARCHAR(255) NOT NULL,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at  TIMESTAMP NULL
)
"""


def ensure_users_table():
    """
    Create the `users` table if it doesn't exist yet. Safe to call every
    time the app starts, so existing installs work without re-running
    setup_db.py (which would wipe the database).
    Returns (ok, message).
    """
    try:
        execute(USERS_TABLE_SQL)
        return True, "users table ready"
    except MySQLError as exc:
        return False, str(exc)


def require_login():
    """before_request hook: send anonymous visitors to the login page."""
    if request.endpoint is None or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if session.get("user_id"):
        return None
    # Remember where they were headed (GET only) so we can return after login.
    next_url = request.full_path.rstrip("?") if request.method == "GET" else None
    return redirect(url_for("auth.login", next=next_url))


def _safe_next(target):
    """Only allow redirects to a path on this site (blocks open-redirects)."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


def _start_session(user):
    session.clear()  # drop any old session data (prevents session fixation)
    session["user_id"] = user["user_id"]
    session["username"] = user["username"]
    session["display_name"] = user.get("full_name") or user["username"]
    session.permanent = False


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard.index"))

    next_url = _safe_next(request.values.get("next"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = fetch_one("SELECT * FROM users WHERE username = %s", (username,)) if username else None

        if user and check_password_hash(user["password_hash"], password):
            execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE user_id = %s",
                    (user["user_id"],))
            _start_session(user)
            flash(f"Welcome back, {session['display_name']}!", "success")
            return redirect(next_url or url_for("dashboard.index"))

        # Same message whether the username or the password was wrong.
        flash("Incorrect username or password.", "error")
        return render_template("login.html", username=username, next_url=next_url), 401

    return render_template("login.html", username="", next_url=next_url)


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if session.get("user_id"):
        return redirect(url_for("dashboard.index"))

    form = {"username": "", "full_name": ""}
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()[:100]
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        form = {"username": username, "full_name": full_name}

        error = None
        if not USERNAME_RE.match(username):
            error = "Username must be 3-30 characters: letters, numbers, dot, dash or underscore."
        elif len(password) < MIN_PASSWORD_LENGTH:
            error = f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif fetch_one("SELECT user_id FROM users WHERE username = %s", (username,)):
            error = "That username is already taken. Please choose another."

        if error:
            flash(error, "error")
            return render_template("signup.html", form=form), 400

        try:
            user_id, _ = execute(
                "INSERT INTO users (username, full_name, password_hash) VALUES (%s, %s, %s)",
                (username, full_name or None, generate_password_hash(password)))
        except MySQLError as exc:
            if getattr(exc, "errno", None) == 1062:  # duplicate key: lost a race
                flash("That username is already taken. Please choose another.", "error")
                return render_template("signup.html", form=form), 400
            raise

        _start_session({"user_id": user_id, "username": username, "full_name": full_name})
        flash("Account created. Welcome to SmartLab!", "success")
        return redirect(url_for("dashboard.index"))

    return render_template("signup.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))
