"""Sessão persistente (regra de produto): login se repete só ao reiniciar o
computador ou no Sair — nunca por tempo fechado nem por reabrir o programa."""

from __future__ import annotations

import json

import pytest

from printgest.core import sessao


_USUARIO = {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"}


@pytest.fixture()
def arquivo_sessao(tmp_path, monkeypatch):
    """Isola o arquivo de sessão por teste (nunca tocar no `~` real)."""
    alvo = tmp_path / ".printgest" / "session.json"
    monkeypatch.setattr(sessao, "SESSION_FILE", alvo)
    return alvo


def test_salvar_e_carregar_mesmo_boot(arquivo_sessao, monkeypatch):
    monkeypatch.setattr(sessao, "tempo_boot", lambda: 1000.0)
    sessao.salvar_sessao("tok-123", _USUARIO)

    dados = sessao.carregar_sessao()

    assert dados is not None
    assert dados["token"] == "tok-123"
    assert dados["usuario"] == _USUARIO


def test_sem_expiracao_por_tempo(arquivo_sessao, monkeypatch):
    """A cópia local NÃO expira: sem timeout de 8 h (validade é do servidor)."""
    monkeypatch.setattr(sessao, "tempo_boot", lambda: 1000.0)
    sessao.salvar_sessao("tok-123", _USUARIO)

    # Corrompe o timestamp antigo a favor do teste: grava "boot" igual mas com
    # chaves extras/velhas — o que importa é que NÃO há cheque de idade.
    dados = json.loads(arquivo_sessao.read_text(encoding="utf-8"))
    dados["antiguidade_horas"] = 999
    arquivo_sessao.write_text(json.dumps(dados), encoding="utf-8")

    assert sessao.carregar_sessao() is not None


def test_reinicio_do_computador_pede_login(arquivo_sessao, monkeypatch):
    """Boot time mudou → o computador reiniciou → sessão não vale mais."""
    monkeypatch.setattr(sessao, "tempo_boot", lambda: 1000.0)
    sessao.salvar_sessao("tok-123", _USUARIO)

    # Novo boot (semana depois, uptime reiniciado).
    monkeypatch.setattr(sessao, "tempo_boot", lambda: 700000.0)

    assert sessao.carregar_sessao() is None
    assert not arquivo_sessao.exists()


def test_hash_divergente_limpa_sessao(arquivo_sessao, monkeypatch):
    monkeypatch.setattr(sessao, "tempo_boot", lambda: 1000.0)
    sessao.salvar_sessao("tok-123", _USUARIO)

    dados = json.loads(arquivo_sessao.read_text(encoding="utf-8"))
    dados["usuario"]["nome"] = "Editado"
    arquivo_sessao.write_text(json.dumps(dados), encoding="utf-8")

    assert sessao.carregar_sessao() is None


def test_boot_indisponivel_e_tolerante(arquivo_sessao, monkeypatch):
    """Sem como detectar o boot (`None`), a sessão é mantida (tolerante)."""
    monkeypatch.setattr(sessao, "tempo_boot", lambda: None)
    sessao.salvar_sessao("tok-123", _USUARIO)

    monkeypatch.setattr(sessao, "tempo_boot", lambda: None)
    assert sessao.carregar_sessao() is not None


def test_limpar_sessao(arquivo_sessao, monkeypatch):
    monkeypatch.setattr(sessao, "tempo_boot", lambda: 1000.0)
    sessao.salvar_sessao("tok-123", _USUARIO)
    sessao.limpar_sessao()

    assert sessao.carregar_sessao() is None
