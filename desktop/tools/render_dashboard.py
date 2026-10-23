"""Renderiza a Tela Inicial (Dashboard) para PNG sem abrir janela real."""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from printgest.core.api import Api  # noqa: E402
from printgest.ui.theme import aplicar_theme  # noqa: E402
from printgest.ui.tela_principal import TelaPrincipal  # noqa: E402

HOJE = date.today()


def resumo(dias: int = 7) -> dict:
    return {
        "filial_nome": "Filial Matriz",
        "vendas_hoje_qtd": 7,
        "vendas_hoje_valor": "112.40",
        "vendas_ontem_qtd": 5,
        "vendas_ontem_valor": "88.20",
        "projetos_em_producao": 3,
        "projetos_atrasados": 1,
        "a_receber_vence_hoje": "150.00",
        "a_receber_atrasado": "40.50",
        "estoque_abaixo_minimo": 4,
        "entregas_hoje": [
            {
                "os_id": 1,
                "numero": "OS-001",
                "cliente_nome": "Ana Souza",
                "servico": "Impressao de cartoes",
                "prazo": HOJE.isoformat(),
                "status": "producao",
                "atrasada": False,
            },
            {
                "os_id": 2,
                "numero": "OS-002",
                "cliente_nome": "Biz Ltda",
                "servico": "Plotagem A0",
                "prazo": (HOJE - timedelta(days=1)).isoformat(),
                "status": "producao",
                "atrasada": True,
            },
        ],
        "vendas_7_dias": [
            {"data": (HOJE - timedelta(days=i)).isoformat(), "valor": f"{i * 40 + 55}.00"}
            for i in range(dias)
        ],
        "faturamento_previsto": [
            {"data": (HOJE + timedelta(days=i)).isoformat(), "valor": f"{i * 33 + 20}.00"}
            for i in range(dias)
        ],
    }


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/dashboard/resumo":
        return httpx.Response(200, json={"data": resumo()})
    if request.url.path == "/v1/licenca":
        return httpx.Response(200, json={"data": {"status": "ativa", "modo_leitura": False}})
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "ok"})
    return httpx.Response(404, json={"detail": "x"})


def main() -> None:
    app = QApplication(sys.argv)
    aplicar_theme(app)
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler))
    api.autenticar(
        {"token": "tok", "usuario": {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"}}
    )
    tela = TelaPrincipal(api, usuario=api.usuario, base_url="127.0.0.1:8000")
    tela.resize(1440, 900)
    tela.show()

    destino = Path(__file__).resolve().parents[1] / "dashboard_preview.png"

    def capturar() -> None:
        tela.grab().save(str(destino))
        print(f"salvo: {destino}")
        app.quit()

    QTimer.singleShot(1600, capturar)
    app.exec()


if __name__ == "__main__":
    main()
