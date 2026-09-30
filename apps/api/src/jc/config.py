from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    database_url: str = "sqlite:///./jc.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = ""
    log_level: str = "INFO"
    demo_mode: bool = False
    sporttery_enabled: bool = True
    sporttery_base_url: str = ""
    sporttery_matches_path: str = ""
    sporttery_odds_path: str = ""
    odds_provider_enabled: bool = False
    odds_provider_base_url: str = ""
    odds_provider_api_key: str = ""
    odds_provider_sports: str = "soccer_epl"
    odds_provider_bookmakers: str = "pinnacle,bet365,macau,williamhill"
    provider_min_interval: int = Field(30, ge=1)
    odds_provider_min_interval: int = Field(60, ge=1)
    provider_timeout: float = Field(15, gt=0)
    provider_max_attempts: int = Field(4, ge=1, le=8)
    mapping_auto_threshold: float = Field(95, ge=0, le=100)
    mapping_review_threshold: float = Field(80, ge=0, le=100)
    mapping_ambiguity_margin: float = Field(5, ge=0, le=100)
    scheduler_enabled: bool = False
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    admin_email: str = ""
    admin_password: str = ""

    @model_validator(mode="after")
    def validate_config(self):
        if self.mapping_review_threshold > self.mapping_auto_threshold:
            raise ValueError("Review threshold must not exceed auto threshold")
        if self.app_env == "production":
            if len(self.jwt_secret) < 32 or self.jwt_secret.startswith("replace-"):
                raise ValueError("Production requires a random JWT_SECRET of 32+ characters")
            if not self.database_url.startswith("postgresql") or self.demo_mode:
                raise ValueError("Production requires PostgreSQL and DEMO_MODE=false")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
