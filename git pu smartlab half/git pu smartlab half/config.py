
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "smartlab_db")

    SECRET_KEY = os.getenv("SECRET_KEY", "smartlab-dev-secret-key-change-me")
    DEBUG = os.getenv("FLASK_DEBUG", "True") == "True"

    DEFAULT_TIME_QUANTUM = int(os.getenv("DEFAULT_TIME_QUANTUM", "10"))
