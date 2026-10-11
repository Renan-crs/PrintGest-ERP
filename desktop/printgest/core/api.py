"""Cliente do Local API Service (daemon 127.0.0.1:8000).

Encapsula as chamadas de autenticação e licenciamento usadas pelas telas 1.x.
Qualquer resposta `>= 400` vira uma `ApiError` com o `detail` em PT-BR vindo da
API — a UI só precisa apresentar a mensagem.
"""

from __future__ import annotations

import httpx

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 8.0


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
        self._cliente = httpx.Client(
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

    def ativar_licenca(self, token: str | None, cnpj: str, codigo: str) -> dict:
        return self._post(
            "/v1/licenca/ativar",
            {"cnpj": cnpj, "codigo_licenca": codigo},
            token,
        )

    def renovar_licenca(self, token: str | None) -> dict:
        return self._post("/v1/licenca/renovar", {}, token)

    def testar_comunicacao(self) -> bool:
        try:
            resp = self._cliente.get("/health", timeout=3.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def resumo_dashboard(self, dias: int = 7) -> dict:
        """KPIs da Tela Inicial: `GET /v1/dashboard/resumo?dias=`."""
        return self._get("/v1/dashboard/resumo", self._token, params={"dias": dias})

    def _get(
        self, path: str, token: str | None = None, params: dict | None = None
    ) -> dict:
        resp = self._cliente.get(path, headers=self._headers(token), params=params)
        return self._tratar(resp)

    def _post(self, path: str, payload: dict, token: str | None = None) -> dict:
        resp = self._cliente.post(path, json=payload, headers=self._headers(token))
        return self._tratar(resp)

    def _put(self, path: str, payload: dict, token: str | None = None) -> dict:
        resp = self._cliente.put(path, json=payload, headers=self._headers(token))
        return self._tratar(resp)

    def _delete(self, path: str, token: str | None = None) -> None:
        resp = self._cliente.delete(path, headers=self._headers(token))
        if resp.status_code >= 400:
            raise ApiError(_detalhe(resp))

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