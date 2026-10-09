"""Mixin da condição de pagamento antecipado do cliente (O.S. e Venda Balcão).

O cliente pode ser marcado com `pagamento_adiantado` (100% do total) **ou**
`sinal` (`sinal_pct%` do total) — nunca os dois. Quando qualquer uma dessas
condições existe, criar O.S./venda exige confirmar o recebimento.

Centraliza o cache de flags por cliente, o rótulo dinâmico do check-box e o
gate de validação. A subclasse precisa criar, em `_secoes()`, `self._cliente`
(`CampoCombo`) e `self._pagamento_confirmado` (`CampoCheck`).
"""

from __future__ import annotations

from printgest.core import catalogos
from printgest.ui.formulario import formatar_percentual


class CondicaoPagamentoCliente:
    """Fonte única da regra de confirmação de pagamento para a UI."""

    def _iniciar_condicao_pagamento(self) -> None:
        self._cliente_flags: dict = {}

    def _carregar_clientes_flags(self) -> None:
        catalogos.carregar(
            "clientes",
            lambda: self._api.listar("clientes", limit=1000),
            on_ok=self._clientes_flags_recebidos,
        )

    def _clientes_flags_recebidos(self, saida: dict) -> None:
        dados = saida.get("data", [])
        self._cliente_flags = {
            r["id"]: (
                bool(r.get("pagamento_adiantado")),
                bool(r.get("sinal")),
                r.get("sinal_pct"),
            )
            for r in dados
        }
        self._cliente.alterar_opcoes([(r["id"], r["nome_razao"]) for r in dados])
        self._cliente_mudou()

    def _cliente_mudou(self) -> None:
        adiantado, sinal, pct = self._cliente_flags.get(
            self._cliente.valor(), (False, False, None)
        )
        if adiantado:
            texto = "Recebimento confirmado — pagamento adiantado (total)"
        elif sinal:
            texto = f"Recebimento confirmado — sinal de {formatar_percentual(pct)}%"
        else:
            texto = "Recebimento confirmado (sem exigência do cliente)"
        self._pagamento_confirmado.widget.setText(texto)

    def _exigencia_pendente(self) -> str | None:
        """Rótulo curto da condição não confirmada, ou `None` quando liberado."""
        adiantado, sinal, _pct = self._cliente_flags.get(
            self._cliente.valor(), (False, False, None)
        )
        if (adiantado or sinal) and not self._pagamento_confirmado.valor():
            return "pagamento adiantado (total)" if adiantado else "sinal"
        return None

    def _exigencia_do_cliente(self, cliente_id) -> str | None:
        """Rótulo descritivo da condição de um cliente, ou `None` se não houver."""
        adiantado, sinal, pct = self._cliente_flags.get(
            cliente_id, (False, False, None)
        )
        if adiantado:
            return "pagamento adiantado (total)"
        if sinal:
            return f"sinal de {formatar_percentual(pct)}%"
        return None
