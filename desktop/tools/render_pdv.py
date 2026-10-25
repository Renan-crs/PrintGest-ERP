"""Renderiza o PDV em PNG (offscreen) para inspeção visual da revisão.

Uso:
    desktop\\.venv\\Scripts\\python.exe desktop\\tools\\render_pdv.py [vazio|com_item] [largura altura]

Gera `pdv_<estado>_<WxH>_preview.png` na raiz do desktop (gitignored).
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
from printgest.ui.modulos.venda_balcao import PaginaVendaBalcao  # noqa: E402
from printgest.ui.theme import aplicar_theme  # noqa: E402

ESTADO = (sys.argv[1] if len(sys.argv) > 1 else "vazio").strip().lower()
LARGURA = int(sys.argv[2]) if len(sys.argv) > 2 else 1920
ALTURA = int(sys.argv[3]) if len(sys.argv) > 3 else 1080

_VENDAS: list = []
_CLIENTES = [{"id": 1, "nome_razao": "Ana"}]
_FUNCIONARIOS = [{"id": 10, "nome": "Maria", "e_vendedor": True}]
_PRODUTOS = [
    {"id": 5, "codigo": "B015", "nome": "Adesivo Frosted 3mm",
     "preco_venda": "100.00", "codigo_barras": "7891000100103"},
    {"id": 6, "codigo": "B016", "nome": "Lona 440g 1,20m",
     "preco_venda": "45.90", "codigo_barras": None},
    {"id": 7, "codigo": "B017", "nome": "Banner 300g 1,00m",
     "preco_venda": "38.50", "codigo_barras": None},
]


def handler(request: httpx.Request) -> httpx.Response:
    p = request.url.path
    meta = lambda n: {"total": n, "limit": 50, "offset": 0}  # noqa: E731
    if p == "/v1/vendas":
        return httpx.Response(200, json={"data": _VENDAS, "meta": meta(0)})
    if p == "/v1/clientes":
        return httpx.Response(200, json={"data": _CLIENTES, "meta": meta(1)})
    if p == "/v1/funcionarios":
        return httpx.Response(200, json={"data": _FUNCIONARIOS, "meta": meta(1)})
    if p == "/v1/produtos":
        return httpx.Response(200, json={"data": _PRODUTOS, "meta": meta(3)})
    return httpx.Response(404, json={"detail": "x"})


def main() -> None:
    app = QApplication(sys.argv[:1])
    aplicar_theme(app)
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler))
    api.autenticar({"token": "t", "usuario": {"id": 1, "nome": "Maria", "login": "maria"}})
    tela = PaginaVendaBalcao(api, nivel="admin")
    tela.resize(LARGURA, ALTURA)
    tela.show()

    def capturar() -> None:
        if ESTADO == "com_item":
            # Espera o catálogo carregar (thread): sem isso a busca não
            # resolve e o QMessageBox modal trava o exec offscreen.
            editor = tela._itens_editor
            if "7891000100103" not in editor._por_codigo:
                QTimer.singleShot(100, capturar)
                return
            editor._entrada.setText("7891000100103")
            editor._adicionar_pela_busca()
            editor._adicionar_do_texto("B016 • Lona 440g 1,20m")
            tela._recebido.definir("50")  # mostra o "Falta R$ 95,80"
        QTimer.singleShot(200, lambda: salvar())

    def salvar() -> None:
        destino = (
            Path(__file__).resolve().parents[1]
            / f"pdv_{ESTADO}_{LARGURA}x{ALTURA}_preview.png"
        )
        tela.grab().save(str(destino))
        print(f"salvo: {destino}")
        app.quit()

    QTimer.singleShot(400, capturar)
    app.exec()


if __name__ == "__main__":
    main()
