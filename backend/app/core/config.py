from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "PrintGest Local API Service"
    version: str = "0.1.0"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = (
        "postgresql+psycopg://printgest:printgest@127.0.0.1:5432/printgest"
    )
    session_ttl_minutes: int = 60
    login_max_falhas: int = 5
    bloqueio_minutos: int = 30
    admin_inicial_login: str = "admin"
    admin_inicial_senha: str = "admin123"
    admin_inicial_nome: str = "Administrador"

    redgest_url: str = "http://127.0.0.1:9100"
    redgest_sistema: str = "grafica_erp"
    licenca_refresh_intervalo_segundos: int = 300
    licenca_renova_antes_segundos: int = 3600

    model_config = {"env_prefix": "PRINTGEST_"}


settings = Settings()