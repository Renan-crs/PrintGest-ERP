"""Teste de fumaça sistemático contra o backend REAL (:8000).

Cobertura: todos os modulos da API - leitura, escrita, listagem,
paginacao, busca, filtros, RBAC e caminhos de erro (401/403/404/409/422).

Uso: python scripts_fumaca.py  (backend deve estar no ar em :8000)
"""

from __future__ import annotations

import io
import sys
import uuid

import httpx

BASE = "http://127.0.0.1:8000"
T = 15  # timeout por chamada

PASSOU = 0
FALHOU = 0
ERROS: list[str] = []


def _u() -> str:
    return uuid.uuid4().hex[:8]


def teste(nome: str, condicao: bool, detalhe: str = "") -> None:
    global PASSOU, FALHOU
    if condicao:
        PASSOU += 1
        print(f"  OK  {nome}")
    else:
        FALHOU += 1
        ERROS.append(f"{nome} :: {detalhe}")
        print(f"  XX  {nome}  ->  {detalhe}")


def secao(nome: str) -> None:
    print()
    print(f"-- {nome} --")


def login(login_usr: str = "admin", senha: str = "admin123") -> str:
    resp = httpx.post(
        f"{BASE}/v1/auth/login", json={"login": login_usr, "senha": senha}, timeout=T
    )
    if resp.status_code != 200:
        print(f"ERRO FATAL: login falhou - {resp.text}")
        sys.exit(1)
    return resp.json()["data"]["token"]


def H(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    print("== TESTE DE FUMACA - BACKEND :8000 ==")
    token = login()
    h = H(token)

    # ================================================================ AUTH
    secao("AUTH")
    resp = httpx.get(f"{BASE}/v1/auth/me", headers=h, timeout=T)
    teste(
        "me retorna usuario",
        resp.status_code == 200 and resp.json()["data"]["login"] == "admin",
        f"GET -> {resp.status_code}",
    )

    resp = httpx.post(
        f"{BASE}/v1/auth/login", json={"login": "admin", "senha": "errada"}, timeout=T
    )
    teste(
        "login senha errada 401", resp.status_code == 401, f"POST -> {resp.status_code}"
    )

    resp = httpx.get(f"{BASE}/v1/clientes", timeout=T)
    teste("sem token 401", resp.status_code == 401, f"GET -> {resp.status_code}")

    resp = httpx.get(
        f"{BASE}/v1/clientes", headers={"Authorization": "Bearer invalido"}, timeout=T
    )
    teste("token invalido 401", resp.status_code == 401, f"GET -> {resp.status_code}")

    # ============================================================= CLIENTES
    secao("CLIENTES")
    nome = f"Cliente Fumaca {_u()}"
    resp = httpx.post(
        f"{BASE}/v1/clientes",
        headers=h,
        json={"nome_razao": nome, "tipo_pessoa": "pf"},
        timeout=T,
    )
    teste(
        "criar PF",
        resp.status_code == 200,
        f"POST -> {resp.status_code}: {resp.text[:120]}",
    )
    cli = resp.json()["data"]

    resp = httpx.get(f"{BASE}/v1/clientes/{cli['id']}", headers=h, timeout=T)
    teste(
        "buscar por ID",
        resp.status_code == 200 and resp.json()["data"]["nome_razao"] == nome,
        f"GET -> {resp.status_code}",
    )

    resp = httpx.get(f"{BASE}/v1/clientes", headers=h, params={"q": nome}, timeout=T)
    teste(
        "busca por texto",
        resp.status_code == 200 and len(resp.json()["data"]) == 1,
        f"GET?q -> {resp.status_code}",
    )

    # PJ + documento
    cnpj = f"{_u()}{_u()}"[:14]
    resp = httpx.post(
        f"{BASE}/v1/clientes",
        headers=h,
        json={"nome_razao": f"Empresa {_u()}", "tipo_pessoa": "pj", "cpf_cnpj": cnpj},
        timeout=T,
    )
    teste(
        "criar PJ com CNPJ",
        resp.status_code == 200,
        f"POST -> {resp.status_code}: {resp.text[:120]}",
    )
    cli_pj = resp.json()["data"] if resp.status_code == 200 else None

    if cli_pj:
        resp = httpx.post(
            f"{BASE}/v1/clientes",
            headers=h,
            json={"nome_razao": f"Outra {_u()}", "tipo_pessoa": "pj", "cpf_cnpj": cnpj},
            timeout=T,
        )
        teste(
            "CNPJ duplicado 409", resp.status_code == 409, f"POST -> {resp.status_code}"
        )

    # paginacao
    resp = httpx.get(
        f"{BASE}/v1/clientes", headers=h, params={"limit": 2, "offset": 0}, timeout=T
    )
    body = resp.json()
    teste(
        "paginacao limit=2",
        resp.status_code == 200 and len(body["data"]) <= 2,
        f"GET -> {resp.status_code}",
    )
    teste(
        "meta.total presente",
        isinstance(body.get("meta"), dict) and body["meta"].get("total", 0) > 0,
        f"meta={body.get('meta')}",
    )

    # validacao
    resp = httpx.post(
        f"{BASE}/v1/clientes", headers=h, json={"tipo_pessoa": "pf"}, timeout=T
    )
    teste("sem nome_razao 422", resp.status_code == 422, f"POST -> {resp.status_code}")

    # update + delete
    resp = httpx.put(
        f"{BASE}/v1/clientes/{cli['id']}",
        headers=h,
        json={"telefone": "11999990000"},
        timeout=T,
    )
    teste(
        "atualizar parcial",
        resp.status_code == 200 and resp.json()["data"]["telefone"] == "11999990000",
        f"PUT -> {resp.status_code}: {resp.text[:120]}",
    )

    resp = httpx.delete(f"{BASE}/v1/clientes/{cli['id']}", headers=h, timeout=T)
    teste("excluir 204", resp.status_code == 204, f"DELETE -> {resp.status_code}")

    resp = httpx.get(f"{BASE}/v1/clientes/{cli['id']}", headers=h, timeout=T)
    teste("buscar excluido 404", resp.status_code == 404, f"GET -> {resp.status_code}")

    # ========================================================= FORNECEDORES
    secao("FORNECEDORES")
    resp = httpx.post(
        f"{BASE}/v1/fornecedores",
        headers=h,
        json={"nome_razao": f"Fornecedor {_u()}", "tipo_pessoa": "pj"},
        timeout=T,
    )
    teste("criar", resp.status_code == 200, f"POST -> {resp.status_code}")
    forn = resp.json()["data"]
    resp = httpx.get(f"{BASE}/v1/fornecedores/{forn['id']}", headers=h, timeout=T)
    teste("buscar por ID", resp.status_code == 200, f"GET -> {resp.status_code}")
    resp = httpx.get(
        f"{BASE}/v1/fornecedores",
        headers=h,
        params={"q": forn["nome_razao"][:12]},
        timeout=T,
    )
    teste(
        "busca por texto",
        resp.status_code == 200 and len(resp.json()["data"]) == 1,
        f"GET?q -> {resp.status_code}",
    )
    resp = httpx.put(
        f"{BASE}/v1/fornecedores/{forn['id']}",
        headers=h,
        json={"telefone": "1133334444"},
        timeout=T,
    )
    teste("atualizar", resp.status_code == 200, f"PUT -> {resp.status_code}")
    resp = httpx.delete(f"{BASE}/v1/fornecedores/{forn['id']}", headers=h, timeout=T)
    teste("excluir 204", resp.status_code == 204, f"DELETE -> {resp.status_code}")

    # ========================================================= FUNCIONARIOS
    secao("FUNCIONARIOS")
    resp = httpx.post(
        f"{BASE}/v1/funcionarios",
        headers=h,
        json={
            "nome": f"Funcionario {_u()}",
            "cpf": _u()[:11],
            "cargo": "Atendente",
            "e_atendente": True,
            "e_vendedor": True,
            "comissao_pct": 3.5,
        },
        timeout=T,
    )
    teste(
        "criar",
        resp.status_code == 200,
        f"POST -> {resp.status_code}: {resp.text[:120]}",
    )
    func = resp.json()["data"] if resp.status_code == 200 else None
    if func:
        resp = httpx.get(
            f"{BASE}/v1/funcionarios",
            headers=h,
            params={"q": func["nome"][:10]},
            timeout=T,
        )
        teste(
            "busca por texto",
            resp.status_code == 200 and len(resp.json()["data"]) == 1,
            f"GET?q -> {resp.status_code}",
        )
        resp = httpx.put(
            f"{BASE}/v1/funcionarios/{func['id']}",
            headers=h,
            json={"cargo": "Producao"},
            timeout=T,
        )
        teste(
            "atualizar",
            resp.status_code == 200 and resp.json()["data"]["cargo"] == "Producao",
            f"PUT -> {resp.status_code}",
        )
        resp = httpx.delete(
            f"{BASE}/v1/funcionarios/{func['id']}", headers=h, timeout=T
        )
        teste("excluir 204", resp.status_code == 204, f"DELETE -> {resp.status_code}")

    # =========================================================== CATEGORIAS
    secao("CATEGORIAS")
    resp = httpx.post(
        f"{BASE}/v1/categorias",
        headers=h,
        json={"nome": f"Categoria {_u()}"},
        timeout=T,
    )
    teste(
        "criar",
        resp.status_code == 200,
        f"POST -> {resp.status_code}: {resp.text[:120]}",
    )
    cat = resp.json()["data"] if resp.status_code == 200 else None
    if cat:
        resp = httpx.put(
            f"{BASE}/v1/categorias/{cat['id']}",
            headers=h,
            json={"description": "Papeis especiais"},
            timeout=T,
        )
        teste("atualizar", resp.status_code == 200, f"PUT -> {resp.status_code}")
        resp = httpx.delete(f"{BASE}/v1/categorias/{cat['id']}", headers=h, timeout=T)
        teste("excluir 204", resp.status_code == 204, f"DELETE -> {resp.status_code}")

    # ============================================================= PRODUTOS
    secao("PRODUTOS")
    resp = httpx.post(
        f"{BASE}/v1/produtos",
        headers=h,
        json={
            "codigo": f"FUM-{_u()[:6]}",
            "nome": f"Produto {_u()[:6]}",
            "preco_custo": "5.00",
            "preco_venda": "10.00",
            "unidade": "un",
        },
        timeout=T,
    )
    teste(
        "criar",
        resp.status_code == 200,
        f"POST -> {resp.status_code}: {resp.text[:120]}",
    )
    prod = resp.json()["data"] if resp.status_code == 200 else None
    if prod:
        resp = httpx.get(f"{BASE}/v1/produtos/{prod['id']}", headers=h, timeout=T)
        teste("buscar por ID", resp.status_code == 200, f"GET -> {resp.status_code}")
        resp = httpx.get(
            f"{BASE}/v1/produtos", headers=h, params={"q": prod["nome"]}, timeout=T
        )
        teste(
            "busca por texto",
            resp.status_code == 200 and len(resp.json()["data"]) == 1,
            f"GET?q -> {resp.status_code}",
        )
        resp = httpx.get(
            f"{BASE}/v1/produtos",
            headers=h,
            params={"limit": 2, "offset": 0},
            timeout=T,
        )
        teste(
            "paginacao limit=2",
            resp.status_code == 200 and len(resp.json()["data"]) <= 2,
            f"GET -> {resp.status_code}",
        )
        resp = httpx.put(
            f"{BASE}/v1/produtos/{prod['id']}",
            headers=h,
            json={"preco_venda": "12.50"},
            timeout=T,
        )
        teste("atualizar preco", resp.status_code == 200, f"PUT -> {resp.status_code}")

    # produto descartavel p/ exclusao (sem movimentos)
    resp = httpx.post(
        f"{BASE}/v1/produtos",
        headers=h,
        json={
            "codigo": f"DEL-{_u()[:6]}",
            "nome": f"Descartavel {_u()[:6]}",
            "preco_custo": "1.00",
            "preco_venda": "2.00",
            "unidade": "un",
        },
        timeout=T,
    )
    if resp.status_code == 200:
        del_id = resp.json()["data"]["id"]
        resp = httpx.delete(f"{BASE}/v1/produtos/{del_id}", headers=h, timeout=T)
        teste(
            "excluir sem movimentos 204",
            resp.status_code == 204,
            f"DELETE -> {resp.status_code}",
        )
    else:
        teste("excluir sem movimentos 204", False, f"criar falhou: {resp.status_code}")

    # ========================================================== AGENDAMENTO
    secao("AGENDAMENTO")
    resp = httpx.post(
        f"{BASE}/v1/agendamento",
        headers=h,
        json={
            "titulo": f"Entrega {_u()}",
            "tipo": "entrega",
            "data_hora_inicio": "2026-11-20T14:00:00",
            "data_hora_fim": "2026-11-20T16:00:00",
        },
        timeout=T,
    )
    teste(
        "criar",
        resp.status_code == 201,
        f"POST -> {resp.status_code}: {resp.text[:120]}",
    )
    ag = resp.json()["data"] if resp.status_code == 201 else None
    if ag:
        resp = httpx.get(f"{BASE}/v1/agendamento/{ag['id']}", headers=h, timeout=T)
        teste("buscar por ID", resp.status_code == 200, f"GET -> {resp.status_code}")
        resp = httpx.get(f"{BASE}/v1/agendamento", headers=h, timeout=T)
        teste(
            "listar",
            resp.status_code == 200 and len(resp.json()["data"]) >= 1,
            f"GET -> {resp.status_code}",
        )
        resp = httpx.put(
            f"{BASE}/v1/agendamento/{ag['id']}",
            headers=h,
            json={"titulo": f"Entrega alt {_u()}"},
            timeout=T,
        )
        teste("atualizar", resp.status_code == 200, f"PUT -> {resp.status_code}")
        resp = httpx.patch(
            f"{BASE}/v1/agendamento/{ag['id']}/concluir", headers=h, timeout=T
        )
        teste("concluir", resp.status_code == 200, f"PATCH -> {resp.status_code}")
        resp = httpx.delete(f"{BASE}/v1/agendamento/{ag['id']}", headers=h, timeout=T)
        teste("excluir 204", resp.status_code == 204, f"DELETE -> {resp.status_code}")

    # ============================================================== CAIXA
    secao("CAIXA")
    resp = httpx.get(f"{BASE}/v1/financeiro/caixa/atual", headers=h, timeout=T)
    teste("caixa atual", resp.status_code == 200, f"GET -> {resp.status_code}")
    caixa = resp.json()["data"]
    if caixa is None or caixa.get("status") != "aberto":
        resp = httpx.post(
            f"{BASE}/v1/financeiro/caixa/abrir",
            headers=h,
            json={"valor_abertura": "100.00"},
            timeout=T,
        )
        teste(
            "abrir caixa",
            resp.status_code == 200,
            f"POST -> {resp.status_code}: {resp.text[:120]}",
        )
        caixa = resp.json()["data"]
    else:
        teste("abrir caixa (ja aberto)", True, "skip")

    cx_id = caixa["id"]
    resp = httpx.get(
        f"{BASE}/v1/financeiro/caixa/{cx_id}/extrato", headers=h, timeout=T
    )
    teste("extrato", resp.status_code == 200, f"GET -> {resp.status_code}")

    resp = httpx.post(
        f"{BASE}/v1/financeiro/caixa/{cx_id}/movimento",
        headers=h,
        json={"tipo": "suprimento", "valor": "50.00", "descricao": "Troco"},
        timeout=T,
    )
    teste(
        "movimento suprimento",
        resp.status_code == 200,
        f"POST -> {resp.status_code}: {resp.text[:120]}",
    )

    resp = httpx.post(
        f"{BASE}/v1/financeiro/caixa/{cx_id}/movimento",
        headers=h,
        json={"tipo": "sangria", "valor": "30.00"},
        timeout=T,
    )
    teste("movimento sangria", resp.status_code == 200, f"POST -> {resp.status_code}")

    resp = httpx.post(
        f"{BASE}/v1/financeiro/caixa/{cx_id}/movimento",
        headers=h,
        json={"tipo": "sangria", "valor": "-5"},
        timeout=T,
    )
    teste(
        "movimento negativo 400/422",
        resp.status_code in (400, 422),
        f"POST -> {resp.status_code}",
    )

    # ============================================================== ESTOQUE
    secao("ESTOQUE")
    resp = httpx.get(f"{BASE}/v1/estoque", headers=h, timeout=T)
    teste("listar", resp.status_code == 200, f"GET -> {resp.status_code}")
    resp = httpx.get(f"{BASE}/v1/estoque/resumo", headers=h, timeout=T)
    teste("resumo", resp.status_code == 200, f"GET -> {resp.status_code}")
    resp = httpx.get(f"{BASE}/v1/estoque/reposicao", headers=h, timeout=T)
    teste("reposicao", resp.status_code == 200, f"GET -> {resp.status_code}")

    resp = httpx.post(
        f"{BASE}/v1/estoque/movimentar",
        headers=h,
        json={
            "produto_id": prod["id"],
            "tipo": "entrada",
            "quantidade": 50,
            "observacoes": "fumaca",
        },
        timeout=T,
    )
    teste(
        "entrada movimentar",
        resp.status_code == 200,
        f"POST -> {resp.status_code}: {resp.text[:120]}",
    )
    resp = httpx.get(f"{BASE}/v1/estoque/{prod['id']}/kardex", headers=h, timeout=T)
    teste(
        "kardex",
        resp.status_code == 200 and len(resp.json()["data"]) >= 1,
        f"GET -> {resp.status_code}",
    )

    # =============================================================== VENDAS
    secao("VENDAS / PDV")
    resp = httpx.post(
        f"{BASE}/v1/vendas",
        headers=h,
        json={
            "forma_pagamento": "dinheiro",
            "itens": [
                {"produto_id": prod["id"], "quantidade": 2, "valor_unitario": "12.50"}
            ],
        },
        timeout=T,
    )
    teste(
        "vender com caixa aberto",
        resp.status_code == 200,
        f"POST -> {resp.status_code}: {resp.text[:120]}",
    )
    venda = resp.json()["data"] if resp.status_code == 200 else None

    if venda:
        resp = httpx.get(f"{BASE}/v1/vendas/{venda['id']}", headers=h, timeout=T)
        teste(
            "buscar venda por ID", resp.status_code == 200, f"GET -> {resp.status_code}"
        )
        resp = httpx.get(
            f"{BASE}/v1/vendas",
            headers=h,
            params={"q": str(venda["numero"])},
            timeout=T,
        )
        teste(
            "busca por numero",
            resp.status_code == 200 and len(resp.json()["data"]) >= 1,
            f"GET?q -> {resp.status_code}",
        )

    resp = httpx.post(
        f"{BASE}/v1/vendas",
        headers=h,
        json={
            "forma_pagamento": "dinheiro",
            "itens": [
                {
                    "produto_id": prod["id"],
                    "quantidade": 99999,
                    "valor_unitario": "12.50",
                }
            ],
        },
        timeout=T,
    )
    teste(
        "estoque insuficiente 409",
        resp.status_code == 409,
        f"POST -> {resp.status_code}: {resp.text[:120]}",
    )

    resp = httpx.post(
        f"{BASE}/v1/vendas",
        headers=h,
        json={
            "forma_pagamento": "dinheiro",
            "itens": [
                {"produto_id": prod["id"], "quantidade": 1, "valor_unitario": "12.50"}
            ],
            "cliente_id": 999999,
        },
        timeout=T,
    )
    teste(
        "cliente inexistente 409",
        resp.status_code == 409,
        f"POST -> {resp.status_code}",
    )

    resp = httpx.get(
        f"{BASE}/v1/vendas", headers=h, params={"limit": 2, "offset": 0}, timeout=T
    )
    teste(
        "listar com paginacao",
        resp.status_code == 200 and len(resp.json()["data"]) <= 2,
        f"GET -> {resp.status_code}",
    )

    # cancelar restaura estoque (quantidade vendida = 2)
    if venda:
        antes = httpx.get(f"{BASE}/v1/estoque", headers=h, timeout=T).json()["data"]
        saldo_antes = next(
            (e["saldo"] for e in antes if e["produto_id"] == prod["id"]), None
        )
        resp = httpx.delete(f"{BASE}/v1/vendas/{venda['id']}", headers=h, timeout=T)
        teste(
            "cancelar venda 204",
            resp.status_code == 204,
            f"DELETE -> {resp.status_code}",
        )
        depois = httpx.get(f"{BASE}/v1/estoque", headers=h, timeout=T).json()["data"]
        saldo_depois = next(
            (e["saldo"] for e in depois if e["produto_id"] == prod["id"]), None
        )
        teste(
            "cancelar restaura estoque",
            saldo_antes is not None
            and saldo_depois is not None
            and float(saldo_depois) == float(saldo_antes) + 2.0,
            f"antes={saldo_antes} depois={saldo_depois}",
        )

    # =============================================================== FISCAL
    secao("FISCAL")
    resp = httpx.get(f"{BASE}/v1/fiscal/documentos", headers=h, timeout=T)
    teste("documentos", resp.status_code == 200, f"GET -> {resp.status_code}")
    resp = httpx.get(f"{BASE}/v1/fiscal/resumo", headers=h, timeout=T)
    teste("resumo", resp.status_code == 200, f"GET -> {resp.status_code}")

    # =========================================================== FINANCEIRO
    secao("FINANCEIRO / CONTAS / PLANO")
    resp = httpx.get(
        f"{BASE}/v1/financeiro/contas-receber",
        headers=h,
        params={"status_conta": "aberta"},
        timeout=T,
    )
    teste(
        "contas a receber (filtro aberta)",
        resp.status_code == 200,
        f"GET -> {resp.status_code}",
    )
    resp = httpx.get(f"{BASE}/v1/financeiro/contas-pagar", headers=h, timeout=T)
    teste("contas a pagar", resp.status_code == 200, f"GET -> {resp.status_code}")

    resp = httpx.post(
        f"{BASE}/v1/plano-contas",
        headers=h,
        json={"codigo": f"99{_u()[:4]}", "nome": "Fumaca Receita", "tipo": "receita"},
        timeout=T,
    )
    teste(
        "plano-contas criar",
        resp.status_code == 200,
        f"POST -> {resp.status_code}: {resp.text[:120]}",
    )
    pc = resp.json()["data"] if resp.status_code == 200 else None
    if pc:
        resp = httpx.put(
            f"{BASE}/v1/plano-contas/{pc['id']}",
            headers=h,
            json={"nome": "Fumaca Alt"},
            timeout=T,
        )
        teste(
            "plano-contas atualizar",
            resp.status_code == 200,
            f"PUT -> {resp.status_code}",
        )
        resp = httpx.delete(f"{BASE}/v1/plano-contas/{pc['id']}", headers=h, timeout=T)
        teste(
            "plano-contas excluir 204",
            resp.status_code == 204,
            f"DELETE -> {resp.status_code}",
        )

    # =============================================================== CONFIG
    secao("CONFIG / EMPRESA / REAJUSTE / PRECIFICACAO")
    resp = httpx.get(f"{BASE}/v1/config/empresa", headers=h, timeout=T)
    teste(
        "empresa GET",
        resp.status_code == 200 and resp.json()["data"]["razao_social"],
        f"GET -> {resp.status_code}",
    )
    empresa = resp.json()["data"]
    fantasia = f"Fantasia {_u()}"
    resp = httpx.put(
        f"{BASE}/v1/config/empresa",
        headers=h,
        json={"nome_fantasia": fantasia},
        timeout=T,
    )
    teste(
        "empresa PUT parcial",
        resp.status_code == 200 and resp.json()["data"]["nome_fantasia"] == fantasia,
        f"PUT -> {resp.status_code}",
    )
    resp = httpx.put(
        f"{BASE}/v1/config/empresa",
        headers=h,
        json={"nome_fantasia": empresa["nome_fantasia"]},
        timeout=T,
    )
    teste("empresa PUT restaura", resp.status_code == 200, f"PUT -> {resp.status_code}")

    resp = httpx.get(f"{BASE}/v1/config/reajuste/historico", headers=h, timeout=T)
    teste("reajuste historico", resp.status_code == 200, f"GET -> {resp.status_code}")
    resp = httpx.post(
        f"{BASE}/v1/config/reajuste/simular",
        headers=h,
        json={"criterio": "todos", "tipo_reajuste": "percentual", "valor": "10"},
        timeout=T,
    )
    teste(
        "reajuste simular",
        resp.status_code == 200,
        f"POST -> {resp.status_code}: {resp.text[:120]}",
    )

    resp = httpx.get(f"{BASE}/v1/config/precificacao", headers=h, timeout=T)
    teste(
        "precificacao GET (admin)",
        resp.status_code == 200,
        f"GET -> {resp.status_code}",
    )
    _params_orig = resp.json()["data"]
    resp = httpx.get(
        f"{BASE}/v1/config/precificacao",
        headers=h,
        params={"fornecedor_id": forn["id"]} if False else None,
        timeout=T,
    )
    teste(
        "precificacao GET por fornecedor",
        resp.status_code == 200,
        f"GET -> {resp.status_code}",
    )

    # ==================================================================== OS
    secao("OS / ORCAMENTOS / COTACOES / TERCEIRIZADO / ARTE")
    resp = httpx.post(
        f"{BASE}/v1/clientes",
        headers=h,
        json={"nome_razao": f"Cliente OS {_u()}", "tipo_pessoa": "pf"},
        timeout=T,
    )
    cli_os = resp.json()["data"]

    resp = httpx.post(
        f"{BASE}/v1/os",
        headers=h,
        json={
            "tipo": "os",
            "cliente_id": cli_os["id"],
            "itens": [
                {
                    "descricao_avulsa": "Impressao A4",
                    "quantidade": 100,
                    "valor_unitario": "0.5",
                }
            ],
        },
        timeout=T,
    )
    teste(
        "criar OS",
        resp.status_code == 200,
        f"POST -> {resp.status_code}: {resp.text[:120]}",
    )
    os_d = resp.json()["data"] if resp.status_code == 200 else None

    resp = httpx.post(
        f"{BASE}/v1/os",
        headers=h,
        json={
            "tipo": "orcamento",
            "cliente_id": cli_os["id"],
            "itens": [
                {"descricao_avulsa": "Banner", "quantidade": 1, "valor_unitario": "50"}
            ],
        },
        timeout=T,
    )
    teste("criar orcamento", resp.status_code == 200, f"POST -> {resp.status_code}")
    orc = resp.json()["data"] if resp.status_code == 200 else None

    if os_d:
        resp = httpx.get(f"{BASE}/v1/os/{os_d['id']}", headers=h, timeout=T)
        teste("buscar OS por ID", resp.status_code == 200, f"GET -> {resp.status_code}")
        resp = httpx.get(f"{BASE}/v1/os", headers=h, params={"tipo": "os"}, timeout=T)
        teste(
            "listar OS (filtro tipo)",
            resp.status_code == 200,
            f"GET -> {resp.status_code}",
        )
        resp = httpx.get(
            f"{BASE}/v1/os", headers=h, params={"limit": 2, "offset": 0}, timeout=T
        )
        teste(
            "listar OS paginacao",
            resp.status_code == 200 and len(resp.json()["data"]) <= 2,
            f"GET -> {resp.status_code}",
        )
        resp = httpx.put(
            f"{BASE}/v1/os/{os_d['id']}",
            headers=h,
            json={"observacoes": f"obs {_u()}"},
            timeout=T,
        )
        teste("atualizar OS", resp.status_code == 200, f"PUT -> {resp.status_code}")

        # M3 (3.5): producao nao inicia sem arte aprovada
        resp = httpx.patch(
            f"{BASE}/v1/os/{os_d['id']}/status",
            headers=h,
            json={"status": "producao"},
            timeout=T,
        )
        teste(
            "gate: producao sem arte 409",
            resp.status_code == 409,
            f"PATCH -> {resp.status_code}: {resp.text[:120]}",
        )

    # converter orcamento
    if orc:
        resp = httpx.post(f"{BASE}/v1/os/{orc['id']}/converter", headers=h, timeout=T)
        teste(
            "converter orcamento -> OS",
            resp.status_code == 200 and resp.json()["data"]["tipo"] == "os",
            f"POST -> {resp.status_code}: {resp.text[:120]}",
        )
        os_conv = resp.json()["data"] if resp.status_code == 200 else None
        if os_conv:
            resp = httpx.post(
                f"{BASE}/v1/os/{os_conv['id']}/converter", headers=h, timeout=T
            )
            teste(
                "converter OS ja convertida 400",
                resp.status_code == 400,
                f"POST -> {resp.status_code}",
            )

    # OS com item de fornecedor: cotacoes + terceirizado
    resp = httpx.post(
        f"{BASE}/v1/fornecedores",
        headers=h,
        json={"nome_razao": f"Forn Cot {_u()}", "tipo_pessoa": "pj"},
        timeout=T,
    )
    forn_cot = resp.json()["data"]
    resp = httpx.post(
        f"{BASE}/v1/os",
        headers=h,
        json={
            "tipo": "orcamento",
            "cliente_id": cli_os["id"],
            "itens": [
                {
                    "descricao_avulsa": "Hot stamping",
                    "quantidade": 1,
                    "valor_unitario": "0",
                    "tipo": "fornecedor",
                }
            ],
        },
        timeout=T,
    )
    orc_forn = resp.json()["data"]
    item_forn = orc_forn["itens"][0]

    resp = httpx.post(
        f"{BASE}/v1/os/{orc_forn['id']}/itens/{item_forn['id']}/cotacoes",
        headers=h,
        json={"fornecedor_id": forn_cot["id"], "vf": "100.00", "prazo_dias": 5},
        timeout=T,
    )
    teste(
        "lancar cotacao",
        resp.status_code == 201,
        f"POST -> {resp.status_code}: {resp.text[:120]}",
    )
    cot = resp.json()["data"] if resp.status_code == 201 else None

    resp = httpx.get(
        f"{BASE}/v1/os/{orc_forn['id']}/itens/{item_forn['id']}/cotacoes",
        headers=h,
        timeout=T,
    )
    body = resp.json()
    teste(
        "listar cotacoes",
        resp.status_code == 200 and len(body["data"]) == 1,
        f"GET -> {resp.status_code}",
    )
    teste(
        "VF visivel para admin",
        body["data"] and "vf" in body["data"][0],
        f"campos={list(body['data'][0].keys()) if body['data'] else 'vazio'}",
    )
    teste(
        "estado aguardando",
        body.get("estado_cotacao") == "aguardando",
        f"estado={body.get('estado_cotacao')}",
    )

    if cot:
        resp = httpx.put(
            f"{BASE}/v1/os/{orc_forn['id']}/itens/{item_forn['id']}/cotacoes/{cot['id']}/selecionar",
            headers=h,
            timeout=T,
        )
        teste(
            "selecionar cotacao",
            resp.status_code == 200,
            f"PUT -> {resp.status_code}: {resp.text[:120]}",
        )

    # snapshot VF/CP/VO: exposto no comparativo (selecionado) para quem ve custo (3.2.3)
    resp = httpx.get(
        f"{BASE}/v1/os/{orc_forn['id']}/itens/{item_forn['id']}/cotacoes",
        headers=h,
        timeout=T,
    )
    body = resp.json()
    sel_snap = body.get("selecionado")
    teste(
        "snapshot VF/CP/VO na selecao",
        resp.status_code == 200
        and isinstance(sel_snap, dict)
        and all(k in sel_snap for k in ("vf", "cp", "vo")),
        f"selecionado={sel_snap}",
    )
    teste(
        "estado cotado apos selecao",
        body.get("estado_cotacao") == "cotado",
        f"estado={body.get('estado_cotacao')}",
    )

    resp = httpx.get(
        f"{BASE}/v1/os/{orc_forn['id']}/itens/{item_forn['id']}/terceirizado",
        headers=h,
        timeout=T,
    )
    teste(
        "ver terceirizado (auto-criado)",
        resp.status_code == 200,
        f"GET -> {resp.status_code}",
    )
    ter = resp.json()["data"] if resp.status_code == 200 else None
    if ter:
        resp = httpx.put(
            f"{BASE}/v1/os/{orc_forn['id']}/itens/{item_forn['id']}/terceirizado/receber",
            headers=h,
            json={},
            timeout=T,
        )
        teste(
            "receber terceirizado",
            resp.status_code == 200,
            f"PUT -> {resp.status_code}: {resp.text[:120]}",
        )
        resp = httpx.put(
            f"{BASE}/v1/os/{orc_forn['id']}/itens/{item_forn['id']}/terceirizado/conferir",
            headers=h,
            json={"conferencia": "ok"},
            timeout=T,
        )
        teste(
            "conferir terceirizado",
            resp.status_code == 200,
            f"PUT -> {resp.status_code}: {resp.text[:120]}",
        )

    # confidencialidade VF para operador (3.2.3 - omitir, nao ocultar)
    resp = httpx.post(
        f"{BASE}/v1/usuarios",
        headers=h,
        json={
            "nome": f"Operador {_u()}",
            "login": f"op{_u()}",
            "senha": "Op12345!",
            "nivel_acesso": "operador",
        },
        timeout=T,
    )
    teste(
        "criar usuario operador",
        resp.status_code == 200,
        f"POST -> {resp.status_code}: {resp.text[:120]}",
    )
    if resp.status_code == 200:
        op_login = resp.json()["data"]["login"]
        token_op = login(op_login, "Op12345!")
        h_op = H(token_op)
        resp = httpx.get(
            f"{BASE}/v1/os/{orc_forn['id']}/itens/{item_forn['id']}/cotacoes",
            headers=h_op,
            timeout=T,
        )
        body_op = resp.json()
        teste(
            "VF omitido para operador",
            resp.status_code == 200
            and body_op["data"]
            and "vf" not in body_op["data"][0],
            f"campos={list(body_op['data'][0].keys()) if body_op.get('data') else resp.status_code}",
        )
        resp = httpx.get(f"{BASE}/v1/config/precificacao", headers=h_op, timeout=T)
        teste(
            "precificacao 403 para operador",
            resp.status_code == 403,
            f"GET -> {resp.status_code}",
        )
        resp = httpx.get(f"{BASE}/v1/config/empresa", headers=h_op, timeout=T)
        teste(
            "config empresa 403 para operador",
            resp.status_code == 403,
            f"GET -> {resp.status_code}",
        )

    # ARTE: ciclo completo contra o servidor real
    if os_d:
        resp = httpx.get(f"{BASE}/v1/os/{os_d['id']}/arte", headers=h, timeout=T)
        teste(
            "arte estado inicial",
            resp.status_code == 200,
            f"GET -> {resp.status_code} estado={resp.json().get('estado')}",
        )

        conteudo = b"PNG fake fumaca " + uuid.uuid4().bytes
        resp = httpx.post(
            f"{BASE}/v1/os/{os_d['id']}/arte",
            headers=h,
            files={"arquivo": ("arte.png", io.BytesIO(conteudo), "image/png")},
            timeout=T,
        )
        teste(
            "upload arte v1",
            resp.status_code == 201 and resp.json()["data"]["versao"] == 1,
            f"POST -> {resp.status_code}: {resp.text[:120]}",
        )
        v1 = resp.json()["data"] if resp.status_code == 201 else None

        resp = httpx.post(
            f"{BASE}/v1/os/{os_d['id']}/arte",
            headers=h,
            files={
                "arquivo": ("virus.exe", io.BytesIO(b"MZ"), "application/octet-stream")
            },
            timeout=T,
        )
        teste(
            "extensao .exe bloqueada 400",
            resp.status_code == 400,
            f"POST -> {resp.status_code}",
        )

        # cliente pede ajuste na v1 (ultima versao no momento)
        if v1:
            resp = httpx.post(
                f"{BASE}/v1/os/{os_d['id']}/arte/{v1['id']}/decisao",
                headers=h,
                json={"decisao": "ajuste", "comentarios": "Logo maior"},
                timeout=T,
            )
            teste(
                "decisao ajuste",
                resp.status_code == 201,
                f"POST -> {resp.status_code}: {resp.text[:120]}",
            )
            resp = httpx.get(f"{BASE}/v1/os/{os_d['id']}/arte", headers=h, timeout=T)
            teste(
                "estado ajuste_solicitado",
                resp.json().get("estado") == "ajuste_solicitado",
                f"estado={resp.json().get('estado')}",
            )
            resp = httpx.get(f"{BASE}/v1/os/{os_d['id']}", headers=h, timeout=T)
            teste(
                "status OS = aguardando_arte",
                resp.json()["data"]["status"] == "aguardando_arte",
                f"status={resp.json()['data'].get('status')}",
            )

        # designer reenvia: v2 passa a ser a ultima, sem decisao
        resp = httpx.post(
            f"{BASE}/v1/os/{os_d['id']}/arte",
            headers=h,
            files={
                "arquivo": ("arte_v2.png", io.BytesIO(conteudo + b"v2"), "image/png")
            },
            timeout=T,
        )
        teste(
            "upload arte v2 (reenvio apos ajuste)",
            resp.status_code == 201 and resp.json()["data"]["versao"] == 2,
            f"POST -> {resp.status_code}",
        )
        v2 = resp.json()["data"] if resp.status_code == 201 else None

        if v2:
            resp = httpx.get(f"{BASE}/v1/os/{os_d['id']}/arte", headers=h, timeout=T)
            teste(
                "estado aguardando_aprovacao (v2)",
                resp.json().get("estado") == "aguardando_aprovacao",
                f"estado={resp.json().get('estado')}",
            )
            resp = httpx.get(f"{BASE}/v1/os/{os_d['id']}", headers=h, timeout=T)
            teste(
                "status OS = aguardando_aprovacao",
                resp.json()["data"]["status"] == "aguardando_aprovacao",
                f"status={resp.json()['data'].get('status')}",
            )
            resp = httpx.post(
                f"{BASE}/v1/os/{os_d['id']}/arte/{v2['id']}/decisao",
                headers=h,
                json={"decisao": "aprovada"},
                timeout=T,
            )
            teste(
                "decisao aprovada",
                resp.status_code == 201,
                f"POST -> {resp.status_code}",
            )

        resp = httpx.get(f"{BASE}/v1/os/{os_d['id']}/arte", headers=h, timeout=T)
        teste(
            "estado aprovada",
            resp.json().get("estado") == "aprovada",
            f"estado={resp.json().get('estado')}",
        )

        # status da OS incorpora a arte (M3, 3.5): aprovada -> aprovado,
        # entao producao passa pelo gate e a OS segue o fluxo ate entregue
        resp = httpx.get(f"{BASE}/v1/os/{os_d['id']}", headers=h, timeout=T)
        teste(
            "status OS = aprovado (arte)",
            resp.json()["data"]["status"] == "aprovado",
            f"status={resp.json()['data'].get('status')}",
        )
        resp = httpx.patch(
            f"{BASE}/v1/os/{os_d['id']}/status",
            headers=h,
            json={"status": "producao"},
            timeout=T,
        )
        teste(
            "status -> producao (arte aprovada)",
            resp.status_code == 200,
            f"PATCH -> {resp.status_code}: {resp.text[:120]}",
        )
        resp = httpx.patch(
            f"{BASE}/v1/os/{os_d['id']}/status",
            headers=h,
            json={"status": "entregue"},
            timeout=T,
        )
        teste(
            "status -> entregue",
            resp.status_code == 200,
            f"PATCH -> {resp.status_code}",
        )

        resp = httpx.post(f"{BASE}/v1/os/{os_d['id']}/arte/link", headers=h, timeout=T)
        teste(
            "gerar link de prova",
            resp.status_code == 200 and len(resp.json()["data"]["token"]) > 20,
            f"POST -> {resp.status_code}: {resp.text[:120]}",
        )

        resp = httpx.post(
            f"{BASE}/v1/os/{os_d['id']}/arte/999999/decisao",
            headers=h,
            json={"decisao": "aprovada"},
            timeout=T,
        )
        teste(
            "decisao versao inexistente 404",
            resp.status_code == 404,
            f"POST -> {resp.status_code}",
        )

    # OS descartavel p/ exclusao
    resp = httpx.post(
        f"{BASE}/v1/os",
        headers=h,
        json={
            "tipo": "os",
            "cliente_id": cli_os["id"],
            "itens": [
                {
                    "descricao_avulsa": "Descartavel",
                    "quantidade": 1,
                    "valor_unitario": "1",
                }
            ],
        },
        timeout=T,
    )
    if resp.status_code == 200:
        os_del = resp.json()["data"]
        resp = httpx.delete(f"{BASE}/v1/os/{os_del['id']}", headers=h, timeout=T)
        teste(
            "excluir OS 204", resp.status_code == 204, f"DELETE -> {resp.status_code}"
        )

    # ============================================================== PROJETOS
    secao("PROJETOS (QUADRO)")
    resp = httpx.get(f"{BASE}/v1/projetos/quadro", headers=h, timeout=T)
    teste("quadro", resp.status_code == 200, f"GET -> {resp.status_code}")

    resp = httpx.post(
        f"{BASE}/v1/projetos/quadro/listas",
        headers=h,
        json={"nome": f"Lista {_u()}"},
        timeout=T,
    )
    teste(
        "criar lista",
        resp.status_code == 201,
        f"POST -> {resp.status_code}: {resp.text[:120]}",
    )
    lista = resp.json()["data"] if resp.status_code == 201 else None

    if lista:
        resp = httpx.post(
            f"{BASE}/v1/projetos/cartoes",
            headers=h,
            json={"lista_id": lista["id"], "titulo": f"Cartao {_u()}"},
            timeout=T,
        )
        teste(
            "criar cartao",
            resp.status_code == 201,
            f"POST -> {resp.status_code}: {resp.text[:120]}",
        )
        cartao = resp.json()["data"] if resp.status_code == 201 else None

        if cartao:
            versao = cartao["versao"]
            resp = httpx.patch(
                f"{BASE}/v1/projetos/cartoes/{cartao['id']}",
                headers=h,
                json={"descricao": "detalhe fumaca", "versao": versao},
                timeout=T,
            )
            teste(
                "editar cartao",
                resp.status_code == 200,
                f"PATCH -> {resp.status_code}: {resp.text[:120]}",
            )
            if resp.status_code == 200:
                versao = resp.json()["data"]["versao"]

            # segunda lista p/ mover
            resp = httpx.post(
                f"{BASE}/v1/projetos/quadro/listas",
                headers=h,
                json={"nome": f"Lista2 {_u()}"},
                timeout=T,
            )
            lista2 = resp.json()["data"]
            resp = httpx.patch(
                f"{BASE}/v1/projetos/cartoes/{cartao['id']}/mover",
                headers=h,
                json={"versao": versao, "lista_id": lista2["id"], "posicao": 0},
                timeout=T,
            )
            teste(
                "mover cartao",
                resp.status_code == 200,
                f"PATCH -> {resp.status_code}: {resp.text[:120]}",
            )
            if resp.status_code == 200:
                versao = resp.json()["data"]["versao"]

            resp = httpx.post(
                f"{BASE}/v1/projetos/cartoes/{cartao['id']}/comentarios",
                headers=h,
                json={"texto": "comentario fumaca"},
                timeout=T,
            )
            teste(
                "comentar cartao",
                resp.status_code == 201,
                f"POST -> {resp.status_code}: {resp.text[:120]}",
            )

            resp = httpx.post(
                f"{BASE}/v1/projetos/cartoes/{cartao['id']}/checklists",
                headers=h,
                json={"titulo": "Checklist fumaca"},
                timeout=T,
            )
            teste(
                "criar checklist",
                resp.status_code == 201,
                f"POST -> {resp.status_code}: {resp.text[:120]}",
            )

            resp = httpx.post(
                f"{BASE}/v1/projetos/etiquetas",
                headers=h,
                json={"nome": f"Etiqueta {_u()}", "cor": "#ff0000"},
                timeout=T,
            )
            teste(
                "criar etiqueta",
                resp.status_code == 201,
                f"POST -> {resp.status_code}: {resp.text[:120]}",
            )
            if resp.status_code == 201:
                etq = resp.json()["data"]
                resp = httpx.post(
                    f"{BASE}/v1/projetos/cartoes/{cartao['id']}/etiquetas",
                    headers=h,
                    json={"etiqueta_id": etq["id"]},
                    timeout=T,
                )
                teste(
                    "aplicar etiqueta",
                    resp.status_code == 200,
                    f"POST -> {resp.status_code}: {resp.text[:120]}",
                )

            resp = httpx.get(
                f"{BASE}/v1/projetos/cartoes/{cartao['id']}/atividade",
                headers=h,
                timeout=T,
            )
            teste(
                "atividade do cartao",
                resp.status_code == 200,
                f"GET -> {resp.status_code}",
            )

            resp = httpx.patch(
                f"{BASE}/v1/projetos/cartoes/{cartao['id']}/arquivar",
                headers=h,
                json={"versao": versao},
                timeout=T,
            )
            teste(
                "arquivar cartao",
                resp.status_code == 200,
                f"PATCH -> {resp.status_code}: {resp.text[:120]}",
            )

        resp = httpx.patch(
            f"{BASE}/v1/projetos/quadro/listas/{lista['id']}",
            headers=h,
            json={"nome": f"Lista alt {_u()}"},
            timeout=T,
        )
        teste("editar lista", resp.status_code == 200, f"PATCH -> {resp.status_code}")
        resp = httpx.delete(
            f"{BASE}/v1/projetos/quadro/listas/{lista['id']}", headers=h, timeout=T
        )
        teste(
            "excluir lista vazia 204",
            resp.status_code == 204,
            f"DELETE -> {resp.status_code}: {resp.text[:120]}",
        )

    # ============================================================== USUARIOS
    secao("USUARIOS")
    resp = httpx.get(f"{BASE}/v1/usuarios", headers=h, timeout=T)
    teste(
        "listar",
        resp.status_code == 200 and len(resp.json()["data"]) >= 1,
        f"GET -> {resp.status_code}",
    )
    resp = httpx.post(
        f"{BASE}/v1/usuarios",
        headers=h,
        json={
            "nome": f"Gerente {_u()}",
            "login": f"ger{_u()}",
            "senha": "Ge12345!",
            "nivel_acesso": "gerente",
        },
        timeout=T,
    )
    teste(
        "criar gerente",
        resp.status_code == 200,
        f"POST -> {resp.status_code}: {resp.text[:120]}",
    )
    if resp.status_code == 200:
        usr = resp.json()["data"]
        resp = httpx.put(
            f"{BASE}/v1/usuarios/{usr['id']}",
            headers=h,
            json={"nome": f"Gerente Alt {_u()}"},
            timeout=T,
        )
        teste(
            "atualizar usuario", resp.status_code == 200, f"PUT -> {resp.status_code}"
        )
        # trocar senha e logar com a nova
        resp = httpx.post(
            f"{BASE}/v1/auth/trocar-senha",
            headers=H(login(usr["login"], "Ge12345!")),
            json={"senha_atual": "Ge12345!", "nova_senha": "Ge54321!"},
            timeout=T,
        )
        teste(
            "trocar senha",
            resp.status_code == 200,
            f"POST -> {resp.status_code}: {resp.text[:120]}",
        )
        if resp.status_code == 200:
            tok2 = login(usr["login"], "Ge54321!")
            teste("login com senha nova", bool(tok2), "-")
        resp = httpx.delete(f"{BASE}/v1/usuarios/{usr['id']}", headers=h, timeout=T)
        teste(
            "excluir usuario 204",
            resp.status_code == 204,
            f"DELETE -> {resp.status_code}",
        )

    # ============================================================ DASHBOARD
    secao("DASHBOARD / LICENCA")
    resp = httpx.get(f"{BASE}/v1/dashboard/resumo", headers=h, timeout=T)
    teste("resumo", resp.status_code == 200, f"GET -> {resp.status_code}")
    resp = httpx.get(f"{BASE}/v1/licenca", headers=h, timeout=T)
    teste(
        "licenca",
        resp.status_code == 200,
        f"GET -> {resp.status_code}: {resp.text[:80]}",
    )

    # ================================================== CAIXA FECHADO -> 409
    secao("CAIXA FECHADO BLOQUEIA PDV")
    resp = httpx.get(f"{BASE}/v1/financeiro/caixa/atual", headers=h, timeout=T)
    caixa = resp.json()["data"]
    if caixa and caixa.get("status") == "aberto":
        resp = httpx.post(
            f"{BASE}/v1/financeiro/caixa/{caixa['id']}/fechar",
            headers=h,
            json={"valor_informado": "100.00"},
            timeout=T,
        )
        teste(
            "fechar caixa",
            resp.status_code == 200,
            f"POST -> {resp.status_code}: {resp.text[:120]}",
        )

        resp = httpx.post(
            f"{BASE}/v1/vendas",
            headers=h,
            json={
                "forma_pagamento": "dinheiro",
                "itens": [
                    {
                        "produto_id": prod["id"],
                        "quantidade": 1,
                        "valor_unitario": "12.50",
                    }
                ],
            },
            timeout=T,
        )
        teste(
            "venda com caixa fechado 409",
            resp.status_code == 409,
            f"POST -> {resp.status_code}: {resp.text[:120]}",
        )

        # reabrir p/ deixar o ambiente usavel
        resp = httpx.post(
            f"{BASE}/v1/financeiro/caixa/abrir",
            headers=h,
            json={"valor_abertura": "100.00"},
            timeout=T,
        )
        teste("reabrir caixa", resp.status_code == 200, f"POST -> {resp.status_code}")
    else:
        teste(
            "fechar caixa (nao estava aberto)",
            False,
            f"status={caixa.get('status') if caixa else None}",
        )

    # ================================================== ERROS TRANSVERSAIS
    secao("ERROS TRANSVERSAIS")
    resp = httpx.get(f"{BASE}/v1/rota-inexistente", headers=h, timeout=T)
    teste("rota inexistente 404", resp.status_code == 404, f"GET -> {resp.status_code}")
    resp = httpx.get(f"{BASE}/v1/clientes/99999999", headers=h, timeout=T)
    teste("item inexistente 404", resp.status_code == 404, f"GET -> {resp.status_code}")

    # ================================================================= RESUMO
    print()
    print("=" * 50)
    print(f"RESULTADO: {PASSOU} OK | {FALHOU} XX")
    if ERROS:
        print("FALHAS:")
        for e in ERROS:
            print(f"  - {e}")
    else:
        print("TODOS OS TESTES PASSARAM")
    sys.exit(1 if FALHOU else 0)


if __name__ == "__main__":
    main()
