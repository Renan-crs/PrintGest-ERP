"""Mede o cadastro de produtos/variações offscreen em 1024×768 e 1366×768.

Uso:
    desktop/.venv/Scripts/python.exe scripts/medir_cadastro_produtos.py

Gera capturas em `analysis-assets/cadastro_produtos_<largura>.png` e imprime
a geometria do formulário/grade para auditoria de altura e espaçamento.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "desktop"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QScrollArea

import printgest.core.tarefas as tarefas


def _rodar_sync(fn, on_ok, on_erro):
    try:
        on_ok(fn())
    except Exception:
        pass


tarefas.rodar = _rodar_sync

from printgest.core.api import Api
from printgest.ui.modulos.produtos import PaginaProdutos
from printgest.ui.theme import aplicar_theme

_PRODUTOS = [{
    "id": 4, "codigo": "cv01", "nome": "Cartão de visita", "tipo": "produto",
    "categoria_id": None, "preco_venda": "120.00", "preco_custo": "60.00",
    "controla_estoque": True, "estoque_minimo": "0", "unidade": "un",
}]
_CATEGORIAS = [{"id": 1, "nome": "Papéis & Gramaturas"}]


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/produtos":
        return httpx.Response(200, json={
            "data": _PRODUTOS,
            "meta": {"total": 1, "limit": 50, "offset": 0},
        })
    if request.url.path == "/v1/categorias":
        return httpx.Response(200, json={
            "data": _CATEGORIAS,
            "meta": {"total": 1, "limit": 1000, "offset": 0},
        })
    return httpx.Response(404, json={"detail": "off"})


def _api() -> Api:
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nivel_acesso": "admin"}})
    return api


def medir(app: QApplication, largura: int, altura: int) -> None:
    pagina = PaginaProdutos(_api())
    pagina.show()
    app.processEvents()
    pagina.resize(largura, altura)
    app.processEvents()

    scroll = pagina._painel_form
    conteudo = scroll.widget()
    barra = scroll.verticalScrollBar()
    preco = pagina._preco_venda.widget
    foto = pagina._foto2.widget
    preco_y = preco.mapTo(scroll.viewport(), QPoint(0, 0)).y()
    foto_y = foto.mapTo(scroll.viewport(), QPoint(0, 0)).y()

    print(
        f"{largura}x{altura}: form_viewport={scroll.viewport().height()} "
        f"content_hint={conteudo.sizeHint().height()} scroll_max={barra.maximum()} "
        f"preco_y={preco_y} foto2_y={foto_y} "
        f"variacoes_enabled={pagina._btn_variacoes.isEnabled()} "
        f"tabela_w={pagina._tabela.width()} ref_w={pagina._tabela.columnWidth(0)}"
    )

    destino = RAIZ / "analysis-assets" / f"cadastro_produtos_{largura}.png"
    destino.parent.mkdir(exist_ok=True)
    pagina.grab().save(str(destino))
    print(f"  captura: {destino}")

    pagina.close()
    pagina.deleteLater()
    app.processEvents()


def main() -> None:
    app = QApplication.instance() or QApplication([])
    aplicar_theme(app)
    medir(app, 1366, 768)
    medir(app, 1024, 768)


if __name__ == "__main__":
    main()
