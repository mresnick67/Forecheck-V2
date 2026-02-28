from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "sqlite:///./forecheck.db"
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 14
    environment: str = "development"
    app_mode: str = "single_owner"
    enable_registration: bool = False
    setup_bootstrap_token: str | None = None
    public_base_url: str = "http://localhost:6767"
    api_cors_origins: str = "http://localhost:6767"
    run_sync_loop: bool = False
    nhl_sync_enabled: bool = True
    nhl_sync_interval_minutes: int = 60
    nhl_season: str | None = None
    nhl_game_type: int = 2
    nhl_nightly_sync_hour_utc: int = 4
    nhl_game_log_max_age_hours: int = 24
    nhl_game_log_source: str = "game_center"
    nhl_game_log_backfill_days: int = 1
    nhl_game_center_delay_seconds: float = 0.25
    nhl_sync_commit_batch_size: int = 500
    nhl_player_on_demand_sync: bool = False

    # Yahoo Fantasy API settings
    yahoo_enabled: bool = False
    yahoo_client_id: str | None = None
    yahoo_client_secret: str | None = None
    yahoo_redirect_uri: str | None = None
    yahoo_oauth_path: str = "oauth2.json"

    @property
    def cors_origins(self) -> list[str]:
        raw = self.api_cors_origins.strip()
        if not raw:
            return []
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def resolved_yahoo_redirect_uri(self) -> str:
        if self.yahoo_redirect_uri:
            return self.yahoo_redirect_uri
        return f"{self.public_base_url.rstrip('/')}/api/auth/yahoo/callback"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
