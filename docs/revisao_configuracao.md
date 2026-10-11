# Configuração — empresa, personalização, reajuste em bloco e usuários (release 0.2)

Documento de entrega do menu **Configurações** (id `configuracoes`), alinhado a
`docs/telas_e_fluxos.md` §1.8 / §2.6, ao PRD v2.0/v2.1 (§1.3, §1.8, RBAC §5) e ao
`schema.sql` (tabelas `empresa`, `preco_reajuste_historico`; coluna
`produto.bloqueado_reajuste`).

> **Sobre os IDs.** O repositório não contém a lista numerada original desta
> tarefa; os itens abaixo usam a âncora **CF1…CF7** apenas para rastreio e foram
> reconstruídos a partir do escopo recebido. Cruze com a lista original.

---

## 1. Premissas de escopo (adotadas na largada)

1. **Exclusivo do admin.** Os quatro itens internos (`dados_empresa`,
   `personalizacao`, `reajuste_bloco`, `usuarios`) e o item de menu
   `configuracoes` são visíveis apenas a `admin` (RBAC §5). O backend reforça com
   `require_nivel(ADMIN)` no router `/v1/config`.
2. **Reajuste sempre auditado.** O reajuste em bloco **exige prévia** (`simular`)
   e **confirmação por senha do próprio admin** (`verify_password`). Só então
   `aplicar` grava a trilha em `preco_reajuste_historico` (`detalhes` com valores
   antes/depois, quem e quando — §2.6).
3. **Proteção individual respeitada.** Produtos com `bloqueado_reajuste = true`
   (schema.sql §8.1) são **pulados**: aparecem na contagem de `bloqueados` e não
   são tocados pelo `aplicar`.
4. **Sem invenção de dados.** Empresa é resolvida por `filial.empresa_id`, com
   fallback para a primeira `empresa` ativa — nunca valores fictícios. Nenhuma
   tabela/coluna nova foi criada; tudo já consta no `schema.sql`.
5. **Modo leitura.** `simular`/`aplicar` são `POST` e, portanto, barrados pelo
   middleware de licença (HTTP 423) em modo leitura; a UI desabilita Simular e
   Aplicar e mantém apenas a consulta (Dados da Empresa, Personalização e
   histórico do reajuste).

---

## 2. Componentes

| Arquivo | Papel | Tipo |
| --- | --- | --- |
| `backend/app/schemas/config.py` | **Novo.** `EmpresaOut/Update`, `ReajusteSimulacao/AplicarIn`, `ReajusteItemOut`, `ReajusteSimulacaoOut`, `ReajusteResultadoOut`, `ReajusteHistoricoOut` | backend (novo) |
| `backend/app/services/config_service.py` | **Novo.** Empresa (leitura/atualização parcial), simulação, aplicação com senha e histórico | backend (novo) |
| `backend/app/api/config.py` | **Novo.** Router `/v1/config` (admin-only) | backend (novo) |
| `backend/app/api/__init__.py` | Registra `config.registrar(api)` | backend (compartilhado) |
| `backend/app/schemas/__init__.py` | Exporta os novos schemas | backend (compartilhado) |
| `desktop/printgest/ui/modulos/configuracao.py` | **Novo.** `PaginaFicha` (base), `PaginaEmpresa`, `PaginaPersonalizacao`, `PaginaReajuste`, `PaginaUsuarios` e host `PaginaConfiguracoes` | tela (novo) |
| `desktop/printgest/core/api.py` | Métodos `empresa`, `atualizar_empresa`, `simular_reajuste`, `aplicar_reajuste`, `reajuste_historico` | compartilhado |
| `desktop/printgest/ui/modulos/__init__.py` | `criar_pagina` mapeia `configuracoes` → host e os ids internos `dados_empresa`/`personalizacao`/`reajuste_bloco`/`usuarios` | compartilhado |
| `desktop/tests/test_config.py` | **Novo.** 13 testes de UI | testes |
| `backend/tests/test_config.py` | **Novo.** 8 testes de backend | testes |
| `docs/evidencias/configuracao/` | Capturas **antes/depois** (1280x720, 1366x768, 1920x1080 × 100/125/150%) | evidência |

**Reuso:** `PaginaUsuarios` herda `PaginaCrud` (grade densa + formulário lateral +
filtros + estado vazio) sobre `/v1/usuarios`, com **filtro local** por nível
(`FILTRO_LOCAL = True`, pois o endpoint não filtra por `nivel_acesso`). Empresa e
Personalização compartilham a base `PaginaFicha` (seções roláveis + rodapé fixo).

---

## 3. Backend (novo) — endpoints e RBAC

| Método | Rota | Perfil | Observação |
| --- | --- | --- | --- |
| `GET` | `/v1/config/empresa` | admin | Empresa da filial (fallback: 1ª ativa) |
| `PUT` | `/v1/config/empresa` | admin | Atualização **parcial** (`exclude_unset`); `null` em coluna NOT NULL é ignorado |
| `POST` | `/v1/config/reajuste/simular` | admin | Prévia (`total`/`afetados`/`bloqueados`/`itens`) sem aplicar |
| `POST` | `/v1/config/reajuste/aplicar` | admin | Exige `senha` do admin autenticado; grava `preco_reajuste_historico` |
| `GET` | `/v1/config/reajuste/historico` | admin | Trilha de auditoria paginada |

Regras do reajuste:

- `criterio`: `todos` (toda a filial) ou `categoria` (exige `categoria_id`).
  Gravado como `todos` / `categoria:<id>` (formato do `schema.sql`).
- `tipo_reajuste`: `percentual` (percentual sobre o preço) ou `valor_fixo`
  (soma ao preço). Arredondamento para 2 casas (`ROUND_HALF_UP`); nunca abaixo de
  zero.
- `bloqueado_reajuste = true` → contabilizado em `bloqueados` e **preservado**.
- A senha é validada contra o hash do próprio usuário (`verify_password`); não
  trafega nem é comparada em claro. `null` de campo obrigatório (`razao_social`,
  `cnpj`, `ambiente_fiscal`, `ativa`) é descartado pelo serviço para nunca violar
  NOT NULL.

---

## 4. Telas (front-end)

### 4.1 Host `PaginaConfiguracoes`

- Barra de título **“Configurações”** + alternador de sub-abas (`chaveRapida`),
  no mesmo padrão de Financeiro/Fiscal.
- Sub-abas: **Dados da Empresa**, **Personalização**, **Reajuste de Preços**,
  **Usuários e Níveis**. Perfis não-admin são filtrados por `pode_abrir` e, sem
  nenhuma aba, exibem “Acesso restrito a administradores.”.

### 4.2 Dados da Empresa (`PaginaEmpresa`)

- Ficha única, sem lista, em painel rolável com **rodapé fixo** (Reverter Esc /
  **Salvar F10**), no mesmo desenho do `PaginaCrud`.
- Seções: **Identificação** (razão social, fantasia, CNPJ, IE, IM, regime,
  CNAE, ambiente fiscal), **Endereço** e **Contato**.
- Validação local: razão social obrigatória; CNPJ, se informado, com 14 dígitos.

### 4.3 Personalização (`PaginaPersonalizacao`)

- Seções **Marca** (logotipo, fundo de tela via `CampoArquivo`) e **Impressão**
  (impressora matricial/cupom).
- O `PUT` envia **apenas** essas quatro chaves (atualização parcial), preservando
  o cadastro fiscal da empresa.

### 4.4 Reajuste de Preços (`PaginaReajuste`) — §2.6

- Cartão de **Parâmetros**: critério (todos/categoria), categoria (habilita só no
  critério “por categoria”), tipo (percentual/valor fixo) e valor.
- Botões **Simular (F8)** e **Aplicar reajuste (F9)**; resumo
  “Prévia: N elegível(is) · M bloqueado(s)”.
- Grade de prévia: **Código · Produto · Antes · Depois · Variação** (estado
  vazio próprio).
- **Aplicar** abre `QInputDialog` pedindo a senha do admin; sem confirmação, nada
  é alterado. Após aplicar, a grade é limpa e o histórico recarregado.
- Cartão **Últimos reajustes (trilha de auditoria)** com até 5 lançamentos
  (quando, magnitude, itens, critério).

### 4.5 Usuários e Níveis (`PaginaUsuarios`)

- Lista paginada sobre `/v1/usuarios` com chips por nível (filtro **local**),
  busca e formato de nível legível.
- Formulário: Nome, E-mail, Login, Nível, Ativo e Senha. **Login é imutável** ao
  editar (o endpoint de update não aceita `login`); a senha em branco mantém a
  atual; na criação exige login e senha (mín. 8).

---

## 5. Requisitos de aceite (mesmo padrão dos módulos anteriores)

| ID | Requisito | Status | Observação |
| --- | --- | --- | --- |
| CF1 | Sem texto cortado sem tooltip | ✅ | Títulos usam `ElideLabel`; a grade elide com tooltip nativo |
| CF2 | Sem **scroll horizontal** e no máx. 1 vertical | ✅ | Ver §6 — `h_max=0` nas 45 combinações; fichas com `v_ativas≤1` |
| CF3 | Estado vazio nas listas | ✅ | Prévia do reajuste e lista de usuários com estado vazio próprio |
| CF4 | Cadastro só por teclado (Tab lógico, Esc cancela) | ✅ | Fichas: F10 salva, Esc recarrega; Usuários: F6/F10/Esc |
| CF5 | Sem conflito de atalhos | ✅ | F8/F9 só no Reajuste; F2/F3/F5 globais intactos; F6 “Novo” preservado |
| CF6 | RBAC preservado | ✅ | Ver §8 |
| CF7 | Sem simular emissão/aplicação sem senha | ✅ | `aplicar` sem senha correta → 400 e nenhum preço alterado |

---

## 6. Layout / testes

- Suíte **desktop**: **225 passed** (212 + 13 de `desktop/tests/test_config.py`).
- Suíte **backend**: **115 passed** (107 + 8 de `backend/tests/test_config.py`).
- Verificação de layout sem imagens (`.dev/check_layout_config.py`): mede as
  scrollbars reais de `dados_empresa`, `personalizacao`, `reajuste`, `usuarios` e
  do `host` em 1280x720 / 1366x768 / 1920x1080 × 100/125/150%. Resultado:
  **horizontal = 0 em todas as 45 combinações**; fichas de registro único com
  **no máximo 1 vertical** ativa.

---

## 7. Screenshots (antes/depois)

Versionados em `docs/evidencias/configuracao/`:

```
antes/    config_antes_<res>_<escala>.png             (9)  — placeholder "em construção"
depois/   config_dados_empresa_<res>_<escala>.png     (9)  — ficha da empresa
depois/   config_personalizacao_<res>_<escala>.png    (9)  — marca + impressão
depois/   config_reajuste_<res>_<escala>.png          (9)  — prévia + trilha
depois/   config_usuarios_<res>_<escala>.png          (9)  — usuários e níveis
```

Resoluções: `1280x720`, `1366x768`, `1920x1080`; escalas: `100`, `125`, `150`.
Geradas por `.dev/snapshot_config.py` (empresa preenchida, categorias, prévia com
um produto bloqueado e trilha com dois lançamentos).

---

## 8. RBAC e regressão

- **Menu v2.1:** item `configuracoes` visível apenas a `admin` (inalterado). O
  backend reforça com `403` via `require_nivel(ADMIN)` (testado com `gerente` e
  `operador`).
- **Não hierárquico:** `gerente` (rank 2) **não** acessa `/v1/config/*`, embora
  tenha rank acima de outros perfis — a regra de Configuração é por nível
  mínimo, coerente com “Sistema = admin”.
- **Sem regressão:** nenhum endpoint existente teve contrato alterado; os novos
  métodos do cliente HTTP apenas acrescentam caminhos. A suíte completa (backend
  e desktop) segue verde.

---

## 9. Fora de escopo / pendências (com motivo)

1. **Aplicação assíncrona/lote grande:** `simular` retorna no máximo 500 itens na
   prévia (a contagem `afetados` é o total real). Processar lotes muito grandes
   com progresso exigiria job em background — fora do escopo desta entrega.
2. **Histórico detalhado por item na UI:** a trilha guarda `detalhes` (antes/
   depois por produto) no banco, mas a tela mostra o resumo do lançamento; abrir o
   detalhe completo dependeria de uma rota de detalhe (`GET .../historico/{id}`)
   não prevista na spec.
3. **Reversão de reajuste:** desfazer um reajuste aplicado não está no PRD; a
   trilha permite auditoria, não rollback.
4. **Upload de logotipo/fundo:** `CampoArquivo` guarda o **caminho** do arquivo
   (como nos demais cadastros); armazenamento/serviço de arquivos não existe no
   produto.
5. **Gestão de senha pelo admin (reset):** a aba Usuários permite definir senha na
   criação e trocá-la na edição; fluxos de “forçar troca no próximo login” e
   políticas de senha não constam no `schema.sql`.
