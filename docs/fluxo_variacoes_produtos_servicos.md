# Fluxo de variações de produtos e serviços — guia de desenvolvimento

**Status:** proposta para aprovação (documento de apoio, nenhum código alterado).
**Data:** 22/11/2026 · **Baseline:** v0.5.29 (`1c64f40`), Alembic head `d4e5f6a7b8c9`.

---

## 1. Objetivo

Documentar, de forma executável, como o PrintGest deve tratar **variações de
produtos e de serviços**, usando o caso real de uma gráfica:

| Serviço "Impressão" conforme o substrato | Preço de venda |
|---|---:|
| Sulfite | R$ 1,00 |
| Papel alto alvura | R$ 8,00 |
| Fotográfico | R$ 10,00 |

A pergunta que este documento responde: **como representar "Impressão" com seus
três preços sem criar um "serviço com estoque" e sem perder o rastreio por
SKU?** Hoje o sistema **rejeita exatamente esse caso** (item 3.4).

---

## 2. Estado atual da implementação (v0.5.29)

### 2.1 Modelo de dados

Tudo vive na tabela única `produto` (`backend/app/models/cadastros.py:217-310`):

| Campo | Papel na variação |
|---|---|
| `tipo` | `produto` ou `servico` (`models/enums.py:35-37`) |
| `produto_pai_id` | aponta para o pai; FK composta `(produto_pai_id, filial_id)` garante mesmo inquilino |
| `sku`, `uuid`, `codigo`, `codigo_barras` | identidade; `sku` e `codigo` únicos **por filial**, `uuid` global |
| `atrib_tamanho`, `atrib_marca`, `atrib_cor` | eixos de variação (domínio fechado na UI) |
| `controla_estoque`, `preco_custo`, `preco_venda`, `estoque_minimo` | dado econômico por variante |
| `produto_estoque` | linha de saldo **por variante** (criada com saldo 0) |

Restrições relevantes:

- `ck_produto_servico_sem_estoque` — `tipo='servico' ⇒ controla_estoque=false`;
- `uq_produto_variante_atributos` — UNIQUE por
  `(filial, pai, COALESCE(tamanho), COALESCE(marca), COALESCE(cor))`;
- `uq_produto_filial_sku`, `uq_produto_filial_codigo`, `uq_produto_uuid`,
  `uq_produto_codigo_barras`;
- `campos_immutaveis = {sku, uuid, produto_pai_id, tipo}` no PUT — identidade da
  variante não pode ser trocada (`api/cadastros.py:201`).

### 2.2 Geração (`backend/app/services/variacao_service.py`)

`gerar()` (linhas 33-194):

1. valida pai existente **na filial do usuário** (404);
2. **rejeita pai `servico` com 400** — `"Serviços não possuem variações com estoque."` (linhas 39-44);
3. exige ao menos um atributo por linha (422);
4. monta `sku = prefixo-TAM-MARCA-COR` com `_slug()` (remove acentos/pontuação,
   caixa alta, máximo 8 caracteres por segmento — linhas 28-30);
5. cria filha com `tipo=PRODUTO`, `controla_estoque=True` (linhas 152-154), uma
   linha em `produto_estoque` com saldo 0 (linhas 165-169) e evento de sync
   `mestre:produto` (linhas 171-185);
6. preço: `variacao.preco_venda` se informado, senão herda do pai (linhas 156-160);
7. idempotente por SKU: reativa filha excluída e recria a linha de estoque se
   faltando (linhas 92-127); `IntegrityError` → 409 com rollback.

`propagar_preco()` (linhas 197-234) **sobrescreve** `preco_venda`, `preco_custo` e
`estoque_minimo` de todas as filhas ativas com os valores do pai.

`buscar_por_sku()` (linhas 237-258) casa `sku`/`uuid`/`codigo_barras`/`codigo`,
mas filtra **somente** `Produto.tipo == PRODUTO` e `ativo=True`.

### 2.3 API e UI

- `POST /v1/produtos/variacoes/gerar` — `api/cadastros.py:206-232`; exige
  OPERADOR para gerar e **GERENTE+ se qualquer `preco_venda` for enviado**.
- `POST /v1/produtos/{id}/propagar-preco` — GERENTE+ (`api/cadastros.py:235-252`).
- `GET /v1/produtos?somente_variantes=true` — filtro no banco (`api/cadastros.py:175-179`).
- `GET /v1/produtos/buscar-sku/{termo}` (OPERADOR) e o espelho
  `GET /v1/pdv/produtos/buscar-sku/{termo}` (CAIXA) — ambos usam
  `buscar_por_sku()`.
- `VariacaoIn` (`schemas/cadastros.py:187-210`) aceita
  `tamanho | marca | cor | preco_venda | codigo_barras`.
- Diálogo `DialogoVariacoes` (`desktop/.../dialogo_variacoes.py`) mostra o
  preview do SKU e edita os três atributos + preço + barras. O botão "Gerar
  variações" aparece em `produtos.py:77-94`, habilitado para qualquer registro
  salvo (`_atualizar_botao_variacoes`, linhas 336-345) — o bloqueio hoje é
  **server-side**, não visual.
- PDV: `venda_balcao.py:326-360` carrega `/v1/pdv/produtos` (teto 5000) e indexa
  `codigo`, `sku` e `codigo_barras` em `_por_codigo`; fallback ao servidor em
  `_buscar_sku_no_servidor()` (linhas 428+).
- OS: itens carregam `produto_id`, `valor_unitario` e `tipo`
  (`services/os_service.py:60-73`); serviços não geram movimentação de estoque.

---

## 3. Diagnóstico: por que o exemplo da gráfica não funciona hoje

| # | Gap | Evidência | Consequência prática |
|---|---|---|---|
| 3.1 | Pai `servico` é recusado | `variacao_service.py:39-44` | Não dá para criar "Impressão" com 3 preços |
| 3.2 | Filha é sempre `tipo=PRODUTO` com estoque | `variacao_service.py:152-154,165-169` | Mesmo que o pai fosse aceito, geraria "serviço com estoque" — exatamente o bug corrigido em v0.5.26 (`docs/verificacao_produtos_variacoes.md:35`) |
| 3.3 | Não existe eixo "material/substrato" | `VariacaoIn` só tem tamanho/marca/cor | "Sulfite / Alto alvura / Fotográfico" só caberia como `marca` (gambiarra semântica) |
| 3.4 | Busca por SKU ignora serviços | `variacao_service.py:249` | Mesmo criadas, as filhas-serviço não seriam encontradas pelo coletor do PDV |
| 3.5 | Propagação sobrescreve preços distintos | `variacao_service.py:213-216` | Um clique em "Propagar preço" transformaria R$ 1/8/10 em um único preço |
| 3.6 | Sem Distinção visual no cadastro | `produtos.py:336-345` | Operador não é avisado de que variações de serviço têm regras diferentes |

** workaround disponível hoje (sem código):** cadastrar três serviços independentes —
"Impressão sulfite", "Impressão alto alvura", "Impressão fotográfico". Funciona
para faturar, mas não agrupa os preços sob um pai, não mantém nomenclatura
consistente, não oferece propagação controlada e atrapalha relatórios. É a
solução temporária enquanto a funcionalidade não é entregue.

---

## 4. Modelo recomendado: duas trilhas explícitas

A mesma tabela `produto` continua servindo os dois casos; o que muda é a **regra
de herança do pai para a filha**:

| | **Trilha A — Produto (já existe)** | **Trilha B — Serviço (nova)** |
|---|---|---|
| Pai | `tipo=produto`, `controla_estoque=true` | `tipo=servico`, `controla_estoque=false` |
| Filha | `tipo=produto`, `controla_estoque=true` | `tipo=servico`, `controla_estoque=false` |
| `produto_estoque` | linha própria, saldo inicial 0 | **nenhuma linha** |
| Baixa de estoque | sim, `UPDATE ... WHERE saldo >= qtd` (409 se insuficiente) | **nunca** |
| Preço | por variante; herda do pai se omitido | por variante; **obrigatório/quase sempre distinto** |
| SKU | `prefixo-TAM-MARCA-COR` | `prefixo-MATERIAL[-TAM]` |
| Seleção | PDV (bip/código) e OS | PDV (bip/código) e OS — **sem baixa** |
| Propagação de preço | permitida (GERENTE+) | **desabilitada** (preço é a própria variação) |
| Sync | evento `mestre:produto` por filha | evento `mestre:produto` por filha (preço replicado) |

**Invariante central:** *nenhuma filha de serviço poderá, em hipótese alguma,
ter `controla_estoque=true` ou linha em `produto_estoque`.* O
`CHECK ck_produto_servico_sem_estoque` já garante metade disso no banco; a
outra metade é não criar a linha de estoque no gerador.

### 4.1 Eixo de variação para serviços

Para o exemplo, o eixo natural é o **substrato/material**. Duas opções:

- **Curto prazo (sem migration):** usar `atrib_marca` como "material" e apenas
  reler o rótulo na UI ("Material / substrato"). Custo zero, mas semântica
  suja: o campo continua se chamando `marca` na API, nos eventos de sync e nos
  relatórios.
- **Recomendado:** novo campo `atrib_material` (String 60) em `Produto` e em
  `VariacaoIn`, incluído na UNIQUE `uq_produto_variante_atributos`. É uma
  migration pequena, compatível com os dados atuais (coluna nova NULL ⇒ o
  conjunto de unicidade existente não muda). Mantém `tamanho/marca/cor` intactos
  para produtos.

**Recomendação deste documento:** adotar `atrib_material` já na primeira
entrega, evitando retrabalho de renomear o campo depois. A migration segue a
regra do projeto: **execução em branch de backup, com aprovação explícita
antes de tocar em produção.**

---

## 5. Decisões de produto a confirmar antes de codar

| # | Decisão | Recomendação | Por quê |
|---|---|---|---|
| D1 | Eixo do serviço | Novo `atrib_material` (§4.1) | Semântica correta; evita "marca" significando papel |
| D2 | Preço obrigatório na filha-serviço | Obrigatório (422 se faltar) | No exemplo os 3 preços são diferentes; herdar do pai quase sempre seria erro. Para produtos, manter herança (retrocompatibilidade) |
| D3 | Propagação de preço | Botão oculto para pai `servico` | Sobrescreveria R$ 1/8/10. Se no futuro fizer sentido, introduzir `preco_fixo` por filha e pular as fixas |
| D4 | Onde selecionar | PDV **e** OS | Impressão é vendida no balcão e entra em O.S.; os dois fluxos usam o mesmo catálogo |
| D5 | Pai com filhas já existentes | Mesma idempotência de hoje (SKU duplicado → reativa) | Evita duplicatas e mantém o comportamento conhecido |
| D6 | Código fiscal da variante | Mesmo código do pai (a variante não muda a natureza do serviço) | Substrato é atributo comercial, não item de serviço distinto para a prefeitura |
| D7 | Rótulo no cadastro | Mostrar `tipo=SERVICO` + aviso "sem estoque" no diálogo de variações | Reduz o risco de operador esperar baixa de estoque |

---

## 6. Plano de implementação (por fases)

### Fase 1 — Modelo e regra de domínio

1. `backend/app/models/cadastros.py`: acrescentar `atrib_material: Mapped[str | None]`
   (String 60) e incluí-lo no índice `uq_produto_variante_atributos` (usar
   `text("COALESCE(atrib_material, '')")` na lista de colunas).
2. Migration Alembic nova (head após `d4e5f6a7b8c9`): `ADD COLUMN atrib_material`,
   `DROP INDEX uq_produto_variante_atributos`, recriá-lo com a coluna nova.
   Pré-checagem: 0 duplicatas; **backup branch antes de aplicar em produção**.
3. `backend/app/schemas/cadastros.py`: `ProdutoBase.atrib_material` e
   `VariacaoIn.material` (mesmo validador de "não vazio" dos demais atributos).
4. Atualizar o validador `_ao_menos_um_atributo` para considerar `material`.

### Fase 2 — Gerador com duas trilhas

Arquivo: `backend/app/services/variacao_service.py`

1. Substituir o bloqueio das linhas 39-44 por uma decisão de trilha:
   ```python
   eh_servico = pai.tipo == TipoProduto.SERVICO
   tipo_filha = TipoProduto.SERVICO if eh_servico else TipoProduto.PRODUTO
   controla_estoque = not eh_servico
   ```
   Mantém os 404 (pai inexistente / outra filial) e a recusa de pai inativo.
2. Atributos passam a incluir `material`; ordem canônica
   `(material, tamanho, marca, cor)` para **SKU e rótulo** (produtos existentes
   têm `material=NULL`, então seus SKUs não mudam).
3. Na criação da filha (linhas 139-169):
   - `tipo=tipo_filha`, `controla_estoque=controla_estoque`;
   - **criar `ProdutoEstoque` somente quando `controla_estoque` for True**;
   - na reativação (linhas 95-109), o mesmo `if` — nunca criar estoque para serviço.
4. Preço (D2): se `eh_servico` e `variacao.preco_venda is None` → 422
   `"Variações de serviço exigem preço de venda explícito."`
5. `propagar_preco()` (D3): se `pai.tipo == SERVICO`, não alterar nada e
   devolver 0 (a UI já esconde o botão); alternativamente 400 com mensagem
   orientando.
6. `buscar_por_sku()` (linha 249): remover o filtro
   `Produto.tipo == TipoProduto.PRODUTO` — passam a ser encontráveis produtos
   **e** serviços ativos. O filtro `ativo=True` e o escopo por `filial_id`
   permanecem.

> Segurança: como o `CHECK` do banco impede `servico + controla_estoque`, um
> bug no gerador que tentasse criar estoque para serviço estouraria em 500 —
> o teste de mutação (§9) garante que isso continua sendo detectado.

### Fase 3 — API e contrato

Endpoints existentes são reaproveitados; nenhuma rota nova é necessária:

| Endpoint | Ajuste |
|---|---|
| `POST /v1/produtos/variacoes/gerar` | aceita `material` no payload; mensagens de erro específicas para serviço |
| `GET /v1/produtos?somente_variantes=true` | sem mudança — inclui filhas-serviço |
| `POST /v1/produtos/{id}/propagar-preco` | devolve 0 para pai serviço (D3) |
| `GET /v1/produtos/buscar-sku/{termo}` | passa a encontrar serviços |
| `GET /v1/pdv/produtos/buscar-sku/{termo}` | idem (mesmo serviço) |
| `GET /v1/pdv/produtos` | sem mudança — já devolve todos os tipos |

RBAC inalterado: GERENTE+ para definir preço na geração e para propagação.

### Fase 4 — Desktop

1. `dialogo_variacoes.py`:
   - novo combo/ campo "Material / substrato", com domínio sugerido
     `["Sulfite", "Alto alvura", "Fotográfico"]` **quando o pai for serviço**;
   - para produto, manter Tamanho/Marca/Cor;
   - aviso no topo para serviço: *"Variações de serviço não controlam estoque;
     cada preço é independente."*;
   - preview do SKU já existente passa a incluir o material.
2. `produtos.py::_atualizar_botao_variacoes` (linhas 336-345): manter habilitado
   para serviço, mas trocar o tooltip do botão "Propagar preço" para
   *"Não disponível para serviços — o preço é definido por variante."* e
   desabilitá-lo quando `tipo == 'servico'`.
3. `venda_balcao.py`: nenhuma mudança no cache — `_por_codigo` já indexa `sku`
   (linha 352) e o catálogo `/v1/pdv/produtos` traz as filhas-serviço. Confirmar
   que `_adicionar_produto` não tenta reservar estoque para serviço (já é o
   comportamento do `venda_service`).
4. `grade_itens.py` / `os.py`: ao selecionar uma variante-serviço, preencher
   `valor_unitario` com `preco_venda` da filha. Nenhuma baixa de estoque.

### Fase 5 — Validação e release

Ver §9 e §10. Release com tag, instalador, GitHub Release e `CHANGELOG.md`,
seguindo o ritual do projeto.

---

## 7. Ex concreto: payload, SKU e nomes

### 7.1 Cadastro do pai

```json
POST /v1/produtos
{
  "codigo": "IMP",
  "nome": "Impressão",
  "tipo": "servico",
  "controla_estoque": false,
  "unidade": "un",
  "preco_venda": 1.00
}
```

O preço do pai funciona como *preço de referência* (sulfite). As variantes
carregam os preços reais.

### 7.2 Geração das três variações

```json
POST /v1/produtos/variacoes/gerar
{
  "produto_pai_id": 123,
  "prefixo_sku": "IMP",
  "variacoes": [
    {"material": "Sulfite",       "preco_venda": 1.00},
    {"material": "Alto alvura",   "preco_venda": 8.00},
    {"material": "Fotográfico",   "preco_venda": 10.00}
  ]
}
```

Resposta (201): três registros com `tipo="servico"`, `controla_estoque=false`,
`produto_pai_id=123`, preços 1/8/10 e nenhuma linha em `produto_estoque`.

### 7.3 SKU e nomenclatura gerados

`_slug()` remove acentos/pontuação, converte em caixa alta e limita cada
segmento a 8 caracteres — por isso o preview da UI é importante:

| Material digitado | Segmento do SKU | SKU final | `nome` da filha |
|---|---|---|---|
| Sulfite | `SULFITE` | `IMP-SULFITE` | Impressão Sulfite |
| Alto alvura | `ALTOALVU` | `IMP-ALTOALVU` | Impressão Alto alvura |
| Fotográfico | `FOTOGRFI` | `IMP-FOTOGRFI` | Impressão Fotográfico |

> Atenção: "Alto alvura" perde o espaço e é truncado em 8; "Fotográfico" perde
> o acento. O operador vê o SKU antes de confirmar e pode ajustar o
> `prefixo_sku` ou o texto do material para obter um código legível.

`codigo` (único por filial) é gerado como `<sku>-<8 hex>`, ex.:
`IMP-SULFITE-a1b2c3d4`.

### 7.4 Uso no PDV e na O.S.

- Operador bipa `IMP-FOTOGRFI` → `_por_codigo` resolve → item "Impressão
  Fotográfico", `valor_unitario=10,00`, quantidade 1 → total R$ 10,00.
- O `venda_service` **não** chama baixa de estoque (serviço não controla
  estoque) e o kardex permanece intocado.
- Na O.S., o mesmo item entra como linha de serviço próprio com
  `valor_unitario=10,00` (`os_service.py:60-73`).
- Se o SKU não estiver no cache (ex.: cadastro feito após a abertura da tela),
  `_buscar_sku_no_servidor` consulta `/v1/pdv/produtos/buscar-sku/IMP-FOTOGRFI`
  — que passa a encontrar serviços após a Fase 2.

---

## 8. Invariantes que não podem regressar

1. **Nenhum serviço com estoque.** `ck_produto_servico_sem_estoque` + nenhuma
   linha em `produto_estoque` + nenhuma movimentação de kardex.
2. **Isolamento por filial.** SKU/`codigo` únicos por filial; pai e filha na
   mesma filial (FK composta); `buscar_por_sku` sempre com `filial_id`.
3. **Identidade imutável.** `sku`, `uuid`, `produto_pai_id`, `tipo` não mudam
   via PUT.
4. **Preço é decisão de gerência.** Tanto na geração quanto na propagação.
5. **Idempotência.** Regerar combinação existente reativa a filha; nunca cria
   duplicata (UNIQUE composto + verificação por SKU).
6. **Soft-delete em cascata.** Desativar o pai desativa as filhas na mesma
   transação (`api/cadastros.py:197-199`).
7. **Erro detalhado no log.** Qualquer 400/404/409/422 do novo fluxo continua
   sendo registrado pelos handlers de `main.py` (v0.5.29), sem segredos.

---

## 9. Plano de testes

### 9.1 Backend (`backend/tests/`)

| Teste novo | O que prova |
|---|---|
| `test_servico_pode_ser_pai_de_variacao` | 201; 3 filhas com `tipo=servico`, `controla_estoque=false` |
| `test_variante_servico_nao_tem_linha_de_estoque` | `SELECT` em `produto_estoque` → 0 linhas para as filhas |
| `test_venda_de_variante_servico_nao_baixa_estoque` | venda conclui; kardex sem SAIDA; nenhum `UPDATE` em saldo |
| `test_preco_explicito_obrigatorio_para_servico` | 422 quando falta `preco_venda` |
| `test_propagacao_nao_altera_preco_de_servico` | preços 1/8/10 permanecem após `propagar-preco` |
| `test_buscar_sku_encontra_variante_servico` | `buscar_por_sku` e `/v1/pdv/produtos/buscar-sku/...` |
| `test_material_na_unique` | duas variações que diferem só por `material` são aceitas |
| `test_pai_de_outra_filial_continua_404` | isolamento preservado |
| `test_pai_inativo_continua_400` | regra antiga preservada |

Ajustes em testes existentes: `test_produtos_variacoes_contrato.py` (hoje espera
400 para pai serviço — passa a esperar 201) e o mutante correspondente no
harness.

### 9.2 Desktop (`desktop/tests/`)

- `test_dialogo_variacoes_servico_ofere_material` — domínio e aviso corretos;
- `test_botao_propagar_desabilitado_para_servico`;
- `test_pdv_bipa_sku_de_servico_sem_request` — SKU `IMP-FOTOGRFI` resolvido pelo
  cache `_por_codigo`, sem chamada ao endpoint;
- `test_os_variante_servico_preenche_valor_unitario`.

### 9.3 Mutação (`scripts/testes_mutabilidade.py`)

Novos mutantes, mantendo a meta **100% mortos**:

| Mutante | Teste que deve matar |
|---|---|
| `filha_servico_com_estoque` (forçar `controla_estoque=True`) | `test_variante_servico_nao_tem_linha_de_estoque` + CHECK |
| `preco_servico_herdado` (remover 422) | `test_preco_explicito_obrigatorio_para_servico` |
| `propagacao_sobrescreve_servico` | `test_propagacao_nao_altera_preco_de_servico` |
| `busca_sku_ignora_servico` (readicionar filtro de tipo) | `test_buscar_sku_encontra_variante_servico` |
| `material_fora_da_unique` | `test_material_na_unique` |

Os 17 mutantes atuais continuam ativos (incluindo `log_http_desligado` e
`sanitizacao_desligada`).

---

## 10. Critérios de aceite

- [ ] Cadastrar "Impressão" como serviço e gerar as 3 variações com preços
      1,00 / 8,00 / 10,00 em uma única operação.
- [ ] As 3 filhas aparecem com `↳` na grade, `tipo=SERVICO`, sem estoque.
- [ ] Nenhuma linha em `produto_estoque` e nenhum kardex é criada para elas.
- [ ] Bipar `IMP-SULFITE`, `IMP-ALTOALVU` e `IMP-FOTOGRFI` no PDV adiciona o
      item com o preço correto e **sem baixa de estoque**.
- [ ] Selecionar qualquer uma delas em O.S. preenche `valor_unitario` correto.
- [ ] "Propagar preço" está indisponível para o pai serviço; os preços
      permanecem distintos.
- [ ] Tentativa de gerar variação de serviço sem preço → 422 com mensagem clara
      e linha no log.
- [ ] Regerar as mesmas três combinações não cria duplicatas (idempotência).
- [ ] Tudo isso restrito à filial logada; pai de outra filial → 404.
- [ ] Suítes: backend e desktop 100% verdes; mutação 22/22 mortos (17 atuais +
      5 novos).
- [ ] Migration aplicada primeiro em branch de backup, com aprovação e
      registro do LSN.

---

## 11. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Reintroduzir o bug "serviço com estoque" que v0.5.26 corrigiu | `CHECK` no banco + gerador condicional + mutante `filha_servico_com_estoque` |
| Migration da UNIQUE com dados reais | Pré-checagem de duplicatas; branch de backup; aprovação explícita |
| Propagação acidental achatar os preços | Botão desabilitado no cliente **e** guarda no servidor (defesa em duas camadas) |
| SKUs ilegíveis por acentos/truncamento | Preview no diálogo antes de confirmar |
| Operador esperar baixa de estoque ao vender serviço | Aviso no diálogo e tooltip no botão (D7) |
| Mudança quebrar cadastro de produtos existente | Trilha A intacta: herança de preço, estoque e SKU permanecem iguais |

---

## 12. Fora de escopo desta proposta

- Preço por **faixa de quantidade** (ex.: 100 cópias sulfite mais barato) —
  exigiria tabela de preços por faixa; registrado como evolução futura.
- Atributos genéricos (EAV: nome/valor livres por produto) — hoje o modelo é de
  colunas fixas; `atrib_material` é a extensão mínima.
- Cálculo de custo por substrato na Produção/OS — hoje `preco_custo` é por
  variante, sem consumo de bobina/papel.
- Gating/licenciamento específico para "variações de serviço" — o módulo
  `cadastros` já cobre o recurso.

---

## 13. Referências

- `docs/verificacao_produtos_variacoes.md` — histórico do fluxo e correções
  anteriores (inclusive o bug do serviço com estoque).
- `docs/auditoria_cadastro_produtos.md` — medições da tela de cadastro.
- `docs/logging_erros.md` — requirement "sempre que houver erro, detalhar no log".
- Código: `backend/app/services/variacao_service.py`,
  `backend/app/models/cadastros.py`, `backend/app/schemas/cadastros.py`,
  `backend/app/api/cadastros.py`, `backend/app/api/pdv.py`,
  `desktop/printgest/ui/modulos/dialogo_variacoes.py`,
  `desktop/printgest/ui/modulos/produtos.py`,
  `desktop/printgest/ui/modulos/venda_balcao.py`.
