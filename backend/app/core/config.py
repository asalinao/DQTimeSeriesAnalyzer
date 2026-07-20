from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    admin_username: str = "admin"
    admin_password: str = "admin"
    admin_token: str = "change-me"
    encryption_key: str = "change-me"
    database_url: str = "sqlite:///./dq_mvp.db"
    min_series_points: int = 30
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost:8080"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
