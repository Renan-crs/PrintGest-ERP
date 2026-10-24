# Erro na ativacao - Contrato C / SISTEMA_SEM_CREDENCIAL

Data: 2026-10-23
Sistema: PrintGest ERP
Ambiente: Instalacao em maquina de testes (instalador gerado)

## Sintoma observado
Na tela de serial/licenciamento (ativacao), ao tentar ativar com a chave de produto:

```text
2026-10-23 19:28:51,946 INFO [..] httpx: HTTP Request: POST https://redgest-system.onrender.com/api/v1/licencas-software/validar/ "HTTP/1.1 403 Forbidden"
2026-10-23 19:28:51,948 INFO [..] printgest: POST /v1/licenca/ativar -> 400 (688.2 ms)
INFO:     127.0.0.1:65402 - "POST /v1/licenca/ativar HTTP/1.1" 400 Bad Request
```

A tela retorna erro de ativacao. A licenca local nao foi revogada (comportamento correto).

## Configuracao atual (backend/.env)
```env
PRINTGEST_REDGEST_URL=https://redgest-system.onrender.com
PRINTGEST_REDGEST_SISTEMA=printgest
PRINTGEST_REDGEST_API_KEY=<presente>
PRINTGEST_REDGEST_CONTRATO=c
```

## Teste realizado diretamente no RedGest
**Contrato C - endpoint `/api/v1/licencas-software/validar/`**
- Requisicao assinada com HMAC-SHA256 usando a `PRINTGEST_REDGEST_API_KEY` presente no .env
- Resultado: `403 Forbidden`
- Corpo: `{"detail": "Sistema sem credencial de integracao configurada.", "codigo": "SISTEMA_SEM_CREDENCIAL"}`

Conclusao: O sistema `printgest` nao esta provisionado no RedGest com a API key informada. Ou a API key esta incorreta para esse sistema, ou o sistema nao tem credencial configurada.

**Contrato B - endpoint `/api/v1/licencas/{uuid}/ativar/`**
- POST com corpo `{cnpj, codigo_licenca, hardware_profile}` e `Idempotency-Key`
- Codigo falso: `00000000-0000-0000-0000-000000000000`
- Resultado: `400 Bad Request`
- Corpo: `{"detail": "Licenca nao encontrada."}`
- Conclusao: Endpoint acessivel, **nao exige** a API key do sistema `printgest`. A autenticacao e por CNPJ + codigo da licenca.

## Solucao
Verificar com o RedGest qual foi o formato emitido:

1. **Se foi emitida CHAVE DE PRODUTO (`XXXX-XXXX-XXXX-XXXX`) - Contrato C**
   - Necessario provisionar/configurar a credencial de integracao para o sistema `printgest` no RedGest com a API key correta
   - Atualizar `PRINTGEST_REDGEST_API_KEY` no `.env` do PrintGestAPI com a chave correta e reiniciar o servico
   - Manter `PRINTGEST_REDGEST_CONTRATO=c`

2. **Se foi emitido CNPJ + CODIGO DA LICENCA (UUID) - Contrato B (recomendado com base nos testes)**
   - Alterar `PRINTGEST_REDGEST_CONTRATO=b` no `.env` do PrintGestAPI
   - Reiniciar o PrintGestAPI
   - A tela de ativacao passara a solicitar CNPJ + Codigo da Licenca
   - Ativar com os dados fornecidos pelo RedGest

## Observacao
O backend trata corretamente o `403` do RedGest (nao revoga licenca local) e converte para `400` na resposta da API para exibicao na tela de ativacao.
