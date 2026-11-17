# Emissão fiscal via API de terceiro (NF-e / NFC-e / NFS-e)

O PrintGest **não transmite nem assina** documentos fiscais. Ele monta o payload
a partir de uma venda de balcão ou O.S., envia a um **gateway fiscal de terceiro**
configurado na instalação e acompanha o retorno (chave de acesso, protocolo,
status). Isso vale para:

| Modelo | Origem típica | Quem emite |
|---|---|---|
| `nfce` | Venda de balcão (PDV) | Gateway (SEFAZ via provedor) |
| `nfe` | Venda/OS | Gateway (SEFAZ via provedor) |
| `nfse` | O.S. (serviços) | Gateway (prefeitura via provedor) |

## Configuração

Todas as variáveis são lidas pelo `Settings` do backend com prefixo
`PRINTGEST_` (arquivo `.env` da instalação — **nunca commitar credenciais**):

| Variável | Default | Finalidade |
|---|---|---|
| `PRINTGEST_FISCAL_GATEWAY_URL` | `""` | Base URL do provedor. Vazia = emissão desativada (consulta segue ativa). |
| `PRINTGEST_FISCAL_GATEWAY_TOKEN` | `""` | Credencial enviada no cabeçalho. |
| `PRINTGEST_FISCAL_GATEWAY_AUTH_HEADER` | `Authorization` | Nome do cabeçalho de autenticação. |
| `PRINTGEST_FISCAL_GATEWAY_AUTH_PREFIX` | `Bearer ` | Prefixo do valor do cabeçalho. |
| `PRINTGEST_FISCAL_GATEWAY_TIMEOUT_SEGUNDOS` | `15` | Timeout HTTP. |
| `PRINTGEST_FISCAL_GATEWAY_AMBIENTE` | `homologacao` | `homologacao` ou `producao` (produção exige HTTPS). |
| `PRINTGEST_FISCAL_GATEWAY_EMITIR_PATH` | `/documentos` | Rota POST de emissão. |
| `PRINTGEST_FISCAL_GATEWAY_CONSULTAR_PATH` | `/documentos/{id}` | Rota GET de consulta. |
| `PRINTGEST_FISCAL_GATEWAY_CANCELAR_PATH` | `/documentos/{id}/cancelamento` | Rota POST de cancelamento. |
| `PRINTGEST_FISCAL_GATEWAY_HEALTH_PATH` | `/health` | Rota GET de disponibilidade. |

Os caminhos são templates: `{id}` é preenchido com o `gateway_id` retornado na
emissão. Qualquer provedor REST pode ser adaptado apenas com variáveis de
ambiente — sem mudança de código.

### Adaptando a um provedor específico

1. Aponte `FISCAL_GATEWAY_URL` para a base da API do provedor.
2. Ajuste os `_PATH` conforme a documentação dele (ex.: Focus NFe usa
   `/v2/nfce`, `/v2/nfce/{ref}/status`, `/v2/nfce/{ref}/cancelamento`).
3. Configure o cabeçalho/prefixo de autenticação (alguns provedores usam
   `X-API-Key` com prefixo vazio).
4. O retorno é normalizado em `fiscal_gateway.GatewayResult`. Campos aceitos:
   `id`/`ref`/`gateway_id`, `status` (vários aliases), `chave_acesso`/`chaveNFe`,
   `numero`, `serie`, `protocolo`, `xml_url`/`xml`, `danfe_url`/`danfe`, `mensagem`.

## Endpoints

| Método | Rota | Ação |
|---|---|---|
| `GET` | `/v1/fiscal/resumo` | Panorama + estado do gateway (sem credenciais). |
| `GET` | `/v1/fiscal/gateway` | Estado do gateway. |
| `GET` | `/v1/fiscal/documentos` | Lista documentos (filtros: modelo, status, contingência, q). |
| `POST` | `/v1/fiscal/documentos/emitir` | Emite via gateway a partir de venda ou O.S. |
| `POST` | `/v1/fiscal/documentos/{id}/consultar` | Consulta status no gateway. |
| `POST` | `/v1/fiscal/documentos/{id}/cancelar` | Cancela no gateway (com motivo). |
| `GET` | `/v1/fiscal/documentos/{id}/eventos` | Trilha de auditoria. |

Corpo de emissão:

```json
{
  "modelo": "nfce",
  "venda_balcao_id": 123,
  "contingencia": false
}
```

Exatamente uma origem (`venda_balcao_id` **ou** `ordem_servico_id`) é obrigatória.
A emissão é idempotente para documentos já `processando`/`autorizados`.

## Comportamento em falha

- Falha de transporte/HTTP do gateway → documento `rejeitado` (ou
  `contingenciado` quando `contingencia=true`) e evento `emissao_falhou` com a
  mensagem. A venda/O.S. **não é afetada** — a emissão é independente.
- Credenciais nunca são gravadas: `GatewayResult` e os eventos de auditoria
  passam por sanitização (`token`, `api_key`, `senha`, `authorization`, etc.
  viram `***`).
- Isolamento: documentos e eventos são sempre filtrados por `filial_id`.

## Migration

`a3b4c5d6e7f8` — adiciona `nfse` ao enum `modelo_fiscal`, colunas de gateway/
ambiente/consulta/cancelamento em `documento_fiscal` e cria `fiscal_evento`.
Aplique com `alembic upgrade head` em cada instalação.
