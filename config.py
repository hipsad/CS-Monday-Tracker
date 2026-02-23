"""Configuration for the CS Monday Tracker application."""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///tracker.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    LEETIFY_API_KEY = os.getenv("LEETIFY_API_KEY", "")
    LEETIFY_API_BASE = "https://api.cs-prod.leetify.com/api"
    STEAM_API_KEY = os.getenv("STEAM_API_KEY", "")
