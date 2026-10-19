"""Cofre do SO para a chave de ativação (doc de integração RedGest §9.4).

A doc exige a chave em cofre do sistema operacional (Windows: DPAPI). Estes
testes cobrem o contrato do módulo, incluindo a leitura de linhas gravadas em
texto puro antes do cofre existir e o caso de blob ilegível (banco restaurado
em outra máquina), que precisa virar "reative a licença" em vez de lixo na
requisição.
"""

from app.core import cofre
from app.core.config import settings

CHAVE = "A1B2-C3D4-E5F6-7890"


def test_proteger_e_revelar_roundtrip(monkeypatch):
    monkeypatch.setattr(settings, "cofre", "dpapi")
    guardado = cofre.proteger(CHAVE)
    if cofre.disponivel():
        assert guardado.startswith(cofre.PREFIXO)
        assert CHAVE not in guardado
        assert cofre.revelar(guardado) == CHAVE
    else:
        # Sem DPAPI nesta máquina o módulo degrada para texto puro (avisa no log).
        assert guardado == CHAVE


def test_disponivel_depende_da_configuracao(monkeypatch):
    monkeypatch.setattr(settings, "cofre", "nenhum")
    assert cofre.disponivel() is False
    assert cofre.proteger(CHAVE) == CHAVE  # cofre desligado: grava em texto puro


def test_revelar_aceita_texto_puro_de_bases_antigas(monkeypatch):
    monkeypatch.setattr(settings, "cofre", "dpapi")
    assert cofre.revelar(CHAVE) == CHAVE


def test_revelar_blob_corrompido_devolve_vazio(monkeypatch):
    monkeypatch.setattr(settings, "cofre", "dpapi")
    assert cofre.revelar(cofre.PREFIXO + "isto-nao-e-base64!!") == ""
    assert cofre.revelar(cofre.PREFIXO + "YWJjZGVm") == ""


def test_valores_vazios():
    assert cofre.proteger("") == ""
    assert cofre.revelar("") == ""
    assert cofre.revelar(None) == ""
