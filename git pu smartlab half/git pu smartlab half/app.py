
import os

from flask import Flask, render_template
from mysql.connector import Error as MySQLError

from config import Config
from db.database import test_connection

from routes.auth import auth_bp, require_login, ensure_users_table
from routes.dashboard import dashboard_bp
from routes.computers import computers_bp
from routes.maintenance import maintenance_bp
from routes.scheduling import scheduling_bp
from routes.resources import resources_bp
from routes.monitoring import monitoring_bp


STATUS_TONE_MAP = {
    "Critical": "danger", "High": "warning", "Medium": "warning", "Low": "success",
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

    app.before_request(require_login)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(computers_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(scheduling_bp)
    app.register_blueprint(resources_bp)
    app.register_blueprint(monitoring_bp)

    ensure_users_table()

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

    print("[SmartLab] Starting Flask development server on http://127.0.0.1:5000")
   
    use_reloader = Config.DEBUG and not os.getenv("SMARTLAB_NO_RELOAD")
    app.run(host="127.0.0.1", port=5000, debug=Config.DEBUG, use_reloader=use_reloader)
