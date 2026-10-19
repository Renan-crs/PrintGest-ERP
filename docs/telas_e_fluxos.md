# Lista de Telas e Fluxos de Processo — ERP Gráfica Rápida

Baseado no PRD v2.0 (escopo MVP: 5 estações, 1 filial, licenciamento online-first).

---

## 1. Lista de Telas por Módulo

### 1.1 Acesso e Licenciamento
- Tela de Login (usuário/senha)
- Tela de Ativação de Licença (1ª execução: chave de produto `XXXX-XXXX-XXXX-XXXX`)
- Banner/Modal de Aviso de Modo Leitura (licença sem renovação)

### 1.2 Cadastros
- Clientes (lista + formulário; campo de foto)
- Fornecedores (lista + formulário)
- Funcionários / Vendedores / Atendentes (lista + formulário)
- Produtos e Serviços (lista + formulário; 2 campos de foto; preço custo/venda; estoque mínimo)
- Categorias de Produto (lista simples)
- Usuários do Sistema (lista + formulário; nível de acesso)

### 1.3 Movimento
- Ordem de Serviço — Lista (com filtro por status)
- Ordem de Serviço — Formulário (dados do cliente, itens, valores, status)
- Orçamento — Formulário (mesma base da OS, com opção "converter em OS")
- Projetos — Quadro (Kanban por etapa) e Lista (1 projeto = 1 O.S., tipo `os`)
- Venda Balcão — Tela de Venda (busca rápida de produto, totalizador, forma de pagamento)
- Pedido de Compra — Lista
- Pedido de Compra — Formulário (fornecedor, itens, previsão de entrega)
- Agendamento — Calendário/Lista (produção, entregas)

### 1.4 Estoque
- Consulta de Estoque (lista com saldo atual e mínimo)
- Movimentação Manual de Estoque (ajuste/entrada/saída avulsa)
- Relatório de Reposição (produtos abaixo do mínimo)
- Relatório de Mais Vendidos

### 1.5 Financeiro
- Caixa — Abertura/Fechamento
- Caixa — Extrato do Dia
- Contas a Receber — Lista + Baixa de Pagamento
- Contas a Pagar — Lista + Baixa de Pagamento
- Plano de Contas — Cadastro

### 1.6 Fiscal
- Emissão de NF-e/NFC-e (a partir de Venda Balcão ou OS)
- Consulta de Documentos Fiscais Emitidos (status, XML, DANFE)
- Tela de Contingência (aviso quando gateway fiscal está indisponível)

### 1.7 Relatórios
- Vendas por Período
- Clientes que Mais Compram
- Serviços Mais Executados
- Aniversariantes do Mês

### 1.8 Configurações
- Dados da Empresa (logotipo, razão social, CNPJ)
- Personalização (fundo de tela, impressoras padrão)
- Reajuste de Preços em Bloco (simulação + confirmação com senha)
- Gestão de Usuários e Níveis de Acesso

---

## 2. Fluxos de Processo (passo a passo)

### 2.1 Fluxo: Ordem de Serviço (do orçamento à entrega)

1. Atendente abre novo Orçamento → seleciona cliente (ou cadastra na hora)
2. Adiciona itens (produto/serviço, quantidade, dimensões se aplicável)
3. Sistema calcula valor total; atendente aplica desconto se autorizado
4. Orçamento salvo com status `aberto`
5. Cliente aprova → atendente converte Orçamento em Ordem de Serviço (status `aberta`)
6. Produção assume a OS → atualiza status para `producao`
7. Produção conclui → status `pronta`; sistema pode disparar aviso de retirada
8. Cliente retira/paga → status `entregue`; gera lançamento em Contas a Receber ou baixa direta no Caixa
9. Se aplicável, emite NF-e/NFC-e vinculada à OS

### 2.2 Fluxo: Venda Balcão

1. Operador abre tela de Venda Balcão
2. Busca produto por código ou nome → adiciona à venda
3. Repete até finalizar itens
4. Seleciona forma de pagamento
5. Confirma venda → baixa automática de estoque (via `movimento_estoque`)
6. Sistema oferece emissão de NF-e/NFC-e
7. Se emitida: aguarda retorno do gateway fiscal; se autorizada, vincula XML/DANFE à venda; se rejeitada, exibe erro para correção
8. Lançamento no Caixa do dia

### 2.3 Fluxo: Pedido de Compra e Entrada de Estoque

1. Usuário cria Pedido de Compra → seleciona fornecedor e itens
2. Pedido salvo com status `aberto`
3. Mercadoria chega → usuário abre o pedido e confirma recebimento
4. Sistema gera entrada em `movimento_estoque` para cada item, atualizando saldo
5. Pedido muda para status `recebido`
6. Gera lançamento em Contas a Pagar (se não pago à vista)

### 2.4 Fluxo: Caixa (abertura, movimento, fechamento)

1. Operador abre o caixa no início do expediente (valor inicial informado)
2. Cada venda balcão/recebimento de OS gera lançamento automático de entrada
3. Sangrias e suprimentos podem ser lançados manualmente
4. No fim do expediente, operador fecha o caixa
5. Sistema confere valor esperado (soma dos lançamentos) vs valor informado na conferência física
6. Divergência, se houver, é registrada

### 2.5 Fluxo: Licenciamento (chave de produto, validação online)

1. Na 1ª execução, o sistema solicita a chave de produto (`XXXX-XXXX-XXXX-XXXX`)
2. Local API Service valida a chave online no RedGest (Contrato C) e registra o fingerprint da máquina
3. Sistema libera o uso normal
4. Local API Service revalida a chave em background a cada ~6 h (detecta revogação/bloqueio/expiração)
5. Se a revalidação falhar (sem internet): sistema segue funcionando dentro da vigência
6. Vencida a vigência sem reconexão, abre-se a tolerância offline de 72 h (ainda escreve, com aviso)
7. Esgotada a tolerância: modo leitura — bloqueia criação/edição e emissão fiscal, mantém consulta
8. Conexão volta → revalidação automática → sistema volta ao normal sem ação do usuário

### 2.6 Fluxo: Reajuste de Preços em Bloco

1. Admin acessa Configurações → Reajuste em Bloco
2. Seleciona critério (categoria, todos os produtos, percentual ou valor fixo)
3. Sistema mostra simulação (preços antes/depois) sem aplicar ainda
4. Admin confirma com senha
5. Sistema aplica em lote e registra trilha de auditoria (quem, quando, valores antigos e novos)

---

## 3. Fluxo de Telas (navegação)

### 3.1 Fluxo principal de entrada no sistema

```
[Login] --credenciais ok--> [Licença válida?]
                                  |
                     não -------- +-------- sim
                     |                        |
              [Ativação de Licença]     [Tela Principal / Dashboard]
                     |                        |
              ativa com sucesso --------------+
```

### 3.2 Navegação a partir da Tela Principal

```
Tela Principal
 ├── Cadastros
 │     ├── Clientes ── [Lista] ── [Formulário]
 │     ├── Fornecedores ── [Lista] ── [Formulário]
 │     ├── Funcionários ── [Lista] ── [Formulário]
 │     └── Produtos ── [Lista] ── [Formulário]
 │
 ├── Movimento
 │     ├── Ordem de Serviço ── [Lista] ── [Formulário] ──> [Emissão Fiscal] (opcional)
 │     ├── Orçamento ── [Lista] ── [Formulário] ──> "Converter em OS" ──> [Formulário de OS]
 │     ├── Venda Balcão ── [Tela de Venda] ──> [Emissão Fiscal] (opcional) ──> [Caixa: lançamento automático]
 │     ├── Pedido de Compra ── [Lista] ── [Formulário] ──> [Confirmar Recebimento] ──> [Estoque atualizado]
 │     └── Agendamento ── [Calendário/Lista]
 │
 ├── Estoque
 │     ├── Consulta de Estoque
 │     ├── Movimentação Manual
 │     ├── Relatório de Reposição
 │     └── Relatório de Mais Vendidos
 │
 ├── Financeiro
 │     ├── Caixa ── [Abertura] ── [Extrato do Dia] ── [Fechamento]
 │     ├── Contas a Receber ── [Lista] ── [Baixa de Pagamento]
 │     ├── Contas a Pagar ── [Lista] ── [Baixa de Pagamento]
 │     └── Plano de Contas
 │
 ├── Fiscal
 │     ├── Consulta de Documentos Fiscais
 │     └── Tela de Contingência (exibida automaticamente se gateway indisponível)
 │
 ├── Relatórios
 │     ├── Vendas por Período
 │     ├── Clientes que Mais Compram
 │     ├── Serviços Mais Executados
 │     └── Aniversariantes
 │
 └── Configurações (visível conforme nível de acesso)
       ├── Dados da Empresa
       ├── Personalização
       ├── Reajuste de Preços em Bloco ── [Simulação] ── [Confirmação com senha]
       └── Usuários e Níveis de Acesso
```

### 3.3 Fluxo de tela: Venda Balcão até Emissão Fiscal

```
[Tela de Venda Balcão]
        |
   adiciona itens
        |
  confirma pagamento
        |
        v
[Venda registrada] ---> [Lançamento automático no Caixa]
        |
   "Emitir Nota?"
     /        \
   Não          Sim
    |            |
    v            v
[Fim]     [Chamada ao Gateway Fiscal]
                  |
         +--------+--------+
         |                 |
     Autorizada        Rejeitada/Indisponível
         |                 |
   [XML/DANFE           [Tela de erro com
   vinculados à          motivo + opção de
      venda]              tentar novamente
         |               ou emitir depois
         v               (contingência)]
      [Fim]
```

### 3.4 Atalhos do teclado

Atalhos **globais** (ativos em qualquer tela, respeitando o RBAC — só navegam
para módulos que o usuário pode abrir):

| Tecla | Ação |
| --- | --- |
| `F2` | Abre **Clientes** |
| `F3` | Abre **Produtos** |
| `F5` | Abre **PDV** (Venda Balcão) |

No **PDV**, com o foco dentro da página:

| Tecla | Ação |
| --- | --- |
| `F6` | Alterna para **Nova venda** |
| `F9` | **Finalizar venda** |
| `Ctrl+F` | Foca a busca da visão ativa (produto na *Nova venda*; vendas no *Histórico*) |
| `Enter` (na busca de produto) | Adiciona o item selecionado |

Nas telas de **cadastro** (Clientes, Fornecedores, Produtos & Serviços, O.S.) e em
**Projetos**, com o foco dentro da página:

| Tecla | Ação |
| --- | --- |
| `F6` | Novo registro (limpa o formulário e foca o primeiro campo) — em Projetos, "Novo Projeto" |
| `F10` | Salvar alterações |
| `Esc` | Cancelar a edição (limpa o formulário) |
| `Ctrl+F` | Foca a busca da lista |

No **Quadro** de Projetos (visão Kanban), os cartões são focáveis: `Tab` percorre
as etapas e `Enter`/`Espaço` abrem o projeto na visão Lista.

> Os atalhos globais `F2`/`F3`/`F5` continuam valendo em qualquer tela; o `F6`
> de cada cadastro é local e não colide com o `F6` do PDV (que alterna para
> "Nova venda") porque só a página visível tem os atalhos ativos.

---

## 4. Observações de Design

- Todas as listas (Clientes, Produtos, OS, etc.) devem ter busca rápida — é o padrão do sistema de referência (OSGrafica) e crítico para uso no dia a dia
- Telas de Venda Balcão e OS precisam funcionar bem por teclado (atalhos), já que operador de gráfica normalmente não usa mouse para tudo
- O nível de acesso (RBAC) deve ocultar itens de menu que o usuário não tem permissão, não apenas bloquear ao clicar — evita confusão
- Tela de Modo Leitura (licença) deve deixar claro, em linguagem simples, o que está bloqueado e o que ainda funciona (consulta), sem jargão técnico
