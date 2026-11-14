from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", extra="ignore")

    ENV: str = "development"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ADMIN_GITHUB_USERNAMES: str | None = None
    GITHUB_CLIENT_ID: str = "dev-github-client-id"
    GITHUB_CLIENT_ID_CLI: str = "dev-github-cli-client-id"
    GITHUB_CLIENT_SECRET: str = "dev-github-client-secret"
    GITHUB_CLIENT_SECRET_CLI: str = "dev-github-cli-client-secret"
    FRONTEND_URL: str = "http://localhost:3000"
    LOCAL_DATABASE_URL: str | None = "sqlite:///./local_dev.db"
    PROD_DATABASE_URL: str | None = None
    REDIS_URL: str = "redis://localhost:6379/0"


settings = Settings()


def get_database_url(settings: Settings) -> str:
    env = settings.ENV or "development"

    db_url = (
        settings.LOCAL_DATABASE_URL
        if env == "development"
        else settings.PROD_DATABASE_URL
    )

    if not db_url:
        raise ValueError("DATABASE_URL is not set in environment variables")

    return db_url


DATABASE_URL = get_database_url(settings)

