from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "PrintGest Local API Service"
    version: str = "0.1.0"
    env: str = "dev"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = (
        "postgresql+psycopg://printgest:printgest@127.0.0.1:5432/printgest"
    )
    cors_origins: list[str] = []
    auto_migrate: bool = True
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
    licenca_desabilitada: bool = False

    model_config = {"env_prefix": "PRINTGEST_", "env_file": ".env", "extra": "ignore"}

    def validar_producao(self) -> None:
        """P17: recusa defaults inseguros fora de dev/local/test.

        Mantém os defaults de desenvolvimento (usados pela suíte e pelo
        `setup_postgres.ps1`), mas impede que uma instalação produtiva suba com a
        senha do admin ou a credencial de banco de fábrica.
        """
        if self.env.lower() in {"dev", "local", "test"}:
            return
        if self.admin_inicial_senha == "admin123":
            raise RuntimeError(
                "Defina PRINTGEST_ADMIN_INICIAL_SENHA — a senha padrão 'admin123' "
                "não é permitida em produção."
            )
        if "printgest:printgest@" in self.database_url:
            raise RuntimeError(
                "Defina PRINTGEST_DATABASE_URL com credenciais próprias — a "
                "credencial padrão não é permitida em produção."
            )


settings = Settings()