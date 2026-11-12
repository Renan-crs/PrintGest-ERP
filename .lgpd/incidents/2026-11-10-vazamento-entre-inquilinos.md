# Incidente: exposição de dados entre inquilinos (banco compartilhado)

**ID**: INC-2026-11-10-01
**Data/hora (T+0)**: 2026-11-10, relato do operador
**Classificação**: incidente de segurança — vazamento de dados pessoais entre
titulares de inquilinos distintos
**Ambiente**: `printg` (Neon, banco compartilhado) — **CONTROLADO/TESTE** (sem
titulares reais expostos; exercício de resposta, não há obrigação de
comunicação à ANPD nesta ocorrência — Res. CD/ANPD 15/2024, art. 5º). Registro
interno mantido por 5 anos (art. 10).

## Descrição
A instalação da "empresa" CNPJ 32.667.694/0001-01 exibia os clientes
cadastrados pela instalação do CNPJ 01.941.569/0001-14. Causa: as duas
instalações receberam o MESMO instalador (mesma credencial Neon embutida em
`installer/env.instalacao`), e o sistema operava sem isolamento por inquilino
no banco compartilhado — ambos caíam na mesma filial.

## Contenção e correção (T+0 → correção)
1. **Diagnóstico**: auditoria somente-leitura do banco + revisão do escopo de
   consultas (`FilialDep`) — isolamento era "um banco por instalação", não
   aplicado quando duas instalações compartilham o banco.
2. **Correção estrutural (multi-tenant)**:
   - Inquilino declarado por instalação: `PRINTGEST_EMPRESA_CNPJ`.
   - Bootstrap garante empresa/filial/admin do inquilino (idempotente).
   - Login escopado ao inquilino (`services/tenants.py`).
   - Licença por inquilino (`licenca.empresa_id`).
   - Unicidades globais → por filial (cliente.cpf_cnpj, fornecedor.cpf_cnpj,
     funcionario.cpf, produto.codigo, usuario.login).
   - Migração `b7c8d9e0f1a2` + suíte `tests/test_multitenant.py` provando que
     o que A cadastra não aparece para B.
3. **Provisionamento por cliente**: instaladores passam a ser gerados com o
   env do inquilino (CNPJ + credenciais); nunca reutilizar o mesmo
   `env.instalacao` entre gráficas.

## Lições / acompanhamento (gaps organizacionais)
- **Credencial de banco compartilhada**: o isolamento aplicativo não impede
  acesso direto ao Postgres com a credencial do `.env`. Evolução recomendada:
  roles/RLS por inquilino no Neon (fase 2) ou banco por gráfica.
- Fluxo de distribuição de instaladores por cliente precisa de checklist
  (CNPJ correto no env + validação `configurar_auth_neon.py` antes de entregar).
- Ferramenta de referência adotada para governança: `goul4rt/lgpd-skills`
  (lgpd-incident-response, Res. 15/2024; lgpd-data-mapping para a fase 2).
