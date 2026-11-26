"""M1 — banner de modo leitura único e reativo a mudança em runtime."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from printgest.ui.tela_principal import TelaPrincipal

_USUARIO = {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"}


def _banners_visiveis(tela: TelaPrincipal) -> list[QWidget]:
    return [
        b for b in tela.findChildren(QWidget, "bannerAmber") if b.isVisibleTo(tela)
    ]


def test_banner_unico_quando_entra_em_modo_leitura(app):
    tela = TelaPrincipal(api=object(), usuario=_USUARIO, modo_leitura=True)
    assert tela._banner_leitura.isVisibleTo(tela)
    assert len(_banners_visiveis(tela)) == 1
    # O aviso antigo dentro da página Início foi removido (os formulários de
    # cadastro têm o próprio aviso, que é legítimo).
    assert tela._pagina_inicio.findChildren(QWidget, "bannerLeitura") == []


def test_banner_aparece_quando_licenca_muda_em_runtime(app):
    tela = TelaPrincipal(api=object(), usuario=_USUARIO, modo_leitura=False)
    assert not tela._banner_leitura.isVisibleTo(tela)

    tela._licenca({"estado": "leitura", "modo_leitura": True})

    assert tela._banner_leitura.isVisibleTo(tela)
    assert tela._modo_leitura is True
    assert len(_banners_visiveis(tela)) == 1


def test_banner_continua_oculto_com_licenca_ativa(app):
    tela = TelaPrincipal(api=object(), usuario=_USUARIO, modo_leitura=False)
    tela._licenca({"estado": "ativa", "status": "ativa"})
    assert not tela._banner_leitura.isVisibleTo(tela)
    assert tela._modo_leitura is False


def test_revogacao_tambem_entra_em_modo_leitura(app):
    tela = TelaPrincipal(api=object(), usuario=_USUARIO, modo_leitura=False)
    tela._licenca({"estado": "revogada"})
    assert tela._banner_leitura.isVisibleTo(tela)
    assert tela._modo_leitura is True


def test_motivo_da_falha_de_licenca_vai_para_tooltip(app):
    tela = TelaPrincipal(api=object(), usuario=_USUARIO)
    tela._sem_licenca("Bearer supersecreto123 na consulta da licença")
    tooltip = tela._lbl_licenca.toolTip()
    assert "Bearer" in tooltip
    assert "supersecreto123" not in tooltip


def test_falha_do_daemon_aparece_mesmo_em_modo_leitura(app):
    tela = TelaPrincipal(api=object(), usuario=_USUARIO, modo_leitura=True)
    inicio = tela._pagina_inicio
    inicio._status_conexao(False)
    assert inicio._alerta_conexao.isVisibleTo(inicio)

    inicio._status_conexao(True)
    assert not inicio._alerta_conexao.isVisibleTo(inicio)
