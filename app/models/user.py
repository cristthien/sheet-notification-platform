from datetime import datetime
from typing import Optional
from beanie import Document
from pydantic import Field


class User(Document):
    """Platform user - authenticated via Google OAuth."""

    # Google identity (from login OAuth)
    google_id: str                        # Google's 'sub' claim (unique per user)
    email: str
    name: str
    avatar_url: Optional[str] = None

    # ─── Google Sheets OAuth credentials (SEPARATE from login) ───
    # These are obtained via a second OAuth flow with Sheets scope.
    # Stored encrypted-at-rest in production; plain for simplicity here.
    sheets_access_token: Optional[str] = None
    sheets_refresh_token: Optional[str] = None
    sheets_token_expiry: Optional[datetime] = None  # Used for revoke detection
    sheets_token_scope: Optional[str] = None
    sheets_connected: bool = False
    sheets_revoked: bool = False           # True if user revoked permission

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"
        indexes = ["google_id", "email"]

    class Config:
        json_schema_extra = {
            "example": {
                "google_id": "116xxxxxxxxxx",
                "email": "user@gmail.com",
                "name": "Nguyen Van A",
            }
        }
