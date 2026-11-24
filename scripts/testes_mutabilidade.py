"""Testes de mutabilidade (mutation testing) para produtos/variações/estoque.

Aplica pequenas mutações controladas no código, roda o teste que deveria
detectá-la e restaura o arquivo original. Um mutante "sobrevivente" indica
uma lacuna na suíte; um mutante "morto" prova que o teste realmente protege
a regra de negócio.

Uso:
    backend/.venv/Scripts/python.exe scripts/testes_mutabilidade.py

Nenhuma mutação é persistida: a restauração acontece em `finally`, inclusive
se o pytest falhar. O script termina com exit code 1 se algum mutante
sobreviver ou se o repositório ficar sujo.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_FLAGS = ["-m", "pytest", "-q", "-p", "no:warnings", "--tb=no"]
# Cada suíte tem seu próprio venv (PySide6 só existe no de desktop).
_PY_BACKEND = RAIZ / "backend" / ".venv" / "Scripts" / "python.exe"
_PY_DESKTOP = RAIZ / "desktop" / ".venv" / "Scripts" / "python.exe"


def _pytest(pasta: str) -> list[str]:
    python = _PY_BACKEND if pasta == "backend" else _PY_DESKTOP
    return [str(python)] + _FLAGS


@dataclass(frozen=True)
class Mutante:
    nome: str
    arquivo: str          # relativo à raiz
    antigo: str
    novo: str
    teste: str            # node id do pytest
    pasta: str = "backend"


MUTANTES = [
    Mutante(
        "pai_servico_aceito",
        "backend/app/services/variacao_service.py",
        "if pai.tipo != TipoProduto.PRODUTO:",
        "if False:",
        "tests/test_produtos_variacoes_contrato.py::test_variacao_exige_produto_pai",
    ),
    Mutante(
        "filha_sem_controle_estoque",
        "backend/app/services/variacao_service.py",
        "controla_estoque=True,",
        "controla_estoque=False,",
        "tests/test_produtos_variacoes_contrato.py::test_filha_tem_estoque_proprio_e_pai_nao",
    ),
    Mutante(
        "saldo_inicial_da_filha_errado",
        "backend/app/services/variacao_service.py",
        "filial_id=filial_id, produto_id=filha.id, saldo=0",
        "filial_id=filial_id, produto_id=filha.id, saldo=5",
        "tests/test_produtos_variacoes_contrato.py::test_filha_tem_estoque_proprio_e_pai_nao",
    ),
    Mutante(
        "rbac_preco_desligado",
        "backend/app/api/crud_factory.py",
        "if RANK.get(usuario.nivel_acesso, 0) < RANK[nivel_preco]:",
        "if False:",
        "tests/test_produtos_variacoes_contrato.py::test_operador_nao_altera_preco",
    ),
    Mutante(
        "identidade_mutavel",
        "backend/app/api/cadastros.py",
        'campos_immutaveis={"sku", "uuid", "produto_pai_id", "tipo"},',
        "campos_immutaveis=set(),",
        "tests/test_produtos_variacoes_contrato.py::test_campos_de_identidade_sao_imutaveis",
    ),
    Mutante(
        "soft_delete_sem_cascata",
        "backend/app/api/cadastros.py",
        ').update({"ativo": False}),',
        ').update({"ativo": True}),',
        "tests/test_produtos_variacoes_contrato.py::test_soft_delete_do_pai_desativa_filhas",
    ),
    Mutante(
        "produto_inativo_movimentavel",
        "backend/app/services/estoque_service.py",
        "Produto.id == produto_id,\n            Produto.filial_id == filial_id,\n            Produto.ativo.is_(True),",
        "Produto.id == produto_id,\n            Produto.filial_id == filial_id,",
        "tests/test_produtos_variacoes_contrato.py::test_estoque_nao_movimenta_produto_inativo",
    ),
    Mutante(
        "kardex_saida_positiva",
        "backend/app/services/venda_service.py",
        "-item.quantidade if tipo == TipoMovEstoque.SAIDA",
        "item.quantidade if tipo == TipoMovEstoque.SAIDA",
        "tests/test_vendas.py::test_venda_baixa_estoque_e_registra_kardex",
    ),
    Mutante(
        "prefixo_sku_curto",
        "backend/app/schemas/cadastros.py",
        "prefixo_sku: str | None = Field(default=None, max_length=30)",
        "prefixo_sku: str | None = Field(default=None, max_length=10)",
        "tests/test_produtos_variacoes_contrato.py::test_prefixo_sku_de_30_caracteres_e_aceito",
    ),
    Mutante(
        "atributo_vazio_aceito",
        "backend/app/schemas/cadastros.py",
        "if not any((self.tamanho, self.marca, self.cor)):",
        "if False:",
        "tests/test_produtos_variacoes_contrato.py::test_schema_rejeita_variacao_sem_atributo",
    ),
    Mutante(
        "filtro_variantes_desligado",
        "backend/app/api/cadastros.py",
        'if request.query_params.get("somente_variantes", "").lower() == "true":',
        'if False:',
        "tests/test_produtos_variacoes_contrato.py::test_filtro_server_side_de_variantes",
    ),
    Mutante(
        "rbac_preco_na_geracao",
        "backend/app/api/cadastros.py",
        "and RANK.get(usuario.nivel_acesso, 0) < RANK[NivelAcesso.GERENTE]",
        "and False",
        "tests/test_produtos_variacoes_contrato.py::test_gerar_com_preco_exige_gerente",
    ),
    Mutante(
        "rbac_propagacao_desligado",
        "backend/app/api/cadastros.py",
        '"""Propaga preço/custo/mínimo do pai às variantes ativas (GERENTE+)."""\n    from app.deps import RANK\n\n    if RANK.get(usuario.nivel_acesso, 0) < RANK[NivelAcesso.GERENTE]:',
        '"""Propaga preço/custo/mínimo do pai às variantes ativas (GERENTE+)."""\n    from app.deps import RANK\n\n    if False:',
        "tests/test_produtos_variacoes_contrato.py::test_propagar_preco_para_variantes",
    ),
    Mutante(
        "propagacao_nao_altera_preco",
        "backend/app/services/variacao_service.py",
        "filha.preco_venda = pai.preco_venda",
        "filha.preco_venda = filha.preco_venda",
        "tests/test_produtos_variacoes_contrato.py::test_propagar_preco_para_variantes",
    ),
    Mutante(
        "log_http_desligado",
        "backend/app/main.py",
        '    logger.error(\n        "HTTP %s %s %s | filial=%s usuario=%s tipo=%s detail=%s",',
        '    logger.info(\n        "HTTP %s %s %s | filial=%s usuario=%s tipo=%s detail=%s",',
        "tests/test_logging_erros.py::test_404_e_detalhado_no_log",
    ),
    Mutante(
        "sanitizacao_desligada",
        "backend/app/core/log_seguranca.py",
        "    for padrao in _PADROES_SEGREDOS:",
        "    for padrao in ():",
        "tests/test_logging_erros.py::test_segredos_sao_mascarados_no_log",
    ),
    Mutante(
        "login_aceita_inativo",
        "backend/app/services/auth_service.py",
        '    if not usuario.ativo:\n        verify_password(senha, _HASH_NEUTRO)\n        raise HTTPException(\n            status_code=status.HTTP_401_UNAUTHORIZED,\n            detail="Usuário ou senha inválidos.",\n        )\n    verificar_bloqueio(usuario, agora)',
        "    verificar_bloqueio(usuario, agora)",
        "tests/test_usuarios_funcionarios.py::test_login_recusa_usuario_inativo",
    ),
    Mutante(
        "bloqueio_nao_reforcado",
        "backend/app/deps.py",
        "    verificar_bloqueio(usuario, agora)\n    # Expiração deslizante ECONÔMICA por inatividade: o TTL renova a cada",
        "    # Expiração deslizante ECONÔMICA por inatividade: o TTL renova a cada",
        "tests/test_usuarios_funcionarios.py::test_bloqueio_vale_em_requisicao_autenticada",
    ),
    Mutante(
        "reset_sem_limpar_bloqueio",
        "backend/app/api/usuarios.py",
        '        dados["falhas_login"] = 0\n        dados["bloqueado_em"] = None\n        dados["primeiro_acesso"] = False',
        '        dados["falhas_login"] = 0\n        dados["primeiro_acesso"] = False',
        "tests/test_usuarios_funcionarios.py::test_reset_senha_limpa_bloqueio",
    ),
    Mutante(
        "delete_funcionario_sem_desativar_usuario",
        "backend/app/api/cadastros.py",
        "        if usuario is not None:\n            usuario.ativo = False\n            revogar_sessoes(db, usuario.id)",
        "        if usuario is not None:\n            revogar_sessoes(db, usuario.id)",
        "tests/test_usuarios_funcionarios.py::test_excluir_funcionario_desativa_usuario_e_revoga_sessao",
    ),
    Mutante(
        "put_funcionario_vazio_aceito",
        "backend/app/api/cadastros.py",
        '    if not dados:\n        raise HTTPException(\n            status_code=status.HTTP_400_BAD_REQUEST,\n            detail="Nenhum campo válido para atualizar.",\n        )\n    item = (',
        "    item = (",
        "tests/test_usuarios_funcionarios.py::test_put_funcionario_vazio_retorna_400",
    ),
    Mutante(
        "pdv_nao_indexa_sku",
        "desktop/printgest/ui/modulos/venda_balcao.py",
        "for chave in (codigo, sku, barras):",
        "for chave in (codigo, barras):",
        "tests/test_venda_balcao.py::test_sku_exato_adiciona_pelo_cache_sem_chamar_endpoint",
        pasta="desktop",
    ),
]


def executar_teste(mutante: Mutante) -> int:
    return subprocess.run(
        _pytest(mutante.pasta) + [mutante.teste],
        cwd=RAIZ / mutante.pasta,
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    # Baseline: todos os testes devem passar antes de qualquer mutação.
    bases = {}
    for mutante in MUTANTES:
        bases.setdefault(mutante.teste, mutante.pasta)
    for teste, pasta in bases.items():
        codigo = subprocess.run(
            _pytest(pasta) + [teste], cwd=RAIZ / pasta, capture_output=True, text=True
        ).returncode
        if codigo != 0:
            print(f"[BASE FALHOU] {teste} (pasta={pasta})")
            return 1
    print(f"[BASE] {len(bases)} testes passando.\n")

    sobreviventes: list[str] = []
    mortos = 0
    with tempfile.TemporaryDirectory() as tmp:
        for mutante in MUTANTES:
            caminho = RAIZ / mutante.arquivo
            backup = Path(tmp) / f"{mortos + len(sobreviventes)}_{caminho.name}"
            shutil.copy2(caminho, backup)
            original = caminho.read_text(encoding="utf-8")
            if mutante.antigo not in original:
                print(f"[MUTAÇÃO NÃO APLICADA] {mutante.nome}: trecho não encontrado")
                sobreviventes.append(mutante.nome)
                continue
            try:
                caminho.write_text(
                    original.replace(mutante.antigo, mutante.novo, 1),
                    encoding="utf-8",
                    newline="",
                )
                codigo = executar_teste(mutante)
            finally:
                shutil.copy2(backup, caminho)
            if codigo != 0:
                mortos += 1
                print(f"[MORTO]     {mutante.nome}")
            else:
                sobreviventes.append(mutante.nome)
                print(f"[SOBREVIVENTE] {mutante.nome} — {mutante.teste}")

    print(f"\nResultado: {mortos} mortos, {len(sobreviventes)} sobreviventes")
    return 1 if sobreviventes else 0


if __name__ == "__main__":
    raise SystemExit(main())
