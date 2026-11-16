from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SAFEVISION_", env_file=".env", env_parse_none_str="null", extra="ignore",
    )

    demo: bool = False
    database_url: str = "postgresql+psycopg://safevision:safevision@localhost:5432/safevision"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint: str | None = "http://localhost:9000"
    s3_access_key: str | None = None
    s3_secret_key: SecretStr | None = None
    s3_bucket: str = "safevision"
    s3_region: str = "us-east-1"

    admin_password: SecretStr | None = None
    session_secret: SecretStr | None = None
    cookie_secure: bool = True
    session_seconds: int = Field(default=28800, ge=300, le=86400)

    weights: Path = Path("models/iaac-ppe.pt")
    device: str = "cpu"
    image_size: int = Field(default=640, ge=160, le=1280, multiple_of=32)
    confidence: float = Field(default=0.35, gt=0, lt=1)
    torch_threads: int = Field(default=2, ge=1, le=16)
    sample_fps: float = Field(default=5, ge=1, le=30)
    violation_seconds: float = Field(default=2, ge=0.5, le=60)
    gap_seconds: float = Field(default=0.8, ge=0.3, le=5)
    recovery_seconds: float = Field(default=1, ge=0.3, le=10)

    image_mb: int = Field(default=8, ge=1, le=50)
    video_mb: int = Field(default=100, ge=1, le=500)
    max_video_seconds: int = Field(default=300, ge=5, le=1800)
    evidence_days: int = Field(default=30, ge=1, le=365)
    upload_days: int = Field(default=2, ge=1, le=30)
    timezone: str = "America/Sao_Paulo"

    @model_validator(mode="after")
    def validate_settings(self):
        from zoneinfo import ZoneInfo

        ZoneInfo(self.timezone)
        if self.gap_seconds < 1 / self.sample_fps:
            raise ValueError("gap_seconds precisa cobrir o intervalo entre amostras")
        if not self.demo:
            if not self.admin_password or len(self.admin_password.get_secret_value()) < 12:
                raise ValueError("Configure SAFEVISION_ADMIN_PASSWORD com pelo menos 12 caracteres")
            if not self.session_secret or len(self.session_secret.get_secret_value()) < 32:
                raise ValueError("Configure SAFEVISION_SESSION_SECRET com pelo menos 32 caracteres")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
