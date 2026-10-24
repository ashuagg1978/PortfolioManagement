from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

CONFIG_JSON = Path(__file__).resolve().parent.parent / "config.json"


class Settings(BaseSettings):
    app_name: str = "Portfolio Management API"
    api_prefix: str = "/api"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Local-first by default: a single SQLite file next to the backend, zero
    # setup required. Environment settings override config-file values, so
    # pointing this at a Postgres DSN later is a config change, not a code
    # change (see the DecimalText type for the one thing that needs attention).
    database_url: str = "sqlite:///./portfolio.db"

    amfi_nav_url: str = "https://portal.amfiindia.com/spages/NAVAll.txt"

    # No auth in v1 - every request is scoped to this single seeded user.
    # app/api/deps.py::get_current_user() is the one seam where real auth
    # plugs in later.
    seed_user_email: str = "owner@portfolio.local"
    seed_user_name: str = "Portfolio Owner"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-pro"
    gemini_timeout_seconds: float = 120.0

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", json_file=CONFIG_JSON
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            JsonConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


settings = Settings()
