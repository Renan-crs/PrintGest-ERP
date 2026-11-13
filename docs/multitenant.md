# Multi-tenant no PrintGest (banco compartilhado)

O projeto Neon do PrintGest (`printg`) é **único e compartilhado entre
gráficas**. O isolamento entre elas é **lógico, por inquilino**:

## Como funciona

- **Instalador universal** (como Office/Corel): um único instalador para todas
  as gráficas. O assistente pergunta o **CNPJ da gráfica** na instalação e
  grava no `.env` da instalação (`PRINTGEST_EMPRESA_CNPJ`) — o `.env` embutido
  no pacote **não** tem CNPJ.
- **Inquilino = `empresa`** (CNPJ). O **bootstrap** (startup do Local API
  Service) garante, idempotentemente, a `empresa` + `filial` ("Matriz") +
  `admin` do inquilino.
- O **login** busca o usuário **dentro do inquilino** — o mesmo login `admin`
  pode existir em gráficas distintas, cada uma com a própria senha.
- Toda listagem/escrita já é escopada por `filial_id` (`FilialDep`) → **gráfica
  A nunca vê dados da gráfica B**.
- A **licença** é por inquilino (`licenca.empresa_id`): cada instalação ativa e
  revalida a própria licença no mesmo banco.
- **Tela de ativação (Contrato B)**: pré-preenche o CNPJ instalado ("Instalado
  para: …") e o backend **recusa** ativar com CNPJ diferente do instalado
  (guard em `licensa_contrato_b.ativar`).

Sem `PRINTGEST_EMPRESA_CNPJ` (dev/demo), o sistema opera no modo single-tenant
legado: bootstrap cria a empresa demo `11111111000111`, login é global.

## Migração

`b7c8d9e0f1a2` — `licenca.empresa_id` (backfill pelo CNPJ da linha; sem
casamento, a linha fica NULL = adotável pelo inquilino que ativar) e
unicidades globais → **por filial**: `usuario.login`, `cliente.cpf_cnpj`,
`fornecedor.cpf_cnpj`, `funcionario.cpf`, `produto.codigo`.

## Provisionar uma nova gráfica (checklist)

O script `scripts/provisionar_cliente.ps1` valida (pré-voo) a gráfica no banco
compartilhado:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\provisionar_cliente.ps1 `
    -Cnpj 32667694000101 -RazaoSocial "Gráfica Exemplo Ltda"
```

Ele aponta o env de build para o CNPJ, valida com
`scripts/configurar_auth_neon.py --env-file installer/env.instalacao`
(conexão, migrations, bootstrap do inquilino e estado do admin) e devolve o env
ao estado **universal** (sem CNPJ). Com `-Empacotar`, gera o instalador
universal (`PrintGest-Setup-<versao>.exe`).

Fluxo de entrega: distribua o **mesmo instalador**; na instalação, informe o
CNPJ da gráfica; na primeira execução, a tela de ativação já vem com o CNPJ
pré-preenchido e pede o código da licença (como a chave de produto do Office).

> **Nunca** embuta CNPJ no pacote nem gere instalador por cliente — o CNPJ é
> informado na instalação. Reaproveitar env/instalador entre gráficas é
> exatamente o vazamento documentado em
> `.lgpd/incidents/2026-11-10-vazamento-entre-inquilinos.md`.

## Limites conhecidos (fase 2)

- A credencial do banco é a mesma para todos os inquilinos: o isolamento é
  aplicativo. Quem tiver o `.env` consegue conectar direto no Postgres e ver
  tudo. Evolução recomendada: **RLS por inquilino no Neon** ou um banco por
  gráfica para clientes com exigência maior de segregação (LGPD).
