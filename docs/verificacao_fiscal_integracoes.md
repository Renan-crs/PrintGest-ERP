# Verificação das chamadas API ↔ endpoints — Fiscal e Integrações

Verificado em 19/11/2026.

## Contrato conferido

Paths/verbos e nomes de chave conferem: `modelo`, `contingencia`,
`venda_balcao_id`, `ordem_servico_id`, `motivo`, `credencial` (cofre) — todos
presentes nos schemas do backend. Nenhuma rota chamada pela UI é inexistente.
A emissão chama gateway real (ou mock nos testes) e **não simula sucesso**;
`venda.documento_fiscal_id` é gravado pelo `fiscal_service`.

## Bugs encontrados e corrigidos

| # | Sev. | Achado | Correção |
|---|---|---|---|
| 1 | 🔴 | **Tela de Integrações não listava nada em produção**: backend devolve `{data,total}` sem `meta`, e `Api._paginar` exigia `corpo["meta"]` → `KeyError: 'meta'`. O "salvo" aparecia mesmo com a lista vazia. | `ListaIntegracoes` passou a incluir `meta` (mantendo `total` no topo por compatibilidade); serviço preenche. |
| 2 | 🔴 | **RBAC fiscal invertido nos atalhos**: `documentos_fiscais`/`contingencia` usavam `nivel="operador"` (hierárquico) → OPERADOR abria e levava 403; CAIXA era barrado embora autorizado. | Ids passaram a declarar `niveis=["caixa","gerente","admin"]`, como `require_perfis`. |
| 3 | 🔴 | **Gateway cadastrado em Integrações era cosmético**: `configurado`/`_url` liam só `.env`, então emissão/consulta davam 503 mesmo com integração fiscal ativa. | `FiscalGateway.base_url` prioriza `integracao.base_url`; `consultar` usa `_gateway(db, filial)`; `gateway_info`/`resumo`/rota `/gateway` passam db+filial. Cache de disponibilidade agora é por `(filial, URL)` (isolamento multi-tenant). |
| 4 | 🟠 | `eventos_integracao` esperava envelope `data`, mas a rota devolve lista crua → `TypeError`. | Cliente aceita lista crua e envelope. |
| 5 | 🟠 | O PDV orientava "Consulte Fiscal > Documentos para tentar novamente", mas a tela não tinha como reemitir. | Botão **Reemitir** (desabilitado em modo leitura) envia `modelo` + origem; backend é idempotente para autorizado/processando. |
| 6 | 🟠 | Status HTTP 401/403/423/409 descartados em Fiscal/Integrações (callbacks de 1 parâmetro); "Testar" ativo em modo leitura. | Callbacks aceitam status; títulos "Sessão encerrada"/"Modo leitura"; teste bloqueado em leitura. |
| 7 | 🟡 | Sanitização de segredos incompleta: chaves exatas (`access_token` etc.) e mensagens livres do gateway iam para auditoria sem máscara. | Correspondência por substring + regex para `Bearer`/`token=`/`chave_privada=` em mensagens e `detalhes`. |
| 8 | 🟡 | Contador de pendências da UI incluía `contingenciado`; backend não. | Backend passou a contar contingência como pendente. |
| 9 | 🟡 | Mensagens contraditórias sobre onde configurar o gateway. | Unificadas: Configurações > Integrações **ou** `PRINTGEST_FISCAL_GATEWAY_URL`. |

## Ressalvas (não corrigidas — exigiriam mudança de schema/decisão de produto)

- `OrdemServico` não tem coluna `documento_fiscal_id`: NFS-e emitida por O.S.
  não é vinculada de volta à O.S. Adicionar a coluna exigiria migration em
  produção (fora do escopo autorizado desta verificação).
- A tela de Integrações não expõe exclusão, eventos/auditoria nem remoção de
  segredo — os endpoints existem (`DELETE`, `GET /{id}/eventos`), mas não há
  botões. Sync real fica em `/v1/plataforma/sync/*`, desconectado da tela.
- `PaginaFiscal` recebe `nivel` mas não o usa para ocultar abas; o acesso é
  controlado pelo menu/`pode_abrir`.

## Validação

- Backend: **413 passed** (4 novos de contrato Fiscal/Integrações).
- Desktop: **445 passed, 4 xfailed** (5 novos: reemissão, envelope, eventos, RBAC).
- Neon: head Alembic `a0b1c2d3e4f5` — nenhuma migration nova.
