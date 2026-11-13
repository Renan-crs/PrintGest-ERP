from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "PrintGest Local API Service"
    version: str = "0.5.1"
    env: str = "dev"
    # Seguro por padrão: bind apenas em localhost. O instalador fixa
    # 127.0.0.1; uma instalação que servira ESTAÇÕES em rede local sobrescreve
    # com PRINTGEST_API_HOST (ex.: 0.0.0.0) conscientemente.
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    database_url: str = (
        "postgresql+psycopg://printgest:printgest@127.0.0.1:5432/printgest"
    )
    cors_origins: list[str] = []
    auto_migrate: bool = True
    # Keep-alive do banco (Neon): ping `SELECT 1` a cada N segundos enquanto o
    # daemon está no ar. O Neon suspende o compute após ~5 min sem atividade
    # (scale-to-zero) e o *cold start* seguinte — somado às conexões do pool
    # mortas — se manifestava como "sistema lento ao salvar" e sessão que o
    # usuário precisava refazer. 120 s mantém o compute acordado; 0 desliga
    # (ex.: banco sempre quente por outro motivo ou plano sem horas ociosas).
    db_keepalive_segundos: int = 120
    session_ttl_minutes: int = 60
    login_max_falhas: int = 5
    bloqueio_minutos: int = 30
    admin_inicial_login: str = "admin"
    admin_inicial_senha: str = "admin123"
    admin_inicial_nome: str = "Administrador"
    # ---------------------------------------------------------------- tenant
    # Banco compartilhado entre gráficas (projeto Neon único): o INQUILINO que
    # esta instalação serve é a empresa com este CNPJ. O bootstrap garante
    # empresa + filial + admin dela, o login busca usuários dentro do
    # inquilino e a licença é por inquilino (licenca.empresa_id).
    # Vazio = modo single-tenant legado (dev/demo, comportamento de antes).
    empresa_cnpj: str = ""
    empresa_razao_social: str = ""
    empresa_filial_nome: str = "Matriz"
    # Instalação nova: o admin nasce sem senha e o operador define a dele na
    # tela "Primeiro acesso" do login. Em dev/testes, desligue para manter a
    # senha de fábrica (`PRINTGEST_ADMIN_INICIAL_PRIMEIRO_ACESSO=false`).
    admin_inicial_primeiro_acesso: bool = False

    redgest_url: str = "http://127.0.0.1:9100"
    redgest_sistema: str = "printgest"
    # Contrato com o RedGest: `c` = Contrato C (chave de produto validada em
    # `/licencas-software/`, vigente) e `b` = Contrato B (`Licenca` v4.0 em
    # `/licencas/`, handshake por CNPJ + código). O default só vira `b` na virada
    # do plano `docs/migracao_redgest_v4.md` (fase M3), depois do piloto.
    redgest_contrato: str = "c"
    # `api_key` do Sistema no RedGest (Contrato C — `/licencas-software/`). É o
    # segredo compartilhado que assina (HMAC-SHA256) cada validação da chave de
    # produto. Sem ele a ativação online não é possível.
    redgest_api_key: str = ""
    # Fingerprint da máquina enviado ao RedGest (doc de integração §7). Vazio =
    # calcula pelo hardware (BIOS UUID / CPU ID / serial da placa-mãe / do disco).
    # Defina para fixar um valor (VMs com SMBIOS ausente, testes ou suporte).
    maquina_fingerprint: str = ""
    # Gating de módulos por plano (PRD v3.0 §2, M0): o middleware `controle_modulos`
    # responde 403 para rotas de módulo fora do `entitlements.modulos`. Desligado
    # por padrão: arma quando o RedGest passar a emitir `modulos` — ligar antes
    # disso bloquearia projetos/financeiro/fiscal do piloto (lição da api_key).
    gating_modulos: bool = False
    # PostgreSQL embarcado (instalador): `true` faz o Local API Service preparar
    # e subir o banco que acompanha a instalação no primeiro uso — initdb, pg_ctl
    # start e CREATE DATABASE (docs/empacotamento.md). Em dev o fluxo continua
    # sendo o `scripts/setup_postgres.ps1` e este módulo não roda.
    pg_embarcado: bool = False
    # Raiz do PostgreSQL embarcado (espera `pgsql\bin` dentro). Vazio = pasta
    # `postgres` ao lado do executável (layout do instalador) no exe congelado,
    # ou `.dev/postgres` quando rodando do repositório.
    pg_raiz: str = ""
    # Cofre do SO para a chave de ativação (§9.4): `dpapi` (Windows, escopo de
    # máquina) ou `nenhum` (grava em texto puro — só para dev/diagnóstico).
    cofre: str = "dpapi"
    # Cópia de recuperação do material de ativação (CNPJ, código e par M2M),
    # fora do banco, para sobreviver à reinstalação/recriação do banco na mesma
    # máquina. Vazio = `%LOCALAPPDATA%\PrintGest\licenca.dat` (Windows) ou
    # `~/.printgest/licenca.dat`. O conteúdo é cifrado com o mesmo DPAPI.
    cofre_licenca_arquivo: str = ""
    licenca_refresh_intervalo_segundos: int = 300
    # Cadência de revalidação online da chave de produto (default 6 h). A licença
    # em si vale até `expira_em`; isso só controla de quanto em quanto tempo o
    # RedGest é consultado para detectar revogação/bloqueio/expiração.
    licenca_revalidar_a_cada_segundos: int = 6 * 60 * 60
    # Resiliência (plano docs/plano_resiliencia_licenca.md): um RedGest em plano
    # gratuito acorda em 30–60 s, então o timeout curto antigo (10 s) fazia a
    # validação falhar justamente no cold start.
    licenca_timeout_segundos: int = 90
    # Tolerância após a vigência (`expira_em`) vencer sem contato com o RedGest.
    # Sem isso o sistema caía em modo leitura no instante do vencimento.
    licenca_tolerancia_horas: int = 72
    # Backoff entre tentativas de renovação após falhas, em CSV de segundos
    # (1, 5, 15 e 60 min — doc de integração §9.2). pydantic-settings não parseia
    # `list[int]` de env de forma confiável — exposto por `licenca_backoff`.
    licenca_backoff_segundos: str = "60,300,900,3600"
    # Jitter (±%) aplicado ao backoff para espaçar clientes que caiam juntos
    # (§9.2: "backoff exponencial com jitter"). 0 desliga.
    licenca_backoff_jitter_percentual: int = 20
    licenca_desabilitada: bool = False

    model_config = {"env_prefix": "PRINTGEST_", "env_file": ".env", "extra": "ignore"}

    @property
    def licenca_backoff(self) -> list[int]:
        """Backoff (segundos) entre tentativas após falhas consecutivas.

        Ignora entradas inválidas; se nada sobrar, devolve o padrão
        (1/5/15/60 min — doc de integração §9.2).
        """
        valores = [
            int(parte.strip())
            for parte in (self.licenca_backoff_segundos or "").split(",")
            if parte.strip().isdigit()
        ]
        return valores or [60, 300, 900, 3600]

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
