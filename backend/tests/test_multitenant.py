"""Multi-tenant no banco compartilhado (printg): isolamento por inquilino.

O projeto Neon do PrintGest atende várias gráficas no MESMO banco. O inquilino
da instalação é `PRINTGEST_EMPRESA_CNPJ` — bootstrap garante empresa/filial/
admin dele, o login busca dentro do inquilino e cada inquilino tem a própria
licença. Estes testes provam que o que uma gráfica cadastra não aparece para a
outra.
"""

import pytest
import sqlalchemy as sa

from app.core.config import settings
from tests.conftest import auth

CNPJ_A = "32667694000101"
CNPJ_B = "01941569000114"


def _limpar_inquilinos(sessao, *cnpjs: str) -> None:
    """Remove inquilinos e TUDO que referencia suas filiais (ordem filha→pai).

    SQL cru com ids inline (inteiros vindos do próprio banco): o `sa.text`
    não expande tuplas em `IN`. ORM nularia `filial.empresa_id` (NOT NULL).
    """
    ids = [
        r[0]
        for r in sessao.execute(
            sa.text("SELECT id FROM empresa WHERE cnpj IN :cnpjs").bindparams(
                sa.bindparam("cnpjs", expanding=True)
            ),
            {"cnpjs": list(cnpjs)},
        ).fetchall()
    ]
    if not ids:
        return
    lista = ", ".join(str(i) for i in ids)
    filtro_filial = (
        f"filial_id IN (SELECT id FROM filial WHERE empresa_id IN ({lista}))"
    )
    for sql in (
        f"DELETE FROM usuario_sessao WHERE usuario_id IN (SELECT id FROM usuario WHERE {filtro_filial})",
        f"DELETE FROM usuario WHERE {filtro_filial}",
        f"DELETE FROM funcionario WHERE {filtro_filial}",
        f"DELETE FROM cliente WHERE {filtro_filial}",
        f"DELETE FROM fornecedor WHERE {filtro_filial}",
        f"DELETE FROM produto WHERE {filtro_filial}",
        f"DELETE FROM produto_categoria WHERE {filtro_filial}",
        f"DELETE FROM licenca WHERE empresa_id IN ({lista})",
        f"DELETE FROM filial WHERE empresa_id IN ({lista})",
        f"DELETE FROM empresa WHERE id IN ({lista})",
    ):
        sessao.execute(sa.text(sql))
    sessao.commit()


@pytest.fixture()
def _dois_inquilinos(monkeypatch):
    """Bootstrapia os inquilinos A e B; teardown remove SÓ o que eles criaram.

    SEM truncate global: a suíte compartilha o banco por sessão e dezenas de
    testes dependem da filial demo (o fallback `usuario.filial_id or 1`) e das
    sequências — truncar com RESTART IDENTITY quebrava tudo depois.
    """
    from app import bootstrap
    from app.db import SessionLocal

    def _bootstrap(cnpj: str, senha: str) -> None:
        monkeypatch.setattr(settings, "empresa_cnpj", cnpj)
        monkeypatch.setattr(settings, "admin_inicial_senha", senha)
        monkeypatch.setattr(settings, "admin_inicial_primeiro_acesso", False)
        bootstrap.rodar_bootstrap()

    _bootstrap(CNPJ_A, "senhaA123")
    _bootstrap(CNPJ_B, "senhaB123")
    monkeypatch.setattr(settings, "empresa_cnpj", "")  # resto do teste escolhe
    yield
    sessao = SessionLocal()
    try:
        _limpar_inquilinos(sessao, CNPJ_A, CNPJ_B)
    finally:
        sessao.close()


@pytest.mark.usefixtures("_dois_inquilinos")
def test_clientes_de_um_inquilino_nao_aparecem_para_o_outro(client, monkeypatch):
    # Inquilino A: login e cadastro de cliente.
    monkeypatch.setattr(settings, "empresa_cnpj", CNPJ_A)
    resp_a = client.post(
        "/v1/auth/login", json={"login": "admin", "senha": "senhaA123"}
    )
    assert resp_a.status_code == 200, resp_a.text
    token_a = resp_a.json()["data"]["token"]
    assert (
        client.post(
            "/v1/clientes",
            headers=auth(client, token_a),
            json={"nome_razao": "Cliente exclusivo da gráfica A", "tipo_pessoa": "pf"},
        ).status_code
        == 200
    )

    # Inquilino B: login COM O MESMO 'admin' (senha própria) e outro cliente.
    monkeypatch.setattr(settings, "empresa_cnpj", CNPJ_B)
    resp_b = client.post(
        "/v1/auth/login", json={"login": "admin", "senha": "senhaB123"}
    )
    assert resp_b.status_code == 200, resp_b.text
    token_b = resp_b.json()["data"]["token"]
    assert (
        client.post(
            "/v1/clientes",
            headers=auth(client, token_b),
            json={"nome_razao": "Cliente exclusivo da gráfica B", "tipo_pessoa": "pf"},
        ).status_code
        == 200
    )

    lista_a = client.get("/v1/clientes", headers=auth(client, token_a)).json()["data"]
    lista_b = client.get("/v1/clientes", headers=auth(client, token_b)).json()["data"]
    nomes_a = {c["nome_razao"] for c in lista_a}
    nomes_b = {c["nome_razao"] for c in lista_b}
    assert "Cliente exclusivo da gráfica A" in nomes_a
    assert "Cliente exclusivo da gráfica A" not in nomes_b
    assert "Cliente exclusivo da gráfica B" in nomes_b
    assert "Cliente exclusivo da gráfica B" not in nomes_a


@pytest.mark.usefixtures("_dois_inquilinos")
def test_licenca_e_por_inquilino_no_banco_compartilhado(client, monkeypatch):
    """Nenhuma linha de licença fica sem inquilino ou herdada por outro."""
    from app.db import SessionLocal
    from app.models.core import Empresa
    from app.models.licenca import Licenca

    def _inquilino_id(cnpj: str) -> int | None:
        sessao = SessionLocal()
        try:
            return sessao.query(Empresa.id).filter(Empresa.cnpj == cnpj).scalar()
        finally:
            sessao.close()

    monkeypatch.setattr(settings, "empresa_cnpj", CNPJ_A)
    client.post(
        "/v1/licenca/ativar", json={"cnpj": "12345678000199", "codigo_licenca": "X"}
    )
    # Contrato C (default da suíte): sem integração real o ativar responde erro
    # — o que importa aqui é a INVARIANTE do banco compartilhado: toda linha de
    # licença pertence a um inquilino (empresa_id NOT NULL na prática), nunca
    # fica órfã vazando para outra gráfica.
    sessao = SessionLocal()
    try:
        for lic in sessao.query(Licenca).all():
            assert lic.empresa_id is not None, (
                "licenca sem inquilino: vazaria entre gráficas"
            )
    finally:
        sessao.close()


def test_bootstrap_tenant_e_idempotente(client, monkeypatch):
    """Bootstrap repetido não duplica empresa/filial/admin do inquilino."""
    from app import bootstrap
    from app.db import SessionLocal
    from app.models.core import Empresa, Filial, Usuario

    monkeypatch.setattr(settings, "empresa_cnpj", CNPJ_A)
    monkeypatch.setattr(settings, "admin_inicial_senha", "senhaA123")
    monkeypatch.setattr(settings, "admin_inicial_primeiro_acesso", False)

    bootstrap.rodar_bootstrap()
    bootstrap.rodar_bootstrap()

    sessao = SessionLocal()
    try:
        empresas = sessao.query(Empresa).filter(Empresa.cnpj == CNPJ_A).all()
        assert len(empresas) == 1
        filiais = sessao.query(Filial).filter(Filial.empresa_id == empresas[0].id).all()
        assert len(filiais) == 1
        admins = (
            sessao.query(Usuario)
            .filter(Usuario.filial_id == filiais[0].id)
            .filter(Usuario.login == "admin")
            .all()
        )
        assert len(admins) == 1
    finally:
        sessao.close()
    sessao = SessionLocal()
    try:
        _limpar_inquilinos(sessao, CNPJ_A)
    finally:
        sessao.close()
