"""Renderiza a tela de ativação (serial) em PNG, sem abrir janela real.

Uso:
    desktop\\.venv\\Scripts\\python.exe desktop\\tools\\render_ativacao.py <c|b> <inicial|erro|validando|sucesso> [largura altura] [escala]

Exemplos:
    render_ativacao.py b inicial
    render_ativacao.py b erro 1280 720 150

Gera `ativacao_<contrato>_<estado>_<WxH>@<escala>_preview.png` na raiz do
desktop (gitignored). Os PNGs alimentam a inspeção visual por resolução/escala
(critérios de aceite da revisão — docs/revisao_tela_ativacao.md).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from printgest.core.api import Api  # noqa: E402
from printgest.ui.ativacao import AtivacaoWindow  # noqa: E402
from printgest.ui.theme import aplicar_theme  # noqa: E402

CONTRATO = (sys.argv[1] if len(sys.argv) > 1 else "b").strip().lower()
ESTADO = (sys.argv[2] if len(sys.argv) > 2 else "inicial").strip().lower()
LARGURA = int(sys.argv[3]) if len(sys.argv) > 3 else 1280
ALTURA = int(sys.argv[4]) if len(sys.argv) > 4 else 720
ESCALA = sys.argv[5] if len(sys.argv) > 5 else "100"

if CONTRATO not in {"c", "b"}:
    raise SystemExit("contrato inválido: use 'c' ou 'b'")
if ESCALA not in {"100", "125", "150"}:
    raise SystemExit("escala inválida: use 100, 125 ou 150")
os.environ["QT_SCALE_FACTOR"] = str(int(ESCALA) / 100)

SITUACAO_ATIVA = {
    "status": "ativa",
    "modo_leitura": False,
    "plano": "ANUAL",
    "expira_em": "2027-10-19T00:56:26",
}


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "ok"})
    if request.url.path == "/v1/licenca/ativar":
        return httpx.Response(200, json={"data": SITUACAO_ATIVA})
    return httpx.Response(404, json={"detail": "x"})


def preparar_estado(tela: AtivacaoWindow) -> None:
    if ESTADO == "erro":
        if tela._contrato_b:
            tela._campo_cnpj.setText("11222333000182")  # DV inválido
            tela._validar_cnpj()
            tela._erro.setText(
                "Não conseguimos falar com o servidor de licenças. "
                "Verifique a internet e tente novamente."
            )
        else:
            tela._campo_chave.setText("A3F1-9C2B")
            tela._marcar_erro_campo(
                tela._campo_chave,
                tela._erro_chave,
                "Informe a chave completa (XXXX-XXXX-XXXX-XXXX).",
            )
    elif ESTADO == "validando":
        if tela._contrato_b:
            tela._campo_cnpj.setText("11.222.333/0001-81")
            tela._campo_codigo.setText("ABC-1234-XYZ")
        else:
            tela._campo_chave.setText("A3F1-9C2B-77DE-1045")
        tela._entrar_em_validacao()
    elif ESTADO == "sucesso":
        tela._definir_passo(3)
        tela._preencher_sucesso(SITUACAO_ATIVA)
        tela._cartao.setCurrentIndex(1)


def main() -> None:
    app = QApplication(sys.argv[:1])
    aplicar_theme(app)
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler))
    tela = AtivacaoWindow(api, token=None, contrato=CONTRATO)
    tela.resize(LARGURA, ALTURA)
    tela.show()
    preparar_estado(tela)

    destino = (
        Path(__file__).resolve().parents[1]
        / f"ativacao_{CONTRATO}_{ESTADO}_{LARGURA}x{ALTURA}@{ESCALA}_preview.png"
    )

    def capturar() -> None:
        tela.grab().save(str(destino))
        print(f"salvo: {destino}")
        app.quit()

    QTimer.singleShot(300, capturar)
    app.exec()


if __name__ == "__main__":
    main()
