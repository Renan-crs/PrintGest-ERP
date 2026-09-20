# Documento de Requisitos do Produto (PRD)
## Sistema de Gestão para Gráfica Rápida

**Versão:** 2.0.0
**Data:** 20 de setembro de 2026
**Status:** Rascunho para validação
**Baseline:** Substitui PRD v1.2.0 — reduzido ao escopo real de implantação (até 5 máquinas, 1 filial, internet disponível na rede)

---

## Histórico de Revisões

| Versão | Alterações |
|---|---|
| 1.0.0 | Versão inicial enxuta, sem licenciamento via terceiro. |
| 1.2.0 (RedGest) | Versão superdimensionada: Local API Service, licenciamento offline-first com hardware ID/rebind/tamper, blind index de PII, Documenso, SOX/ISO 9001/WCAG. |
| **2.0.0** | Recalibrada para o caso real: 5 máquinas na mesma rede com internet, licenciamento online-first via RedGest (token curto + refresh, sem hardware ID), LGPD proporcional ao porte, backlog explícito do que foi adiado. |

---

## 1. Visão Geral

### 1.1 Propósito

Sistema ERP desktop (Windows) para gráficas rápidas de pequeno porte, operando em rede local com **até 5 estações**, com uma máquina atuando como servidor local (Local API Service + PostgreSQL). Gerencia Ordens de Serviço, orçamentos, vendas, estoque, financeiro e emissão fiscal.

### 1.2 Contexto de operação

- Todas as estações estão na mesma rede local, **com internet disponível como regra**
- Offline é tratado como **falha temporária de conectividade**, não como modo de uso planejado
- Uma máquina da rede (não necessariamente dedicada) roda o **Local API Service**; as demais 4 estações acessam esse serviço via rede interna — nenhuma estação-cliente acessa o PostgreSQL ou a internet diretamente para fins do ERP
- Expansão futura para filiais é suportada pelo modelo de dados, mas **não é requisito da primeira entrega**

### 1.3 Escopo incluído (MVP)

- Cadastros: clientes, fornecedores, vendedores, atendentes, produtos/serviços, usuários
- Movimento: Ordem de Serviço, Orçamento, Venda Balcão, Pedido de Compra, Agendamento
- Estoque: entrada/saída, relatório de reposição, produtos mais vendidos
- Financeiro: caixa, contas a pagar/receber, plano de contas
- Relatórios: vendas, clientes que mais compram, serviços mais executados, aniversariantes
- Impressão: jato de tinta, matricial 80 colunas, cupom não fiscal 40 colunas (QPrinter)
- Emissão fiscal: NF-e e NFC-e via gateway terceirizado (Focus NFe, PlugNotas ou eNotas)
- Controle de acesso por usuário/nível (admin, gerente, operador, caixa)
- Licenciamento via RedGest, modelo online-first (ver §3)
- Personalização: logotipo, fundo de tela, reajuste de preços em bloco com trilha de auditoria simples

### 1.4 Escopo excluído do MVP (backlog — ver §9)

- Multi-filial ativo (modelo de dados já suporta; ativação de fato é pós-MVP)
- Criptografia de PII com blind index (AES-GCM + HMAC + HKDF)
- Assinatura digital via Documenso
- Curva ABC de estoque, conciliação bancária OFX/CSV
- Réplica/sincronização multi-servidor
- Aplicativo móvel
- Compliance corporativo não aplicável (SOX, ISO 9001, WCAG) — mantém-se apenas LGPD e obrigações fiscais reais

### 1.5 Público-alvo

Donos e operadores de gráficas rápidas de pequeno porte no Brasil, tipicamente com 1 a 5 estações de trabalho em uma única unidade, com expansão possível para filiais no médio prazo.

### 1.6 Decisões-chave desta versão

| # | Decisão | Resumo |
|---|---|---|
| D1 | Local API Service continua obrigatório | Centraliza acesso ao banco e RBAC; estações-cliente nunca acessam PostgreSQL diretamente. Mantido do PRD anterior por ser boa prática independente de porte. |
| D2 | Licenciamento online-first, sem hardware ID | Como há internet como regra, a licença é validada por token de curta duração renovado automaticamente, vinculada ao CNPJ da gráfica — não à máquina. |
| D3 | LGPD proporcional | Controle de acesso por usuário/nível + backup substituem criptografia de campo (blind index) como medida inicial; criptografia de PII vira item de backlog, não bloqueador de lançamento. |
| D4 | Sem dependência de terceiro fora do RedGest para licenciamento | RedGest permanece como autoridade emissora, mas com contrato simplificado (ver §3). |
| D5 | Multi-filial: dado pronto, funcionalidade não ativada | Tabelas já usam `filial_id`; telas e regras de consolidação entre filiais ficam para quando houver de fato uma segunda unidade. |

---

## 2. Arquitetura

### 2.1 Topologia (até 5 máquinas)

```
[Estação 1] ---\
[Estação 2] ----\
[Estação 3] -----> Local API Service (FastAPI) ---> PostgreSQL
[Estação 4] ----/         (roda em 1 das 5 máquinas)
[Estação 5] ---/                   |
                                    v
                          RedGest (validação de licença,
                          só esta máquina acessa a internet
                          para fins de licenciamento)
```

- A máquina que roda o Local API Service deve permanecer ligada durante o expediente. Recomenda-se que não seja a estação de atendimento mais usada, para evitar contenção.
- Requisito mínimo recomendado para essa máquina: 8GB RAM, SSD, Windows 10/11 64 bits — deve ser documentado no manual de instalação.
- Se essa máquina reiniciar ou cair, as demais 4 ficam sem acesso ao sistema até ela voltar — ponto único de falha aceito conscientemente neste porte; mitigado por registrar o Local API Service e o PostgreSQL como serviços Windows com início automático.

### 2.2 Stack técnica

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.12 |
| Interface desktop | PySide6 (Qt6) |
| Backend local | FastAPI (Local API Service) |
| Banco de dados | PostgreSQL 15+ |
| ORM / Migrações | SQLAlchemy 2.x + Alembic |
| Impressão | QPrinter (nativo Qt) |
| Emissão fiscal | Gateway REST (Focus NFe / PlugNotas / eNotas) |
| Empacotamento | PyInstaller + Inno Setup (instalador único com PostgreSQL embarcado) |

---

## 3. Licenciamento (RedGest — modelo online-first)

### 3.1 Princípio

A licença é emitida e controlada pelo RedGest, vinculada ao **CNPJ da gráfica** (não a hardware). Apenas o Local API Service comunica-se com o RedGest; as estações-cliente nunca o fazem diretamente.

### 3.2 Fluxo

1. **Ativação**: no primeiro uso, o operador informa CNPJ + código de licença (recebido na contratação). O Local API Service troca isso por credenciais (`client_id`/`client_secret`) junto ao RedGest — fluxo 100% online, sem ativação assistida manual.
2. **Token**: RedGest emite um JWT RS256 de curta duração (ex.: 4 horas) contendo entitlements (`max_estacoes`, módulos habilitados, plano).
3. **Renovação automática**: o Local API Service renova o token periodicamente (ex.: a cada 3h) antes de expirar. Processo silencioso, sem intervenção do usuário.
4. **Falha de renovação (internet fora do ar)**: sistema continua operando normalmente com o último token válido até ele expirar. Ao expirar sem renovação, entra em **modo leitura** (bloqueia escrita e emissão fiscal) até a conexão voltar.
5. **Janela de tolerância offline**: 24–72h, não 7 dias — adequado a "internet cai, depois volta", não a "gráfica opera sem internet por design".
6. **Revogação** (inadimplência/cancelamento): refletida na próxima tentativa de renovação; sistema entra em modo leitura em poucas horas.
7. **Troca da máquina-servidor**: reinstala o Local API Service na nova máquina e reativa com o mesmo CNPJ — sem fluxo de rebind com limite de tentativas.

### 3.3 O que foi removido do desenho original (v1.2) e por quê

| Removido | Motivo |
|---|---|
| Ativação offline assistida (código + suporte manual) | Só necessária se a gráfica nunca tiver internet na instalação — não é o caso aqui |
| Hardware ID com tolerância/score + rebind limitado (2/90 dias) | Licença por CNPJ elimina a necessidade de vincular e revincular hardware |
| Detecção elaborada de tamper de relógio (LVT assinado) | Proteção antipirataria desproporcional para o risco real deste produto/porte |
| Cache de licença criptografado com DPAPI + HMAC | Token de curta duração já limita a janela de uso indevido sem precisar de criptografia de arquivo local elaborada |

### 3.4 Contrato com o RedGest

Reaproveita o modelo genérico `Sistema`/`Licenca` (ver documento "Plano de generalização do RedGest"), com o ERP da gráfica cadastrado como:

```
codigo: grafica_erp
tipo_licenciamento: online_periodic   -- novo tipo, mais simples que hardware_bound
schema_entitlements: { cnpj_vinculado, max_estacoes, modulos_habilitados[] }
```

**Pendência a resolver com quem mantém o RedGest:** confirmar que o tipo `online_periodic` será suportado — hoje o RedGest (v3.5) só tem os sistemas `ILPI_GESTAO` e `RH_DIGITAL`, nenhum deles com esse modelo de token curto.

---

## 4. Modelo de Dados (resumo)

Ver `schema.sql` para o DDL completo. Estrutura principal:

- `empresa` → `filial` (1:N) — tabelas operacionais referenciam `filial_id`, mesmo operando com 1 filial hoje
- `cliente`, `fornecedor`, `funcionario`, `produto` — cadastros
- `ordem_servico` + `ordem_servico_item` — OS/orçamento
- `venda_balcao` + `venda_balcao_item` — venda direta
- `pedido_compra` + `pedido_compra_item` — compras de insumo
- `movimento_estoque` — kardex
- `conta_receber`, `conta_pagar`, `movimento_caixa`, `plano_contas` — financeiro
- `documento_fiscal` — vínculo com retorno do gateway fiscal

---

## 5. RBAC (simplificado)

| Nível | Permissões |
|---|---|
| Admin | Acesso total, incluindo reajuste de preços em bloco e configurações |
| Gerente | Cadastros, movimento, financeiro, relatórios — sem configurações de sistema |
| Operador | Cadastros e movimento (OS, orçamento, venda) — sem financeiro |
| Caixa | Venda balcão e movimentação de caixa apenas |

Controles associados: bloqueio por tentativas de senha incorretas, expiração de sessão por inatividade.

---

## 6. Requisitos Não Funcionais

| Requisito | Critério |
|---|---|
| Instalação | Instalador único, execução < 10 min, sem configuração manual de banco |
| Compatibilidade | Windows 10 e 11, 64 bits |
| Performance | Listagens (clientes, produtos, OS) respondem em < 1s com até 50 mil registros |
| Backup | Rotina de backup do PostgreSQL configurável (local ou rede), documentada para o usuário final |
| LGPD | Dados pessoais (CPF/CNPJ, e-mail, telefone) protegidos por controle de acesso via RBAC + backup regular. Criptografia de campo fica como item de backlog (§9), não bloqueador de lançamento — proporcional ao volume e risco de um cadastro de porte pequeno |
| Fiscal | XML de NF-e/NFC-e autorizados armazenados localmente por no mínimo 5 anos, com backup |
| Disponibilidade do Local API Service | Registrado como serviço Windows com início automático, para reduzir impacto de reinicializações da máquina-servidor |

---

## 7. Roadmap de Desenvolvimento

| Fase | Objetivo | Entregáveis |
|---|---|---|
| 1 | Fundação | Schema Alembic; Local API Service (FastAPI) com healthcheck; instalador com PostgreSQL embarcado; setup de serviços Windows |
| 2 | Núcleo operacional | Cadastros, Movimento (OS/Orçamento/Venda Balcão), Estoque, RBAC básico |
| 3 | Financeiro e Fiscal | Caixa, contas a pagar/receber, integração com gateway NF-e/NFC-e |
| 4 | Licenciamento | Integração com RedGest no modelo `online_periodic` (§3); depende da pendência com o time do RedGest |
| 5 | Relatórios e fechamento | Relatórios operacionais, reajuste em bloco auditado, empacotamento final, testes de aceitação |

---

## 8. Critérios de Aceite / Plano de Testes (resumo)

Diferente da versão anterior (focada quase exclusivamente em licenciamento), os testes cobrem operação real e licenciamento em proporção equilibrada:

**Operacional**
- Criação, edição e fechamento de OS com múltiplos itens
- Baixa de estoque automática ao fechar venda/OS
- Emissão de NF-e/NFC-e via gateway, incluindo cenário de contingência
- Fechamento de caixa com conferência de valores
- Acesso simultâneo de 5 estações sem lock indevido em OS diferentes

**Licenciamento**
- Ativação online (CNPJ + código)
- Renovação automática de token
- Queda de internet por período curto (dentro da janela de tolerância) — sistema continua operando
- Queda de internet além da janela de tolerância — modo leitura, com mensagem clara ao usuário
- Revogação de licença — reflexo em modo leitura dentro de poucas horas

**Infraestrutura**
- Reinício da máquina-servidor — serviços voltam automaticamente, estações-cliente reconectam
- Restore de backup em máquina limpa

---

## 9. Backlog (pós-MVP, avaliar conforme demanda real)

| Item | Motivo do adiamento |
|---|---|
| Multi-filial ativo (telas, consolidação financeira entre filiais) | Modelo de dados já suporta; sem 2ª unidade ainda, não há o que validar |
| Criptografia de PII (blind index AES-GCM + HMAC) | Desproporcional ao volume/risco atual; reavaliar se a base de clientes crescer muito ou se houver exigência contratual específica |
| Assinatura digital via Documenso | Validar se é demanda real do cliente antes de construir cota e integração |
| Curva ABC de estoque | Nice-to-have analítico, não bloqueia operação |
| Conciliação bancária OFX/CSV | Nice-to-have financeiro, não bloqueia operação |
| Réplica/sincronização multi-servidor | Só relevante se filiais remotas precisarem operar de forma desconectada da matriz |
| Hardware ID / anti-tamper elaborado | Só reconsiderar se houver evidência concreta de pirataria do produto |

---

## 10. Glossário

| Termo | Definição |
|---|---|
| Local API Service | Serviço FastAPI local, único ponto de acesso ao PostgreSQL e de enforcement de RBAC |
| Modo Leitura | Estado em que o ERP permite apenas consulta, bloqueando escrita e emissão fiscal, por falta de licença válida |
| Token de licença | JWT RS256 de curta duração emitido pelo RedGest, renovado automaticamente pelo Local API Service |
| Entitlement | Permissão específica contida no token de licença (ex.: `max_estacoes`) |
| `tipo_licenciamento: online_periodic` | Modelo de licenciamento definido nesta versão: validação online recorrente, sem vínculo a hardware |

---

## 11. Próximos Passos

1. Validar este PRD com quem decide o escopo de negócio
2. Resolver a pendência com o time do RedGest: suporte ao tipo `online_periodic` (§3.4)
3. Selecionar gateway fiscal (Focus NFe recomendado para começar)
4. Iniciar Fase 1
