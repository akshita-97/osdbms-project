
import os
from dotenv import load_dotenv

# Load variables from a .env file in the project root, if present.
load_dotenv()


class Config:
    # --- MySQL connection settings ---
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "smartlab_db")

    # --- Flask settings ---
    SECRET_KEY = os.getenv("SECRET_KEY", "smartlab-dev-secret-key-change-me")
    DEBUG = os.getenv("FLASK_DEBUG", "True") == "True"

    # --- Application-specific settings ---
    # Default Round Robin time quantum (minutes) - optional algorithm
    DEFAULT_TIME_QUANTUM = int(os.getenv("DEFAULT_TIME_QUANTUM", "10"))
