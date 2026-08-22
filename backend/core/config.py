from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Portfolio Management API"
    api_prefix: str = "/api"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Local-first by default: a single SQLite file next to the backend, zero
    # setup required. The value always comes from the environment though, so
    # pointing this at a Postgres DSN later is a config change, not a code
    # change (see the DecimalText type in app/db/types.py for the one thing
    # that *does* need attention on that move).
    database_url: str = "sqlite:///./portfolio.db"

    amfi_nav_url: str = "https://portal.amfiindia.com/spages/NAVAll.txt"

    # No auth in v1 - every request is scoped to this single seeded user.
    # app/api/deps.py::get_current_user() is the one seam where real auth
    # plugs in later.
    seed_user_email: str = "owner@portfolio.local"
    seed_user_name: str = "Portfolio Owner"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
