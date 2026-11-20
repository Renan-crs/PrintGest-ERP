"""Cliente REST do gateway fiscal de terceiro (NF-e/NFC-e/NFS-e).

O PrintGest não assina nem transmite documentos fiscais: ele monta o payload
da venda/O.S. e entrega a um provedor externo configurado na instalação. A
integração é **genérica** — os caminhos e o cabeçalho de autenticação vêm de
`PRINTGEST_FISCAL_*`, então qualquer provedor REST pode ser adaptado sem
mudar código. Credenciais nunca são gravadas no banco nem no repositório.

O módulo é tolerante a falhas de transporte: devolve
`GatewayResult(ok=False, mensagem=...)` em vez de lançar, para que o serviço
registre a tentativa e mantenha o documento em contingência/rascunho.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import httpx

from app.core.config import Settings, settings
from app.models.enums import StatusFiscal

_STATUS_ALIASES: dict[str, StatusFiscal] = {
    "rascunho": StatusFiscal.RASCUNHO,
    "draft": StatusFiscal.RASCUNHO,
    "processando": StatusFiscal.PROCESSANDO,
    "em_processamento": StatusFiscal.PROCESSANDO,
    "processing": StatusFiscal.PROCESSANDO,
    "autorizado": StatusFiscal.AUTORIZADO,
    "autorizada": StatusFiscal.AUTORIZADO,
    "aprovado": StatusFiscal.AUTORIZADO,
    "approved": StatusFiscal.AUTORIZADO,
    "rejeitado": StatusFiscal.REJEITADO,
    "rejeitada": StatusFiscal.REJEITADO,
    "rejected": StatusFiscal.REJEITADO,
    "cancelado": StatusFiscal.CANCELADO,
    "cancelada": StatusFiscal.CANCELADO,
    "canceled": StatusFiscal.CANCELADO,
    "contingenciado": StatusFiscal.CONTINGENCIADO,
    "contingencia": StatusFiscal.CONTINGENCIADO,
}


def normalizar_status(valor: Any) -> StatusFiscal | None:
    """Converte o status livre do gateway para o enum do produto."""
    if isinstance(valor, StatusFiscal):
        return valor
    texto = str(valor or "").strip().lower()
    if not texto:
        return None
    return _STATUS_ALIASES.get(texto)


@dataclass
class GatewayResult:
    """Resposta normalizada de qualquer provedor de gateway."""

    ok: bool
    status: StatusFiscal | None = None
    dados: dict = field(default_factory=dict)
    mensagem: str | None = None
    gateway_id: str | None = None
    chave_acesso: str | None = None
    numero: int | None = None
    serie: int | None = None
    protocolo: str | None = None
    xml_url: str | None = None
    danfe_url: str | None = None


class GatewayNaoConfigurado(RuntimeError):
    """Nenhuma URL de gateway foi configurada nesta instalação."""


class FiscalGateway:
    """Cliente HTTP — uma instância por chamada (stateless, segura em paralelo)."""

    def __init__(
        self,
        config: Settings | None = None,
        client: httpx.Client | None = None,
        *,
        integracao=None,
        db=None,
        filial_id: int | None = None,
    ):
        self._cfg = config or settings
        self._client = client
        self._integracao = integracao
        self._db = db
        self._filial_id = filial_id or 0

    @property
    def base_url(self) -> str:
        """URL efetiva: integração fiscal do banco tem prioridade sobre `.env`."""
        if self._integracao is not None:
            url = (getattr(self._integracao, "base_url", "") or "").strip()
            if url:
                return url
        return (self._cfg.fiscal_gateway_url or "").strip()

    @property
    def configurado(self) -> bool:
        return bool(self.base_url)

    def _url(self, template: str, **kwargs: Any) -> str:
        base = self.base_url.rstrip("/") + "/"
        caminho = template.lstrip("/").format(**kwargs)
        return urljoin(base, caminho)

    def _headers(self) -> dict[str, str]:
        cabecalhos = {"Accept": "application/json", "Content-Type": "application/json"}
        token = (self._cfg.fiscal_gateway_token or "").strip()
        # PRD v3.3 §3.6: integração fiscal cadastrada na tela de Configurações
        # tem prioridade sobre o token legado de .env (que segue como fallback).
        if self._integracao is not None:
            from app.models.enums import TipoIntegracao
            from app.services import integracao_service

            try:
                token = integracao_service.usar_credencial(
                    self._db,
                    filial_id=self._filial_id,
                    tipo=TipoIntegracao.FISCAL,
                ) or token
                cabecalhos[self._integracao.auth_header or "Authorization"] = (
                    f"{self._integracao.auth_prefix or ''}{token}"
                )
                return cabecalhos
            except Exception:
                pass  # cofre indisponível → mantém o token de .env
        if token:
            nome = (self._cfg.fiscal_gateway_auth_header or "Authorization").strip()
            prefixo = self._cfg.fiscal_gateway_auth_prefix or ""
            cabecalhos[nome] = f"{prefixo}{token}"
        return cabecalhos

    def _request(
        self,
        metodo: str,
        template: str,
        *,
        json_body: dict | None = None,
        **kwargs: Any,
    ) -> GatewayResult:
        if not self.configurado:
            raise GatewayNaoConfigurado(
                "Gateway fiscal não configurado nesta instalação."
            )
        url = self._url(template, **kwargs)
        dono = self._client is None
        cliente = self._client or httpx.Client(
            timeout=self._cfg.fiscal_gateway_timeout_segundos,
            headers=self._headers(),
        )
        try:
            resposta = cliente.request(
                metodo,
                url,
                json=json_body,
                headers=self._headers(),
            )
        except (httpx.HTTPError, OSError) as exc:
            return GatewayResult(ok=False, mensagem=f"Falha de comunicação: {exc}")
        finally:
            if dono:
                cliente.close()

        try:
            corpo = resposta.json()
        except ValueError:
            corpo = None
        dados = corpo if isinstance(corpo, dict) else {"conteudo": resposta.text}
        if not resposta.is_success:
            detalhe = (
                dados.get("message")
                or dados.get("mensagem")
                or dados.get("error")
                or dados.get("detail")
                or resposta.text[:300]
            )
            return GatewayResult(
                ok=False,
                dados=dados,
                mensagem=str(detalhe),
                status=normalizar_status(dados.get("status")),
            )
        return GatewayResult(
            ok=True,
            dados=dados,
            status=normalizar_status(dados.get("status")),
            mensagem=dados.get("mensagem") or dados.get("message"),
            gateway_id=(
                dados.get("id") or dados.get("ref") or dados.get("gateway_id")
            ),
            chave_acesso=dados.get("chave_acesso") or dados.get("chaveNFe"),
            numero=dados.get("numero") or dados.get("numero_nota"),
            serie=dados.get("serie"),
            protocolo=dados.get("protocolo"),
            xml_url=dados.get("xml_url") or dados.get("xml"),
            danfe_url=dados.get("danfe_url") or dados.get("danfe"),
        )

    # --------------------------------------------------------------- operações

    def health(self) -> bool:
        """Checagem leve de disponibilidade (não lança)."""
        if not self.configurado or not (
            self._cfg.fiscal_gateway_health_path or ""
        ).strip():
            return False
        try:
            return self._request("GET", self._cfg.fiscal_gateway_health_path).ok
        except GatewayNaoConfigurado:
            return False

    def emitir(self, payload: dict) -> GatewayResult:
        """Envia o payload fiscal montado pelo serviço."""
        return self._request(
            "POST", self._cfg.fiscal_gateway_emitir_path, json_body=payload
        )

    def consultar(self, gateway_id: str) -> GatewayResult:
        return self._request(
            "GET", self._cfg.fiscal_gateway_consultar_path, id=gateway_id
        )

    def cancelar(self, gateway_id: str, motivo: str) -> GatewayResult:
        return self._request(
            "POST",
            self._cfg.fiscal_gateway_cancelar_path,
            json_body={"motivo": motivo},
            id=gateway_id,
        )
