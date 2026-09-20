from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "PrintGest Local API Service"
    version: str = "0.1.0"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = (
        "postgresql+psycopg://printgest:printgest@localhost:5432/printgest"
    )
    session_ttl_minutes: int = 60
    login_max_falhas: int = 5

    model_config = {"env_prefix": "PRINTGEST_"}


settings = Settings()