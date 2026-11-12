# Multi-tenant no PrintGest (banco compartilhado)

O projeto Neon do PrintGest (`printg`) é **único e compartilhado entre
gráficas**. O isolamento entre elas é **lógico, por inquilino**:

## Como funciona

- **Inquilino = `empresa`** (CNPJ). Cada instalação (daemon) declara o inquilino
  que serve via `PRINTGEST_EMPRESA_CNPJ` no `.env` da instalação.
- O **bootstrap** (startup do Local API Service) garante, idempotentemente, a
  `empresa` + `filial` ("Matriz") + `admin` do inquilino.
- O **login** busca o usuário **dentro do inquilino** — o mesmo login `admin`
  pode existir em gráficas distintas, cada uma com a própria senha.
- Toda listagem/escrita já é escopada por `filial_id` (`FilialDep`), e o
  usuário do inquilino pertence às filiais dele → **gráfica A nunca vê dados
  da gráfica B**.
- A **licença** é por inquilino (`licenca.empresa_id`): cada instalação ativa e
  revalida a própria licença no mesmo banco (o blob DPAPI é da máquina delas).

Sem `PRINTGEST_EMPRESA_CNPJ` (dev/demo), o sistema opera no modo single-tenant
legado: bootstrap cria a empresa demo `11111111000111`, login é global.

## Migração

`b7c8d9e0f1a2` — `licenca.empresa_id` (backfill pelo CNPJ da linha) e
unicidades globais → **por filial**: `usuario.login`, `cliente.cpf_cnpj`,
`fornecedor.cpf_cnpj`, `funcionario.cpf`, `produto.codigo`.

## Provisionar uma nova gráfica (checklist)

O script `scripts/provisionar_cliente.ps1` automatiza o checklist:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\provisionar_cliente.ps1 `
    -Cnpj 32667694000101 -RazaoSocial "Gráfica Exemplo Ltda" -Empacotar
```

Ele (1) grava `installer/env.instalacao` com o CNPJ/razão da gráfica e as
credenciais compartilhadas (lidas do `backend/.env`), (2) valida com
`scripts/configurar_auth_neon.py --env-file installer/env.instalacao`
(conexão, migrations, bootstrap do inquilino e estado do admin) e (3) com
`-Empacotar`, gera o instalador nomeado por CNPJ
(`PrintGest-Setup-<versao>-<cnpj8>.exe`).

Checklist manual equivalente:

1. Copie `installer/env.instalacao.example` → `installer/env.instalacao`
   (ignorado pelo git) e preencha:
   - `PRINTGEST_DATABASE_URL` — credencial do banco compartilhado;
   - `PRINTGEST_EMPRESA_CNPJ` — CNPJ da gráfica (**obrigatório**);
   - `PRINTGEST_EMPRESA_RAZAO_SOCIAL` — razão social (opcional);
   - `PRINTGEST_REDGEST_*` — contrato/licença dela;
   - `PRINTGEST_ADMIN_INICIAL_*` — política de primeiro acesso.
2. Valide antes de entregar: `scripts/configurar_auth_neon.py --env-file
   installer/env.instalacao` (conexão, migrations, bootstrap e estado do admin
   do inquilino).
3. `powershell -ExecutionPolicy Bypass -File scripts/empacotar.ps1` e entregue
   o instalador gerado **só para essa gráfica**.

> **Nunca** entregue o mesmo `env.instalacao` (ou um instalador gerado dele)
> para duas gráficas — é exatamente o vazamento documentado em
> `.lgpd/incidents/2026-11-10-vazamento-entre-inquilinos.md`.

## Limites conhecidos (fase 2)

- A credencial do banco é a mesma para todos os inquilinos: o isolamento é
  aplicativo. Quem tiver o `.env` consegue conectar direto no Postgres e ver
  tudo. Evolução recomendada: **RLS por inquilino no Neon** ou um banco por
  gráfica para clientes com exigência maior de segregação (LGPD).
