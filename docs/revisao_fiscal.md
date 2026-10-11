# Fiscal — consulta de documentos e contingência (release 0.2)

Documento de entrega do menu **Fiscal** (id `fiscal`), alinhado a
`docs/telas_e_fluxos.md` §1.6, ao PRD v2.0/v2.1 (§1.3, RBAC §5) e ao `schema.sql`
(tabela `documento_fiscal`).

> **Sobre os IDs.** O repositório não contém a lista numerada original desta
> tarefa; os itens abaixo usam a âncora **FS1…FS6** apenas para rastreio e foram
> reconstruídos a partir do escopo recebido. Cruze com a lista original.

---

## 1. Premissas de escopo (adotadas na largada)

1. **A emissão de NF-e/NFC-e exige um gateway fiscal externo** (Focus NFe,
   PlugNotas, eNotas…) que **não** faz parte deste repositório nem do `schema.sql`.
   Sem gateway não há autorização, cancelamento nem carta de correção reais.
   Decisão registrada: entregar o que é possível localmente — **consulta** dos
   documentos persistidos e a **tela de contingência** (aviso + pendências) —
   **sem simular** emissão.
2. **Módulo somente leitura.** Nenhuma rota escreve em `documento_fiscal`; a
   consulta nunca inventa status; o gateway é reportado como **não configurado**
   enquanto a integração não existir.
3. **RBAC alinhado ao menu v2.1.** O item `fiscal` é visível a `caixa`, `gerente`
   e `admin`. Como o RBAC é **não hierárquico** (PRD §5 — `operador` tem rank
   maior que `caixa` mas não vê Fiscal), o router usa a lista de perfis
   (`require_perfis`) e não o rank.
4. **Nada de emissão “falsa”.** A tela de contingência explica a
   indisponibilidade e lista os documentos pendentes (rascunho/processando/
   rejeitado e os marcados em contingência), para reemissão futura.

---

## 2. Componentes

| Arquivo | Papel | Tipo |
| --- | --- | --- |
| `backend/app/schemas/fiscal.py` | **Novo.** `DocumentoFiscalOut` e `ResumoFiscal` | backend (novo) |
| `backend/app/services/fiscal_service.py` | **Novo.** Consulta paginada com filtros, detalhe e resumo (contagens por status/modelo + estado do gateway) | backend (novo) |
| `backend/app/api/fiscal.py` | **Novo.** Router `/v1/fiscal` (somente leitura); registrado em `app/api/__init__.py` | backend (novo) |
| `backend/app/deps.py` | **Compartilhado.** Novo `require_perfis(*niveis)` (RBAC não hierárquico), reusado por Financeiro e Fiscal | backend (compartilhado) |
| `backend/app/api/financeiro.py` | Passa a usar `require_perfis` de `deps` (remove `_perfis` local) | backend (compartilhado) |
| `desktop/printgest/ui/modulos/fiscal.py` | **Novo.** `PaginaDocumentosFiscais`, `PaginaContingencia` e host `PaginaFiscal` | tela (novo) |
| `desktop/printgest/core/api.py` | Métodos `documentos_fiscais`, `documento_fiscal`, `resumo_fiscal` | compartilhado |
| `desktop/printgest/ui/formulario.py` | **Compartilhado.** Novo helper `formatar_data_hora` (data/hora ISO → “DD/MM/AAAA HH:MM”) | compartilhado |
| `desktop/printgest/ui/modulos/__init__.py` | `criar_pagina` mapeia `fiscal` → `PaginaFiscal` e os ids internos `documentos_fiscais`/`contingencia` | compartilhado |
| `desktop/tests/test_fiscal.py` | **Novo.** 6 testes de UI | testes |
| `backend/tests/test_fiscal.py` | **Novo.** 4 testes de backend | testes |
| `docs/evidencias/fiscal/` | Capturas **antes/depois** (1280x720, 1366x768, 1920x1080 × 100/125/150%) | evidência |

**Reuso:** Documents Fiscais herda `PaginaCrud` (grade densa + formulário lateral
+ filtros + estado vazio), porém em modo **consulta** (sem F6/F10). A
Contingência usa `TabelaDensa` + `badge`. O helper de data/hora foi promovido a
`formulario.py` para não duplicar `_dt` entre Fiscal e Financeiro.

---

## 3. Backend (novo) — endpoints e RBAC

| Método | Rota | Perfis | Observação |
| --- | --- | --- | --- |
| `GET` | `/v1/fiscal/documentos` | caixa, gerente, admin | Filtros `q` (nº/chave/cliente), `modelo` (`nfe`/`nfce`), `status_fiscal` e `contingencia`; paginado |
| `GET` | `/v1/fiscal/documentos/{id}` | caixa, gerente, admin | Detalhe; 404 se não existir na filial |
| `GET` | `/v1/fiscal/resumo` | caixa, gerente, admin | Contagens por status/modelo, pendentes, em contingência e estado do gateway |

A listagem usa `outerjoin` em `Cliente` para trazer `cliente_nome`; a busca por
número usa `cast(numero, String)`. O resumo reporta
`gateway_configurado = false` (não há integração) e `gateway_disponivel = false`.

---

## 4. Telas (front-end)

### 4.1 Host `PaginaFiscal`

- Barra de título **“Fiscal”** + alternador de sub-abas (`chaveRapida`, um
  checkado por vez), no mesmo padrão de Financeiro/Projetos.
- Sub-abas: **Documentos Fiscais** e **Contingência** (perfis do menu v2.1).
- Troca de aba remove/reinsere o widget central (sem `QStackedWidget`).

### 4.2 Documentos Fiscais (`PaginaDocumentosFiscais`) — consulta

- Grade densa: **Nº · Modelo · Número · Série · Status · Valor · Chave de
  Acesso · Contingência · Emitido em**. Busca por número/chave/cliente e chips
  por status (Todas/Rascunhos/Processando/Autorizados/Rejeitados/Cancelados).
- Formulário lateral **sempre preenchido a partir da seleção** e desabilitado:
  Documento, Autorização (valor, chave, protocolo, emitido em),
  Rastreabilidade (cliente, vínculo com Venda balcão/O.S., contingência,
  XML/DANFE) e Mensagem de retorno.
- **Sem cadastro**: os botões Novo/Salvar/Cancelar ficam ocultos e nenhum atalho
  F6/F10 é instalado.
- Estado vazio: “Nenhum documento fiscal encontrado para os filtros atuais.”

### 4.3 Contingência (`PaginaContingencia`)

- Badges **GATEWAY INDISPONÍVEL/DISPONÍVEL** e **Pendências: N**; cartão de
  aviso com a mensagem do gateway e as contagens (total, autorizados,
  rejeitados, em contingência); botão **Atualizar**.
- Grade de **pendências** (rascunho/processando/rejeitado/em contingência):
  Nº · Modelo · Número · Status · Contingência · Valor · Emitido em, com estado
  vazio próprio.
- Nada é reenviado automaticamente: a tela é o ponto de acompanhamento até a
  integração do gateway.

---

## 5. Requisitos de aceite (mesmo padrão dos Cadastros/Projetos/Financeiro)

| ID | Requisito | Status | Observação |
| --- | --- | --- | --- |
| FS1 | Sem texto cortado sem tooltip | ✅ | Títulos usam `ElideLabel`; a grade elide com tooltip nativo |
| FS2 | Sem **scroll horizontal** e no máx. 1 vertical | ✅ | Ver §6 — `h=0` nas 27 combinações |
| FS3 | Estado vazio nas listas | ✅ | Documentos e Contingência com estado vazio próprio |
| FS4 | Operação só por teclado (Tab/Esc) | ✅ | Consulta; sem atalhos de escrita conflitantes |
| FS5 | Sem conflito de atalhos globais | ✅ | Fiscal não instala F6/F10 (os globais seguem intactos) |
| FS6 | RBAC preservado e reforçado | ✅ | Ver §8 |

---

## 6. Layout / testes

- Suíte **desktop**: **212 passed**, incluindo `desktop/tests/test_fiscal.py`
  (novo, 6 testes).
- Suíte **backend**: **107 passed**, incluindo `backend/tests/test_fiscal.py`
  (novo, 4 testes).
- Verificação de layout sem imagens (`.dev/check_layout_fiscal.py`): mede as
  scrollbars reais de `documentos`, `contingencia` e do `host` em
  1280x720 / 1366x768 / 1920x1080 × 100/125/150%. Resultado: **`h_tab=0` e
  `h_form=0` em todas as 27 combinações**.

---

## 7. Screenshots (antes/depois)

Versionados em `docs/evidencias/fiscal/`:

```
antes/    fiscal_antes_<res>_<escala>.png         (9)  — placeholder "em construção"
depois/   fiscal_documentos_<res>_<escala>.png    (9)  — consulta de documentos
depois/   fiscal_contingencia_<res>_<escala>.png  (9)  — aviso + pendências
```

Resoluções: `1280x720`, `1366x768`, `1920x1080`; escalas: `100`, `125`, `150`.
Geradas por `.dev/snapshot_fiscal.py` (documentos com nomes longos, rejeição,
contingência e resumo com pendências).

---

## 8. RBAC e regressão

- **Menu v2.1:** item `fiscal` visível a `admin`, `gerente` e `caixa`
  (inalterado). O backend reforça com `403` via `require_perfis(...)`.
- **Não hierárquico:** `operador` **não** acessa `/v1/fiscal/*`, ainda que tenha
  rank acima de `caixa` (testado).
- **Refatoração sem regressão:** `require_perfis` centraliza a regra usada por
  Financeiro e Fiscal em `deps.py`; as suítes de Financeiro seguem verdes.
- **Sem regressão** no restante do sistema: a suíte completa segue verde.
  Nenhum endpoint existente teve contrato alterado.

---

## 9. Fora de escopo / pendências (com motivo)

1. **Emissão de NF-e/NFC-e, cancelamento e carta de correção:** dependem de
   gateway fiscal externo e de certificado válido — inexistentes no repositório.
   A interface está pronta para a consulta; a emissão entra quando o gateway for
   integrado.
2. **Configuração do gateway/certificado (A1):** não há tabela nem spec para
   guardar tokens/SENHA do provedor; dependeria de migração e de um cofre de
   segredos.
3. **Reenvio/reprocessamento em lote:** hoje é acompanhamento; o disparo só faz
   sentido com o gateway integrado.
4. **DANFE/XML por download:** os caminhos (`xml_path`/`danfe_path`) são exibidos,
   mas abrir/baixar o arquivo depende de armazenamento e serviço inexistentes.
