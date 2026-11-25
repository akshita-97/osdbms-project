
import os

from flask import Flask, render_template
from mysql.connector import Error as MySQLError

from config import Config
from db.database import test_connection

from routes.auth import auth_bp, require_login, ensure_users_table
from routes.dashboard import dashboard_bp
from routes.computers import computers_bp
from routes.maintenance import maintenance_bp
from routes.resources import resources_bp
from routes.fleet import fleet_bp
from routes.banker import banker_bp
from services.fleet_service import ensure_tables as ensure_fleet_tables
from services.banker_service import ensure_tables as ensure_banker_tables


# Maps every status/severity string used across the app to a visual
# "tone" (see static/css/style.css badge[data-tone] rules).
STATUS_TONE_MAP = {
    # severities / priorities
    "Critical": "danger", "High": "warning", "Medium": "warning", "Low": "success",
    # computer / general
    "Available": "success", "Active": "success", "Completed": "success",
    "Offline": "danger", "Rejected": "danger",
    "Under Maintenance": "warning", "Maintenance Required": "warning",
    "Pending": "warning", "Pending Review": "warning", "Waiting for Resource": "warning",
        "In Progress": "info", "Resources Allocated": "info", "In Use": "info",
    "Approved": "info", "Scheduled": "info", "Converted to Task": "info",
    "Closed": "neutral",
    "Busy": "neutral", "Off Duty": "neutral", "Cancelled": "neutral", "Released": "neutral",
    "Allocated": "info",
}


def tone_for_status(status):
    return STATUS_TONE_MAP.get(status, "neutral")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.jinja_env.filters["tone"] = tone_for_status

    # Every page except /login and /signup requires a logged-in user.
    app.before_request(require_login)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(computers_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(resources_bp)
    app.register_blueprint(fleet_bp)
    app.register_blueprint(banker_bp)

    # Make sure the users table exists (no-op if it already does). If MySQL
    # is down we just skip; the friendly error page appears on first request.
    ensure_users_table()
    try:
        ensure_fleet_tables()
        ensure_banker_tables()
    except MySQLError:
        pass

    # Requests approved before tasks were auto-created get their task now.
    try:
        from services.maintenance_service import sync_approved_requests
        sync_approved_requests()
    except MySQLError:
        pass

    @app.errorhandler(MySQLError)
    def handle_database_error(error):
        """Show a helpful page (not a stack trace) when MySQL is down or misconfigured."""
        return render_template("error.html", error=str(error), db_name=Config.DB_NAME,
                               db_host=Config.DB_HOST, db_port=Config.DB_PORT), 500

    return app


app = create_app()


if __name__ == "__main__":
    ok, message = test_connection()
    if ok:
        print(f"[SmartLab] Database connection OK: {message}")
    else:
        print(f"[SmartLab] WARNING - could not connect to MySQL: {message}")
        print("[SmartLab] Check your .env file and make sure MySQL is running, "
              "and that you have run:  python setup_db.py")

    # Default: this laptop only. Set SMARTLAB_HOST=0.0.0.0 so lab PCs on the LAN can send readings.
    host = os.getenv("SMARTLAB_HOST", "127.0.0.1")
    debug = Config.DEBUG and host == "127.0.0.1"   # never expose the Werkzeug debugger to the LAN
    print(f"[SmartLab] Starting Flask server on http://{host}:5000 (debug={debug})")
    use_reloader = debug and not os.getenv("SMARTLAB_NO_RELOAD")
    app.run(host=host, port=5000, debug=debug, use_reloader=use_reloader)
