from typing import ClassVar
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_secret_key: str = "dev-secret-change-in-production"
    app_base_url: str = "http://localhost:8000"

    # MongoDB
    mongodb_url: str
    mongodb_db_name: str = "sheet_notifier"

    # Google OAuth
    google_client_id: str
    google_client_secret: str

    # Worker
    worker_secret: str = "worker-secret"
    default_poll_interval: int = 30

    @property
    def google_login_redirect_uri(self) -> str:
        return f"{self.app_base_url}/auth/callback"

    @property
    def google_sheets_redirect_uri(self) -> str:
        return f"{self.app_base_url}/google/callback"

    # Google OAuth scopes (ClassVar so pydantic doesn't treat them as fields)
    GOOGLE_LOGIN_SCOPES: ClassVar[list[str]] = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]

    GOOGLE_SHEETS_SCOPES: ClassVar[list[str]] = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
