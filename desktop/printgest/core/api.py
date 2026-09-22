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

    def fechar(self) -> None:
        self._cliente.close()

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

    def _get(self, path: str, token: str | None = None) -> dict:
        resp = self._cliente.get(path, headers=self._headers(token))
        return self._tratar(resp)

    def _post(self, path: str, payload: dict, token: str | None = None) -> dict:
        resp = self._cliente.post(path, json=payload, headers=self._headers(token))
        return self._tratar(resp)

    @staticmethod
    def _headers(token: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"} if token else {}

    @staticmethod
    def _tratar(resp: httpx.Response) -> dict:
        if resp.status_code >= 400:
            raise ApiError(_detalhe(resp))
        return resp.json()["data"]