# Licenciamento do PrintGest ERP

Este documento define **qual licença se aplica a cada parte do repositório**.
Ele não substitui as licenças integrais: `LICENSE` (AGPL-3.0),
`LICENSE-APACHE-2.0` (Apache-2.0) e `LICENSE-COMMERCIAL.md` (referência
`LicenseRef-PrintGest-Commercial`).

## 1. Produto — AGPL-3.0 **ou** licença comercial (dual licensing)

Aplica-se a todo o código de produto, em especial:

- `backend/app/` (API, serviços, modelos, schemas);
- `desktop/printgest/ui/` e `desktop/printgest/main.py`;
- `installer/`, `scripts/` e arquivos de build/distribuição;
- documentação de produto em `docs/`.

Identificador SPDX:

```
SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-PrintGest-Commercial
```

### O que isso significa

- **AGPL-3.0**: você pode usar, modificar e redistribuir o código, inclusive
  comercialmente, desde que cumpra a AGPL. Atenção especial ao **artigo 13**:
  se você modificar o backend e disponibilizá-lo para usuários interagirem pela
  rede, deve oferecer a eles o código-fonte da versão modificada.
- **Licença comercial**: para quem não deseja cumprir essas obrigações (por
  exemplo, ao distribuir uma versão privada ou hospedar um serviço fechado),
  há a opção de licença comercial. Os termos e preços são formalizados à parte;
  `LICENSE-COMMERCIAL.md` descreve apenas a referência SPDX e o contato.

Não é necessário escolher uma das duas para "sempre": a dual licensing permite
distribuir a versão comunitária sob AGPL e negociar a comercial caso a caso.

## 2. Componentes reutilizáveis — Apache-2.0

Os arquivos abaixo são utilitários de domínio/biblioteca, sem acoplamento com a
UI ou com o banco do produto. São licenciados sob **Apache-2.0**:

- `desktop/printgest/core/dominio/` (regras puras de O.S., pagamento e precificação);
- `desktop/printgest/core/dominio.py` (constantes de domínio legadas);
- `backend/app/schemas/common.py` (envelopes de resposta e paginação);
- `backend/app/core/security.py` (hash de senha/token e utilitários gerais).

Identificador SPDX:

```
SPDX-License-Identifier: Apache-2.0
```

Se um desses arquivos for movido ou passar a conter lógica de produto, a
licença deve ser revisada antes do commit.

## 3. Dependências de terceiros

As licenças das dependências **não são alteradas** por este documento.
Resumo em `THIRD_PARTY_NOTICES.md`. Destaques:

- **PySide6 / Qt**: LGPL-3.0 (também GPL-2/3 e comercial). O desktop usa
 ligação dinâmico; mantemos os avisos do Qt no instalador. Isso vale
  independentemente da licença escolhida para o código do PrintGest.
- **psycopg**: LGPL-3.0.
- **certifi**: MPL-2.0.
- **python-multipart**: Apache-2.0 (texto incluído em `LICENSE-APACHE-2.0`).
- **FastAPI, SQLAlchemy, Alembic, pydantic, pydantic-settings**: MIT.
- **uvicorn, httpx**: BSD.

## 4. Como cumprir

1. Mantenha `LICENSE`, `LICENSE-APACHE-2.0`, `NOTICE`,
   `THIRD_PARTY_NOTICES.md` e este arquivo em qualquer redistribuição.
2. Ao modificar código AGPL e expor pela rede, publique o fonte da versão
   modificada (artigo 13 da AGPL).
3. Ao redistribuir os componentes Apache-2.0, preserve `NOTICE` e marque
   alterações nos arquivos modificados (artigo 4 da Apache-2.0).
4. Para LGPL (Qt/psycopg), preserve a possibilidade de relinking e os avisos
   de licença das bibliotecas.

## 5. Alterações nesta política

Mudar a licença de qualquer arquivo exige aprovação explícita e atualização
deste documento, dos cabeçalhos SPDX e do `CHANGELOG.md`.
