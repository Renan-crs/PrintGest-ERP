"""Consolidação de leitura (PRD v3.3 §5.3/§5.6) — psycopg mockado."""

import uuid

import pytest
from app.core import cofre_sync
from app.core.config import settings
from app.db import SessionLocal
from app.models.cadastros import Cliente, Fornecedor, Produto
from app.models.consolidacao import SyncEstado
from app.models.plataforma import EventoSync
from app.services import consolidacao_service, filial_service
from tests.conftest import auth

FILIAL = 1
URL = "postgresql://u:p@ep.neon.tech/consolidado?sslmode=require"


@pytest.fixture(autouse=True)
def _limpar(client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings, "cofre_integracoes_arquivo", str(tmp_path / "integracoes.dat")
    )
    cofre_sync.limpar()
    db = SessionLocal()
    try:
        db.query(SyncEstado).delete()
        db.query(EventoSync).delete()
        db.commit()
    finally:
        db.close()
    yield
    cofre_sync.limpar()


class _Cursor:
    def __init__(self, consultas, respostas):
        self.consultas = consultas
        self.respostas = respostas
        self.executados = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.executados.append((sql, params))
        self.consultas.append((sql, params))

    def fetchall(self):
        sql = self.executados[-1][0]
        for chave, valor in self.respostas.items():
            if chave in sql:
                return valor
        return []

    def fetchone(self):
        valor = self.respostas.get("fetchone")
        return (valor,) if valor is not None else (None,)


class _Conexao:
    def __init__(self, respostas=None):
        self.respostas = respostas or {}
        self.consultas = []
        self.commitado = False

    def cursor(self):
        return _Cursor(self.consultas, self.respostas)

    def commit(self):
        self.commitado = True

    def rollback(self):
        pass

    def close(self):
        pass


def test_publicar_mestre_gera_evento_outbox(client, admin_token):
    db = SessionLocal()
    r = consolidacao_service.publicar_mestre(
        db,
        filial_id=FILIAL,
        entidade="mestre:produto",
        chave="B015",
        payload={"nome": "Adesivo", "preco_venda": "12.00"},
    )
    assert r["entidade"] == "mestre:produto" and r["seq"] == 1

    pendentes, total = filial_service.eventos(
        db, filial_id=FILIAL, pendentes=True
    )
    assert total == 1
    ev = pendentes[0]
    assert ev.entidade == "mestre:produto"
    assert ev.payload["chave"] == "B015"

    with pytest.raises(Exception):
        consolidacao_service.publicar_mestre(
            db, filial_id=FILIAL, entidade=" desconhecida", chave="x", payload={}
        )


def test_descer_mestres_aplica_e_guarda_cursor(client, admin_token):
    cofre_sync.definir_url(FILIAL, URL)
    db = SessionLocal()
    respostas = {
        "SELECT versao, payload FROM consolidado.mestre": [
            (7, {"chave": "B015", "nome": "Adesivo Frosted", "preco_venda": "25.50"}),
            (5, {"chave": "B016", "nome": "Banner", "preco_venda": "84.00"}),
        ]
    }
    conn = _Conexao(respostas)
    resultado = consolidacao_service.descer_mestres(
        db, filial_id=FILIAL, conexao=conn
    )
    assert resultado["ok"] is True, resultado["erros"]
    assert resultado["aplicados"]["mestre:produto"] == 7

    produto = (
        db.query(Produto)
        .filter(Produto.filial_id == FILIAL, Produto.codigo == "B015")
        .first()
    )
    assert produto is not None and produto.nome == "Adesivo Frosted"
    assert str(produto.preco_venda) == "25.50"

    cursor = (
        db.query(SyncEstado)
        .filter(SyncEstado.filial_id == FILIAL, SyncEstado.entidade == "mestre:produto")
        .first()
    )
    assert cursor.ultima_versao == 7

    # Segunda descida com versão maior que o cursor não reaplica nada.
    conn2 = _Conexao(respostas)
    resultado2 = consolidacao_service.descer_mestres(
        db, filial_id=FILIAL, conexao=conn2
    )
    assert resultado2["aplicados"].get("mestre:produto", 0) == 0


def test_conflitos_e_resolucao(client, admin_token):
    cofre_sync.definir_url(FILIAL, URL)
    db = SessionLocal()
    respostas = {
        "GROUP BY 1 HAVING": [
            ("32667694000101", [1, 2], 2),
        ]
    }
    conn = _Conexao(respostas)
    dados = consolidacao_service.conflitos(
        db, filial_id=FILIAL, conexao=conn
    )
    assert dados["total"] == 1
    assert dados["itens"][0]["filiais"] == [1, 2]

    conn2 = _Conexao()
    res = consolidacao_service.resolver_conflito(
        db,
        filial_id=FILIAL,
        documento="32667694000101",
        filial_escolhida=1,
        uuid_escolhido=str(uuid.uuid4()),
        usuario_id=1,
        conexao=conn2,
    )
    assert res["ok"] is True and conn2.commitado
    # O mock registra execute() no cursor; verificamos o SQL gravado.
    sql = conn2.consultas[0][0] if conn2.consultas else ""
    assert "cliente_conflito_resolucao" in sql
    assert "ON CONFLICT" in sql


def test_relatorio_consolidado(client, admin_token):
    cofre_sync.definir_url(FILIAL, URL)
    db = SessionLocal()
    respostas = {
        "GROUP BY filial_id": [
            (1, 10, "1000.00"),
            (2, 4, "250.50"),
        ],
        "fetchone": "2026-11-17T10:00:00Z",
    }
    conn = _Conexao(respostas)
    dados = consolidacao_service.relatorio_vendas(
        db, filial_id=FILIAL, conexao=conn
    )
    assert dados["total_geral"] == "1250.50"
    assert len(dados["por_filial"]) == 2
    assert "defasagem" in dados["observacao"].lower()
    assert any("vw_vendas" in sql for sql, _ in conn.consultas)


def test_cliente_criado_gera_evento_para_conflitos(client, admin_token):
    h = auth(client, admin_token)
    resp = client.post(
        "/v1/clientes",
        headers=h,
        json={
            "nome_razao": f"Cliente {uuid.uuid4().hex[:6]}",
            "cpf_cnpj": uuid.uuid4().hex[:14],
            "tipo_pessoa": "pj",
        },
    )
    assert resp.status_code == 200, resp.text
    db = SessionLocal()
    try:
        eventos = (
            db.query(EventoSync)
            .filter(EventoSync.entidade == "cliente")
            .all()
        )
        assert eventos
        assert "cpf_cnpj" in (eventos[-1].payload or {})
    finally:
        db.close()
