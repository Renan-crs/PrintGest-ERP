# Avisos de terceiros

Este arquivo é informativo. Os textos integrais das licenças acompanham os
pacotes instalados e/ou os arquivos do repositório. A licença do PrintGest
(`LICENSE`, `LICENSE-APACHE-2.0`) **não substitui** a licença destas obras.

## Backend (`backend/requirements.txt`)

| Dependência | Licença | Observações |
|---|---|---|
| FastAPI | MIT | Framework HTTP |
| Uvicorn | BSD-3-Clause | Servidor ASGI |
| SQLAlchemy | MIT | ORM |
| Alembic | MIT | Migrations |
| psycopg | LGPL-3.0-only | Driver PostgreSQL; link dinâmico |
| pydantic / pydantic-settings | MIT | Validação/configuração |
| httpx | BSD | Cliente HTTP |
| python-multipart | Apache-2.0 | Upload multipart; texto em `LICENSE-APACHE-2.0` |
| certifi | MPL-2.0 | CA bundle |

## Desktop (`desktop/requirements.txt`)

| Dependência | Licença | Observações |
|---|---|---|
| PySide6 / Qt | LGPL-3.0-only (ou GPL-2/3, ou comercial) | Usado via **ligação dinâmica**. O instalador deve preservar os avisos do Qt e permitir relinking, conforme a LGPL-3.0 |
| httpx | BSD | Cliente HTTP usado pelo `Api` |
| certifi | MPL-2.0 | CA bundle |

## Banco e infraestrutura

- **PostgreSQL / Neon**: o sistema usa PostgreSQL em nuvem; nenhum binário do
  PostgreSQL é distribuído no instalador (removido na v0.3.4).
- Não há código de terceiros copiado para `backend/app/` ou
  `desktop/printgest/` — apenas dependências declaradas nos `requirements`.

## Obrigações ao redistribuir

1. Inclua `LICENSE`, `LICENSE-APACHE-2.0`, `NOTICE`, `LICENSE-COMMERCIAL.md`,
   `LICENCIAMENTO.md` e este arquivo no pacote.
2. Preserve os avisos do Qt/PySide6 e dos módulos LGPL/MPL.
3. Se modificar componentes Apache-2.0, marque as alterações e mantenha `NOTICE`.
