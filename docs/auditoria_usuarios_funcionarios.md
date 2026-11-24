# Auditoria — Funcionários, Usuários e Permissões

Auditoria de DB/backend/frontend realizada em 24/11/2026 e corrigida na v0.5.30.
Segue o que foi encontrado, o que foi corrigido e o que segue como decisão em
aberto.

## Corrigido nesta versão

| ID | Achado | Correção | Arquivo |
|---|---|---|---|
| A1 | `login()` não verificava `ativo` — usuário desativado recebia token válido e só era recusado na requisição seguinte | Login recusa com **401** e mesma mensagem de credencial inválida (sem enumeração); hash neutro preserva o tempo de resposta | `services/auth_service.py` |
| A2 | `verificar_bloqueio()` rodava só no login — sessão aberta continuava válida após bloqueio | Toda requisição autenticada revalida o bloqueio (**423**) em `_autenticar()`: revogação imediata | `deps.py`, `main.py` (desktop) |
| A4 | Reset por admin revogava sessões, mas não limpava `falhas_login`/`bloqueado_em`/`primeiro_acesso`, e podia deslogar o próprio admin | Reset limpa os três estados; `revogar_sessoes()` ganhou `preservar_token` para manter a sessão que executou a operação | `api/usuarios.py`, `services/auth_service.py` |
| A5 | `DELETE /v1/funcionarios/{id}` só marcava o funcionário inativo — usuário vinculado continuava ativo | Desativa o usuário vinculado (cobre `Funcionario.usuario_id` e `Usuario.funcionario_id`) e revoga suas sessões | `api/cadastros.py` |
| A8 | `PUT /v1/funcionarios/{id}` com `{}` estourava `UnboundLocalError` → **500** | Corpo sem campos válidos retorna **400** com orientação | `api/cadastros.py` |
| A11 | Não havia forma de desbloquear um usuário sem trocar a senha | Novo endpoint `POST /v1/usuarios/{id}/desbloquear` (ADMIN): limpa falhas e bloqueio | `api/usuarios.py` |

O desktop agora trata **423** na restauração de sessão como revogação (limpa a
cópia local e abre o login com a mensagem do backend), e não mais como falha de
transporte do daemon.

## Pontos sólidos confirmados

- `UniqueConstraint("filial_id", "login")` permite o mesmo login em gráficas
  distintas.
- Matriz do desktop (`core/rbac.py`) replica o RBAC **não hierárquico** do
  backend (`require_perfis`): `caixa` vê Financeiro/Fiscal e `operador` não.
- Anti-self-lockout para desativação/rebaixamento e proibição de trocar de
  filial no update de usuário.

## Pendente (decisão/autorização)

- **A3** — sem `PRINTGEST_EMPRESA_CNPJ` e sem CNPJ no cofre, `usuario_por_login`
  e `_escopo` caem para consulta global (modo legado, ver incidente LGPD).
  Produção sempre com CNPJ configurado na ativação.
- **A6** — FKs cruzadas (`Usuario.funcionario_id` ↔ `Funcionario.usuario_id`)
  não têm constraint de coerência no banco. A correção A5 tolera divergências,
  mas a sanção dos registros antigos exige migration — **não aplicada sem
  autorização**.
- **A7** — `Usuario.filial_id` é anulável; `get_filial_atual` cai para a filial 1.
- **A9** — sem RLS: o isolamento é responsabilidade da aplicação.
- **A10** — política de senha validada só no schema (tamanho); sem histórico ou
  expiração.

## Validação

- Backend: **463 passed** (8 novos testes em `tests/test_usuarios_funcionarios.py`).
- Desktop: **476 passed, 4 xfailed** (1 novo teste em `tests/test_main.py`).
- Mutação: **22/22 mortos** (5 novos mutantes: login inativo, bloqueio não
  reforçado, reset sem limpar bloqueio, delete sem desativar usuário e PUT vazio).
