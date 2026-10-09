"""Execução de chamadas de rede fora da thread da UI (PySide6).

Um `QThread` dedicado roda as chamadas (bloqueantes) e o resultado volta para a
thread principal através de sinais QObject→QObject — entrega determinística,
sem depender do mecanismo de conexão direta de callables Python entre threads.
"""

from __future__ import annotations

import atexit
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot


class _Worker(QObject):
    _resultado = Signal(int, object)

    @Slot(int, object)
    def _executar(self, pedido_id: int, chamada) -> None:
        try:
            self._resultado.emit(pedido_id, (True, chamada()))
        except Exception as exc:  # noqa: BLE001 — falha externa não derruba a app
            self._resultado.emit(pedido_id, (False, str(exc)))


class _Controle(QObject):
    """Despacha `chamada` para o worker e entrega o resultado no main thread."""

    _pedido = Signal(int, object)

    def __init__(self) -> None:
        super().__init__()
        self._cotas: dict[int, tuple] = {}
        self._proximo_id = 0
        self._thread = QThread()
        self._thread.start()
        self._worker = _Worker()
        self._worker.moveToThread(self._thread)
        self._worker._resultado.connect(self._entregar)
        self._pedido.connect(self._worker._executar)

    def rodar(
        self,
        chamada: Callable[[], object],
        on_ok: Callable[[object], None],
        on_erro: Callable[[str], None],
    ) -> int:
        pedido_id = self._proximo_id
        self._proximo_id += 1
        self._cotas[pedido_id] = (on_ok, on_erro)
        self._pedido.emit(pedido_id, chamada)
        return pedido_id

    @Slot(int, object)
    def _entregar(self, pedido_id: int, resultado: tuple) -> None:
        on_ok, on_erro = self._cotas.pop(pedido_id)
        ok, valor = resultado
        (on_ok if ok else on_erro)(valor)

    def finalizar(self) -> None:
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)


_controle: _Controle | None = None


def _encerrar() -> None:
    global _controle
    if _controle is not None:
        _controle.finalizar()


atexit.register(_encerrar)


def _obter_controle() -> _Controle:
    """Cria a thread de trabalho sob demanda — só depois de existir um QApplication.

    Criar um `QThread` no import (antes do `QApplication(sys.argv)` do `main`) faz
    o Qt emitir "QEventLoop: Cannot be used without QApplication" e derruba a
    entrega dos resultados na thread da UI.
    """
    global _controle
    if _controle is None:
        _controle = _Controle()
    return _controle


def rodar(
    fn: Callable[[], object],
    on_ok: Callable[[object], None],
    on_erro: Callable[[str], None],
) -> int:
    """Executa `fn` em background; `on_ok(resultado)` ou `on_erro(msg)` no main."""
    return _obter_controle().rodar(fn, on_ok, on_erro)