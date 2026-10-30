# app/config.py
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "My API"
    API_V1_PREFIX: str = "/api/v1"

    # SQLite by default — swap for:
    # postgresql://user:password@localhost:5432/dbname
    DATABASE_URL: str = "sqlite:///./app.db"

    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Gemini & Media Settings
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash"
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 500

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_database_url(self) -> "Settings":
        # Fallback to local SQLite if an unconfigured/dummy remote database URL is present in the environment
        if "xyz.pooler.supabase.net" in self.DATABASE_URL or "change-me" in self.DATABASE_URL:
            self.DATABASE_URL = "sqlite:///./app.db"
        return self


settings = Settings()