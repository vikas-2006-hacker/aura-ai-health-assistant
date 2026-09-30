from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env files."""

    app_name: str = Field(default="AURA", validation_alias="APP_NAME")
    app_version: str = Field(default="0.1.0", validation_alias="APP_VERSION")
    debug: bool = Field(default=False, validation_alias="DEBUG")
    cors_origins: str = Field(default="*", validation_alias="CORS_ORIGINS")
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/aura",
        validation_alias="DATABASE_URL",
    )
    # JWT / Authentication settings
    jwt_secret_key: str = Field(default="CHANGE_ME", validation_alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    # Hydration engine configuration
    # milliliters of water per kilogram of bodyweight used as a baseline heuristic
    water_ml_per_kg: float = Field(default=35.0, validation_alias="WATER_ML_PER_KG")
    # Activity adjustments expressed as fractional increases (e.g., 0.10 == +10%)
    activity_adjustments: dict = Field(default_factory=lambda: {"sedentary": 0.0, "light": 0.05, "moderate": 0.10, "high": 0.15}, validation_alias="ACTIVITY_ADJUSTMENTS")
    # Progress thresholds (percent) for hydration status
    progress_thresholds: dict = Field(default_factory=lambda: {"low": 30, "needs_attention": 60, "progressing": 100}, validation_alias="PROGRESS_THRESHOLDS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug_mode(cls, value: object) -> object:
        """Accept conventional deployment labels while retaining a Boolean setting."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod"}:
                return False
            if normalized in {"development", "dev"}:
                return True
        return value


settings = Settings()
