import os
from pathlib import Path
from pydantic_settings import BaseSettings

# Project Root Directory
BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "SAP Support AI Automation Backend"
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"

    # Database
    DATABASE_URL: str = "sqlite:///./sap_tickets.db"

    # Toggle Flags for Mock Mode
    USE_MOCK_GMAIL: bool = True
    USE_MOCK_LLM: bool = True

    # AI / LLM Configuration
    GEMINI_API_KEY: str = ""

    # Gmail API Configuration
    GMAIL_CREDENTIALS_FILE: str = os.path.join("gmail", "credentials.json")
    GMAIL_TOKEN_FILE: str = os.path.join("gmail", "token.json")

    # Background Email Polling & Webhook Settings
    ENABLE_BACKGROUND_POLLING: bool = False
    EMAIL_POLL_INTERVAL_SECONDS: int = 60
    GMAIL_PUBSUB_TOPIC: str = ""
    WEBHOOK_SECRET_TOKEN: str = "sap-ai-webhook-secret"

    # Upload Directory
    UPLOAD_DIR: str = "uploads"

    @property
    def absolute_upload_dir(self) -> Path:
        path = BASE_DIR / self.UPLOAD_DIR
        path.mkdir(parents=True, exist_ok=True)
        return path

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
