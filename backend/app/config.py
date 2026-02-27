"""Zentrale Konfiguration via Environment Variables"""

import os
import secrets


class Settings:
    # Database
    DATABASE_PATH: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "finanzmanager.db"
    )

    # JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    # CORS
    ALLOWED_ORIGINS: list = os.getenv("ALLOWED_ORIGINS", "").split(",") if os.getenv("ALLOWED_ORIGINS") else []

    # App
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "100"))
    LOGIN_RATE_LIMIT_PER_MINUTE: int = int(os.getenv("LOGIN_RATE_LIMIT_PER_MINUTE", "5"))

    # Upload
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))

    def __init__(self):
        # Auto-generate SECRET_KEY if not set, persist to file for consistency
        if not self.SECRET_KEY:
            secret_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", ".secret_key"
            )
            if os.path.exists(secret_file):
                with open(secret_file, "r") as f:
                    self.SECRET_KEY = f.read().strip()
            else:
                self.SECRET_KEY = secrets.token_urlsafe(64)
                os.makedirs(os.path.dirname(secret_file), exist_ok=True)
                with open(secret_file, "w") as f:
                    f.write(self.SECRET_KEY)


settings = Settings()
