from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Application
    app_name: str = "TaskForge"
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    debug: bool = False

    # Database
    database_url: str = "sqlite:///./taskforge.db"

    # Session
    session_cookie_name: str = "taskforge_session"
    session_max_age: int = 86400  # 24 hours in seconds


settings = Settings()
