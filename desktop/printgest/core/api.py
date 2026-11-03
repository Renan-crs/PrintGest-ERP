"""Cliente do Local API Service (daemon 127.0.0.1:8000).

Encapsula as chamadas de autenticação e licenciamento usadas pelas telas 1.x.
Qualquer resposta `>= 400` vira uma `ApiError` com o `detail` em PT-BR vindo da
API — a UI só precisa apresentar a mensagem.
"""

from __future__ import annotations

import os

import httpx

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 8.0

_LIGADO = {"1", "true", "yes", "on", "sim"}


def _novo_cliente(**kwargs) -> httpx.Client:
    """Cria o cliente HTTP sem herdar a configuração de TLS do ambiente.

    O httpx honra a variável `SSLKEYLOGFILE` ao montar o contexto TLS e tenta
    abrir o arquivo apontado por ela. Em algumas máquinas essa variável aponta
    para um arquivo na raiz de um volume sem permissão de escrita para o
    usuário comum (ex.: ``\\\\?\\Volume{...}\\virtual_file.log``), e a
    inicialização quebra com ``PermissionError: [Errno 13]``.

    O Local API Service é local (HTTP), então não há motivo para herdar
    proxy/CA/keylog do ambiente do Windows. `trust_env=False` também evita
    que variáveis como `HTTP_PROXY` desviem chamadas para 127.0.0.1.
    """
    kwargs.setdefault("trust_env", False)
    return httpx.Client(**kwargs)


def base_url_padrao() -> str:
    """Endereço do Local API Service: o do servidor (modo Estação) ou o local.

    O instalador de uma estação define `PRINTGEST_API_URL` apontando para a
    máquina servidora da gráfica; sem a variável, o alvo é o daemon local
    embutido no modo Servidor.
    """
    endereco = os.environ.get("PRINTGEST_API_URL", "").strip()
    if not endereco:
        return BASE_URL
    if "://" not in endereco:
        endereco = f"http://{endereco}"
    return endereco.rstrip("/")


def modo_estacao() -> bool:
    """True quando esta instalação é uma estação (servidor em outra máquina)."""
    return bool(os.environ.get("PRINTGEST_API_URL", "").strip()) or os.environ.get(
        "PRINTGEST_MODO_ESTACAO", ""
    ).strip().lower() in _LIGADO


class ApiError(Exception):
    """Falha mapeada da API (detail em PT-BR) ou de comunicação."""


def _detalhe(resp: httpx.Response) -> str:
    try:
        corpo = resp.json()
    except ValueError:
        return "Resposta inválida do Local API Service."
    return corpo.get("detail") or "Falha no Local API Service."


class Api:
    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._cliente = _novo_cliente(
            base_url=base_url, timeout=timeout, transport=transport
        )
        self._token: str | None = None
        self._usuario: dict | None = None

    @property
    def base_url_display(self) -> str:
        """URL amigável do daemon (sem o esquema) para a UI."""
        return self._cliente.base_url.host + (
            f":{self._cliente.base_url.port}" if self._cliente.base_url.port else ""
        )

    def fechar(self) -> None:
        self._cliente.close()

    # ------------------------------------------------------------ sessão

    @property
    def autenticado(self) -> bool:
        return self._token is not None

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def usuario(self) -> dict | None:
        return self._usuario

    def autenticar(self, dados_login: dict) -> dict:
        """Guarda token + usuário retornados pelo `/v1/auth/login`."""
        self._token = dados_login["token"]
        self._usuario = dados_login["usuario"]
        return dados_login

    def encerrar_sessao(self) -> None:
        self._token = None
        self._usuario = None

    def logout(self) -> None:
        """Encerra a sessão no servidor e limpa o token local.

        `POST /v1/auth/logout` é **best-effort**: se o daemon não responder, a
        sessão local ainda é limpa (o usuário não fica preso a um token morto).
        """
        try:
            self._post("/v1/auth/logout", {}, self._token)
        except (ApiError, httpx.HTTPError):
            pass
        self.encerrar_sessao()

    # ------------------------------------------------------------ CRUD

    def listar(self, entidade: str, q: str = "", limit: int = 50, offset: int = 0) -> dict:
        """Lista paginada com busca rápida: `{ \"data\": [...], \"total\": n, \"limit\": .., \"offset\": .. }`."""
        return self.listar_com_filtros(entidade, q=q, limit=limit, offset=offset)

    def listar_com_filtros(
        self, entidade: str, q: str = "", limit: int = 50, offset: int = 0, **params
    ) -> dict:
        """Como `listar`, mas aceita filtros adicionais (status, tipo...)."""
        query = {"q": q, "limit": limit, "offset": offset}
        for chave, valor in params.items():
            if valor is not None and valor != "":
                query[chave] = valor
        resp = self._cliente.get(
            f"/v1/{entidade}", params=query, headers=self._headers(self._token)
        )
        return self._paginar(self._resposta_completa(resp))

    def listar_os(
        self,
        q: str = "",
        status: str | None = None,
        tipo: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        return self.listar_com_filtros(
            "os", q=q, status=status, tipo=tipo, limit=limit, offset=offset
        )

    def listar_vendas(
        self,
        q: str = "",
        status_venda: str | None = None,
        forma_pagamento: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        return self.listar_com_filtros(
            "vendas",
            q=q,
            status_venda=status_venda,
            forma_pagamento=forma_pagamento,
            limit=limit,
            offset=offset,
        )

    def atualizar_status(self, item_id: int, status: str) -> dict:
        """Avanço de status da O.S.: `PATCH /v1/os/{id}/status`."""
        resp = self._cliente.patch(
            f"/v1/os/{item_id}/status",
            json={"status": status},
            headers=self._headers(self._token),
        )
        return self._tratar(resp)

    # ----------------------------------------------------------- projetos
    # Módulo Quadro Kanban (PRD Módulo Projetos). Namespace `/v1/projetos`,
    # independente de `/v1/os`: o cartão é a unidade (não mais "1 projeto = 1
    # O.S."). A ordenação é um **índice** 0-based (`posicao` no corpo) e a
    # edição usa controle otimista via `versao` (enviar a versão lida).

    def obter_quadro(self) -> dict:
        """Quadro da filial com as listas ativas: `GET /v1/projetos/quadro`."""
        return self._get("/v1/projetos/quadro", self._token)

    def listar_cartoes(
        self,
        q: str = "",
        lista_id: int | None = None,
        arquivado: bool = False,
        sou_membro: bool | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict:
        """Cartões visíveis ao usuário: `GET /v1/projetos/cartoes`."""
        return self.listar_com_filtros(
            "projetos/cartoes",
            q=q,
            lista_id=lista_id,
            arquivado=arquivado,
            sou_membro=sou_membro,
            limit=limit,
            offset=offset,
        )

    def criar_cartao(self, payload: dict) -> dict:
        return self._post("/v1/projetos/cartoes", payload, self._token)

    def obter_cartao(self, cartao_id: int) -> dict:
        return self._get(f"/v1/projetos/cartoes/{cartao_id}", self._token)

    def atualizar_cartao(self, cartao_id: int, payload: dict) -> dict:
        return self._patch(f"/v1/projetos/cartoes/{cartao_id}", payload, self._token)

    def mover_cartao(self, cartao_id: int, payload: dict) -> dict:
        """Move para `lista_id`/`posicao` (índice) com `versao` (§10)."""
        return self._patch(
            f"/v1/projetos/cartoes/{cartao_id}/mover", payload, self._token
        )

    def arquivar_cartao(self, cartao_id: int, versao: int) -> dict:
        return self._patch(
            f"/v1/projetos/cartoes/{cartao_id}/arquivar", {"versao": versao}, self._token
        )

    def restaurar_cartao(self, cartao_id: int, versao: int) -> dict:
        return self._patch(
            f"/v1/projetos/cartoes/{cartao_id}/restaurar", {"versao": versao}, self._token
        )

    def atribuir_cartao(self, cartao_id: int, versao: int, usuario_id: int) -> dict:
        return self._patch(
            f"/v1/projetos/cartoes/{cartao_id}/atribuir",
            {"versao": versao, "usuario_id": usuario_id},
            self._token,
        )

    def adicionar_membro(self, cartao_id: int, usuario_id: int) -> dict:
        return self._post(
            f"/v1/projetos/cartoes/{cartao_id}/membros",
            {"usuario_id": usuario_id},
            self._token,
        )

    def remover_membro(self, cartao_id: int, membro_id: int) -> dict:
        return self._delete_data(
            f"/v1/projetos/cartoes/{cartao_id}/membros/{membro_id}", self._token
        )

    def criar_lista(self, payload: dict) -> dict:
        return self._post("/v1/projetos/quadro/listas", payload, self._token)

    def atualizar_lista(self, lista_id: int, payload: dict) -> dict:
        return self._patch(
            f"/v1/projetos/quadro/listas/{lista_id}", payload, self._token
        )

    def arquivar_lista(self, lista_id: int) -> dict:
        return self._patch(
            f"/v1/projetos/quadro/listas/{lista_id}/arquivar", {}, self._token
        )

    def excluir_lista(self, lista_id: int) -> None:
        self._delete(f"/v1/projetos/quadro/listas/{lista_id}", self._token)

    # --------------------------------------------------------- agendamento

    def listar_agendamentos(
        self,
        inicio: str | None = None,
        fim: str | None = None,
        tipo: str | None = None,
        status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict:
        """Janela de datas (ISO) para o calendário: `GET /v1/agendamento`."""
        return self.listar_com_filtros(
            "agendamento",
            inicio=inicio,
            fim=fim,
            tipo=tipo,
            status=status,
            limit=limit,
            offset=offset,
        )

    def criar_agendamento(self, payload: dict) -> dict:
        return self._post("/v1/agendamento", payload)

    def obter_agendamento(self, item_id: int) -> dict:
        return self._get(f"/v1/agendamento/{item_id}")

    def atualizar_agendamento(self, item_id: int, payload: dict) -> dict:
        return self._put(f"/v1/agendamento/{item_id}", payload)

    def concluir_agendamento(self, item_id: int) -> dict:
        return self._patch(f"/v1/agendamento/{item_id}/concluir")

    def remover_agendamento(self, item_id: int) -> None:
        self._delete(f"/v1/agendamento/{item_id}")

    # ------------------------------------------------------------ estoque

    def consulta_estoque(
        self,
        q: str = "",
        categoria_id: int | None = None,
        abaixo_minimo: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Consulta de saldos: `GET /v1/estoque` (mockup 4.1)."""
        return self.listar_com_filtros(
            "estoque",
            q=q,
            categoria_id=categoria_id,
            abaixo_minimo=abaixo_minimo,
            limit=limit,
            offset=offset,
        )

    def resumo_estoque(
        self,
        q: str = "",
        categoria_id: int | None = None,
        abaixo_minimo: bool = False,
    ) -> dict:
        """KPIs da consulta (itens, valor, bobinas, abaixo do mínimo)."""
        params = {"q": q, "abaixo_minimo": abaixo_minimo}
        if categoria_id is not None:
            params["categoria_id"] = categoria_id
        resp = self._cliente.get(
            "/v1/estoque/resumo",
            params=params,
            headers=self._headers(self._token),
        )
        return self._tratar(resp)

    def kardex_estoque(
        self,
        produto_id: int,
        tipo: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """Ficha kardex de um insumo: `GET /v1/estoque/{produto_id}/kardex`."""
        params = {"limit": limit, "offset": offset}
        if tipo:
            params["tipo"] = tipo
        resp = self._cliente.get(
            f"/v1/estoque/{produto_id}/kardex",
            params=params,
            headers=self._headers(self._token),
        )
        return self._paginar(self._resposta_completa(resp))

    def reposicao_estoque(
        self,
        q: str = "",
        apenas_abaixo: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """Relatório de reposição e giro: `GET /v1/estoque/reposicao`."""
        return self.listar_com_filtros(
            "estoque/reposicao",
            q=q,
            apenas_abaixo=apenas_abaixo,
            limit=limit,
            offset=offset,
        )

    def movimentar_estoque(self, payload: dict) -> dict:
        """Lançamento manual de estoque: `POST /v1/estoque/movimentar`."""
        return self._post("/v1/estoque/movimentar", payload, self._token)

    # ---------------------------------------------------------- financeiro

    def caixa_atual(self) -> dict | None:
        """Caixa aberto do usuário (ou `None`): `GET /v1/financeiro/caixa/atual`."""
        return self._get("/v1/financeiro/caixa/atual", self._token)

    def abrir_caixa(self, payload: dict) -> dict:
        return self._post("/v1/financeiro/caixa/abrir", payload, self._token)

    def fechar_caixa(self, caixa_id: int, payload: dict) -> dict:
        return self._post(f"/v1/financeiro/caixa/{caixa_id}/fechar", payload, self._token)

    def movimento_caixa(self, caixa_id: int, payload: dict) -> dict:
        return self._post(f"/v1/financeiro/caixa/{caixa_id}/movimento", payload, self._token)

    def extrato_caixa(self, caixa_id: int, limit: int = 200, offset: int = 0) -> dict:
        """Extrato (movimentos) de um caixa: `GET /v1/financeiro/caixa/{id}/extrato`."""
        return self.listar_com_filtros(
            f"financeiro/caixa/{caixa_id}/extrato", limit=limit, offset=offset
        )

    def baixa_conta(self, tipo: str, conta_id: int, payload: dict) -> dict:
        """Baixa de título: `POST /v1/financeiro/{contas-receber|contas-pagar}/{id}/baixa`."""
        return self._post(f"/v1/financeiro/{tipo}/{conta_id}/baixa", payload, self._token)

    # -------------------------------------------------------------- fiscal

    def documentos_fiscais(
        self,
        q: str = "",
        status_fiscal: str | None = None,
        modelo: str | None = None,
        contingencia: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Consulta de documentos fiscais: `GET /v1/fiscal/documentos`."""
        return self.listar_com_filtros(
            "fiscal/documentos",
            q=q,
            status_fiscal=status_fiscal,
            modelo=modelo,
            contingencia=contingencia,
            limit=limit,
            offset=offset,
        )

    def documento_fiscal(self, item_id: int) -> dict:
        return self.obter("fiscal/documentos", item_id)

    def resumo_fiscal(self) -> dict:
        """Panorama fiscal usado pela tela de contingência: `GET /v1/fiscal/resumo`."""
        return self._get("/v1/fiscal/resumo", self._token)

    # --------------------------------------------------------- configuração

    def empresa(self) -> dict:
        """Dados da empresa ativa: `GET /v1/config/empresa`."""
        return self._get("/v1/config/empresa", self._token)

    def atualizar_empresa(self, payload: dict) -> dict:
        """Dados da Empresa / Personalização (parcial): `PUT /v1/config/empresa`."""
        return self._put("/v1/config/empresa", payload, self._token)

    def simular_reajuste(self, payload: dict) -> dict:
        """Prévia do reajuste em bloco: `POST /v1/config/reajuste/simular`."""
        return self._post("/v1/config/reajuste/simular", payload, self._token)

    def aplicar_reajuste(self, payload: dict) -> dict:
        """Aplica o reajuste (exige senha): `POST /v1/config/reajuste/aplicar`."""
        return self._post("/v1/config/reajuste/aplicar", payload, self._token)

    def reajuste_historico(self, limit: int = 20, offset: int = 0) -> dict:
        """Trilha de auditoria: `GET /v1/config/reajuste/historico`."""
        return self.listar_com_filtros(
            "config/reajuste/historico", limit=limit, offset=offset
        )

    def acao(self, entidade: str, item_id: int, acao: str, payload: dict | None = None) -> dict:
        """POST de ação de negócio, ex.: `/v1/os/5/converter`."""
        resp = self._cliente.post(
            f"/v1/{entidade}/{item_id}/{acao}",
            json=payload or {},
            headers=self._headers(self._token),
        )
        return self._tratar(resp)

    def obter(self, entidade: str, item_id: int) -> dict:
        return self._get(f"/v1/{entidade}/{item_id}", self._token)

    def criar(self, entidade: str, payload: dict) -> dict:
        return self._post(f"/v1/{entidade}", payload, self._token)

    def atualizar(self, entidade: str, item_id: int, payload: dict) -> dict:
        return self._put(f"/v1/{entidade}/{item_id}", payload, self._token)

    def excluir(self, entidade: str, item_id: int) -> None:
        self._delete(f"/v1/{entidade}/{item_id}", self._token)

    def login(self, login: str, senha: str) -> dict:
        return self._post("/v1/auth/login", {"login": login, "senha": senha})

    def situacao_licenca(self, token: str | None = None) -> dict:
        return self._get("/v1/licenca", token)

    # A ativação conversa com o RedGest, que em plano gratuito acorda em 30–60 s
    # (PRD §4.3: timeout ≥ 90 s). O timeout padrão do cliente (8 s) serviria só
    # para o daemon local — aqui a chamada atravessa daemon + RedGest.
    TIMEOUT_ATIVACAO_SEGUNDOS = 95.0

    def cliente_para_ativacao(self) -> httpx.Client:
        """Cliente dedicado da ativação: fechável para abortar a espera (D2).

        Fechar o cliente em pleno voo interrompe a requisição de verdade; o
        cliente compartilhado segue intocado para o resto da aplicação.
        """
        return _novo_cliente(
            base_url=self._base_url,
            timeout=self.TIMEOUT_ATIVACAO_SEGUNDOS,
            transport=self._transport,
        )

    def ativar_licenca(
        self,
        token: str | None,
        chave: str | None = None,
        *,
        cnpj: str | None = None,
        codigo: str | None = None,
        cliente: httpx.Client | None = None,
    ) -> dict:
        corpo: dict[str, str] = {}
        if chave:
            corpo["chave_ativacao"] = chave
        if cnpj:
            corpo["cnpj"] = cnpj
        if codigo:
            corpo["codigo_licenca"] = codigo
        if cliente is not None:
            resp = cliente.post(
                "/v1/licenca/ativar", json=corpo, headers=self._headers(token)
            )
            return self._tratar(resp)
        return self._post(
            "/v1/licenca/ativar",
            corpo,
            token,
            timeout=self.TIMEOUT_ATIVACAO_SEGUNDOS,
        )

    def renovar_licenca(self, token: str | None) -> dict:
        return self._post("/v1/licenca/renovar", {}, token)

    def testar_comunicacao(self) -> bool:
        try:
            resp = self._cliente.get("/health", timeout=3.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def verificar_atualizacao(self, versao_atual: str) -> dict | None:
        """Verifica se existe atualização disponível: `GET /v1/atualizacao/verificar`.
        
        Retorna None se estiver atualizado, ou dict com:
        - versao_nova: str
        - download_url: str  
        - revisoes: list[str]
        - data: str
        """
        tipo = "estacao" if modo_estacao() else "servidor"
        resp = self._cliente.get(
            f"/v1/atualizacao/verificar?versao={versao_atual}&tipo={tipo}",
            timeout=5.0,
        )
        if resp.status_code != 200:
            return None
        dados = resp.json()
        if dados.get("atualizado"):
            return None
        return dados.get("data")

    def resumo_dashboard(self, dias: int = 7) -> dict:
        """KPIs da Tela Inicial: `GET /v1/dashboard/resumo?dias=`."""
        return self._get("/v1/dashboard/resumo", self._token, params={"dias": dias})

    # ------------------------------------------------------------- cotações (M1)
    # Item de fornecedor: o comparativo e o lançamento são rotas de OS.

    def listar_cotacoes(self, os_id: int, item_id: int) -> dict:
        """`GET /v1/os/{os_id}/itens/{item_id}/cotacoes` — comparativo interno.

        VF/snapshot **omitidos** pelo servidor para Operador/Caixa.
        """
        return self._get(
            f"/v1/os/{os_id}/itens/{item_id}/cotacoes", self._token
        )

    def lancar_cotacao(
        self, os_id: int, item_id: int, corpo: dict
    ) -> dict:
        """`POST /v1/os/{os_id}/itens/{item_id}/cotacoes` — Gerente/Admin."""
        return self._post(
            f"/v1/os/{os_id}/itens/{item_id}/cotacoes", corpo, self._token
        )

    def selecionar_cotacao(
        self, os_id: int, item_id: int, cotacao_id: int
    ) -> dict:
        """`PUT .../cotacoes/{cotacao_id}/selecionar` — marca a escolhida."""
        resp = self._cliente.put(
            f"/v1/os/{os_id}/itens/{item_id}/cotacoes/{cotacao_id}/selecionar",
            headers=self._headers(self._token),
        )
        return self._tratar(resp)

    # ------------------------------------------------------------- arte (M3, §3.5)
    # Versões da arte, decisão do cliente (aprovada/ajuste) e link público.

    def arte(self, os_id: int) -> dict:
        """`GET /v1/os/{os_id}/arte` — resposta COMPLETA (data + estado derivado).

        O estado (`sem_arte` / `aguardando_aprovacao` / `ajuste_solicitado` /
        `aprovada`) olha a decisão sobre a última versão enviada (§3.5).
        """
        resp = self._cliente.get(
            f"/v1/os/{os_id}/arte", headers=self._headers(self._token)
        )
        return self._resposta_completa(resp)

    def enviar_arte(self, os_id: int, caminho: str) -> dict:
        """`POST /v1/os/{os_id}/arte` — upload multipart de nova versão (v1, v2…)."""
        from mimetypes import guess_type
        from pathlib import Path

        arquivo = Path(caminho)
        mime = guess_type(arquivo.name)[0] or "application/octet-stream"
        with arquivo.open("rb") as f:
            resp = self._cliente.post(
                f"/v1/os/{os_id}/arte",
                files={"arquivo": (arquivo.name, f, mime)},
                headers=self._headers(self._token),
                timeout=120.0,
            )
        return self._tratar(resp)

    def decidir_arte(
        self, os_id: int, versao_id: int, decisao: str, comentarios: str | None = None
    ) -> dict:
        """`POST /v1/os/{os_id}/arte/{versao_id}/decisao` — aprovada/ajuste (§3.5).

        `ajuste` exige comentários (o servidor responde 400 sem eles).
        """
        corpo: dict = {"decisao": decisao}
        if comentarios:
            corpo["comentarios"] = comentarios
        return self._post(
            f"/v1/os/{os_id}/arte/{versao_id}/decisao", corpo, self._token
        )

    def link_arte(self, os_id: int) -> dict:
        """`POST /v1/os/{os_id}/arte/link` — token público da prova (uso único).

        O relay hospedado (decisão D-03) resolve o token; a expiração vem do
        servidor (72 h por padrão).
        """
        return self._post(f"/v1/os/{os_id}/arte/link", {}, self._token)

    def _get(
        self, path: str, token: str | None = None, params: dict | None = None
    ) -> dict:
        resp = self._cliente.get(path, headers=self._headers(token), params=params)
        return self._tratar(resp)

    def _post(
        self, path: str, payload: dict, token: str | None = None, timeout: float | None = None
    ) -> dict:
        kwargs: dict = {"json": payload, "headers": self._headers(token)}
        if timeout is not None:
            kwargs["timeout"] = timeout
        resp = self._cliente.post(path, **kwargs)
        return self._tratar(resp)

    def _put(self, path: str, payload: dict, token: str | None = None) -> dict:
        resp = self._cliente.put(path, json=payload, headers=self._headers(token))
        return self._tratar(resp)

    def _patch(self, path: str, payload: dict | None = None, token: str | None = None) -> dict:
        resp = self._cliente.patch(
            path, json=payload or {}, headers=self._headers(token)
        )
        return self._tratar(resp)

    def _delete(self, path: str, token: str | None = None) -> None:
        resp = self._cliente.delete(path, headers=self._headers(token))
        if resp.status_code >= 400:
            raise ApiError(_detalhe(resp))

    def _delete_data(self, path: str, token: str | None = None) -> dict:
        """DELETE que devolve o corpo `data` (ex.: remover membro de um cartão)."""
        resp = self._cliente.delete(path, headers=self._headers(token))
        return self._tratar(resp)

    @staticmethod
    def _headers(token: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"} if token else {}

    @staticmethod
    def _tratar(resp: httpx.Response) -> dict:
        if resp.status_code >= 400:
            raise ApiError(_detalhe(resp))
        return resp.json()["data"]

    @staticmethod
    def _paginar(corpo: dict) -> dict:
        """Normaliza uma resposta paginada em `{data, total, limit, offset}`."""
        return {
            "data": corpo["data"],
            "total": corpo["meta"]["total"],
            "limit": corpo["meta"]["limit"],
            "offset": corpo["meta"]["offset"],
        }

    @staticmethod
    def _resposta_completa(resp: httpx.Response) -> dict:
        if resp.status_code >= 400:
            raise ApiError(_detalhe(resp))
        return resp.json()