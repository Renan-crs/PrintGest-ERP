# PrintGest ERP - Sistema de Gestão para Gráficas

![PrintGest Logo](desktop/printgest/ui/assets/printgest-logo-horizontal.svg)

**PrintGest ERP** é um sistema completo de gestão para gráficas, integrado com o **RedGest**, uma plataforma de licenciamento e ativação.

## 🚀 Características Principais

### 📊 Gestão de Negócio
- **Ordens de Serviço (OS)**: Controle completo de produção
- **Orçamentos**: Cotações com fornecedores e conversão em OS
- **Vendas (PDV)**: Sistema de balcão com gestão de caixa
- **Agendamento**: Calendário de produção e entregas
- **Projetos**: Quadro Kanban para controle de tarefas

### 📦 Módulos
| Módulo | Descrição |
|--------|-----------|
| **Clientes** | Cadastro com contato e situação |
| **Produtos/Serviços** | Catálogo com preços e estoque |
| **Fornecedores** | Cotações e pedidos de compra |
| **Financeiro** | Caixa, contas a receber/pagar, relatórios |
| **Estoque** | Controle de insumos (papéis, tintas, etc.) |

### 🔐 Licenciamento
- **Contrato B**: Ativação por CNPJ + código
- **Contrato C**: Ativação por chave de produto
- **Tolerância offline**: 72 horas de funcionamento sem conexão
- **Modo leitura**: Consultas quando a licença está expirada

## 📦 Instalação

### Requisitos
- **Windows 10/11** (64-bit)
- **PowerShell 5.1+**
- **Neon Database** (PostgreSQL gerenciado em nuvem)

### Instalação Rápida
1. Baixe o instalador:
   - **Servidor**: `PrintGest-Setup-0.3.5.exe` (44.1 MB - Neon)
   - **Estação**: `PrintGest-Setup-0.3.5Estacao.exe` (37.9 MB)

2. Execute o instalador:
   ```powershell
   # Instalação padrão (Servidor)
   PrintGest-Setup-0.3.5.exe
   
   # Instalação Estação (aponta para servidor existente)
   PrintGest-Setup-0.3.5Estacao.exe
   ```

3. Siga o assistente e configure a conexão com Neon

### Instalação Manual (Desenvolvedores)

```bash
# Clone o repositório
git clone https://github.com/Renan-crs/PrintGest-ERP-de-Gerenciamento-de-Gr-fica-.git
cd PrintGest-ERP-de-Gerenciamento-de-Gr-fica-

# Backend (Python 3.11+)
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

# Desktop (Python 3.11+)
cd desktop
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 🛠️ Desenvolvimento

### Tecnologias
| Camada | Tecnologia |
|--------|------------|
| **Backend** | FastAPI, SQLAlchemy, PostgreSQL, Alembic |
| **Desktop** | PySide6, Python 3.11+ |
| **Banco** | PostgreSQL 14 (embarcado ou externo) |
| **Licenciamento** | Integração RedGest API |

### Estrutura do Projeto
```
PrintGest/
├── backend/              # API FastAPI
│   ├── app/
│   ├── migrations/
│   └── tests/
├── desktop/              # Cliente PySide6
│   ├── printgest/
│   ├── ui/
│   └── tests/
├── installer/            # Script e specs de instalação
└── docs/                # Documentação técnica
```

## 🔐 Segurança

### Política de Segurança

Se você encontrar uma vulnerabilidade de segurança, por favor, NOTifique-NOS de forma responsável:

**Não abra um issue público para vulnerabilidades de segurança.**

Em vez disso, envie-nos um e-mail para **security@printgest.com.br** (ou entre em contato através do canal de suporte) com:

1. **Descrição detalhada** da vulnerabilidade
2. **Passos para reproduzir** o problema
3. **Impacto** da vulnerabilidade
4. **Sugestões de correção** (se possível)

### Pontos de Contato

| Tipo | Contato |
|------|---------|
| **Vulnerabilidades** | security@printgest.com.br |
| **Suporte Técnico** | suporte@printgest.com.br |
| **Licenciamento** | licenca@printgest.com.br |
| **Documentação** | docs.printgest.com.br |

### Práticas de Segurança Implementadas

- ✅ **Autenticação** via token JWT/RedGest
- ✅ **Autorização** baseada em níveis (Admin, Gerente, Operador)
- ✅ **Criptografia** de dados sensíveis no cofre do SO
- ✅ **Validação de input** em todos os endpoints
- ✅ **Rate limiting** em endpoints críticos
- ✅ **Logs de auditoria** para ações sensíveis

### Reportando uma Vulnerabilidade

1. **Não divulgue** publicamente a vulnerabilidade
2. **Forneça** detalhes completos para reprodução
3. **Aguarde** nossa resposta (idealmente 48h)
4. **Colabore** conosco no processo de correção

Recebemos agradecimentos por descobertas responsáveis e reconhecemos contribuições na segurança.

## 📖 Documentação

### Documentação do Usuário
- [Guia do Usuário](docs/guia_usuario.md)
- [Fluxos de Trabalho](docs/fluxos.md)
- [Tela de Ativação](docs/ativacao.md)

### Documentação Técnica
- [Arquitetura do Sistema](docs/arquitetura.md)
- [API Reference](docs/api.md)
- [Migrações de Banco](docs/migracoes.md)
- [Empacotamento](docs/empacotamento.md)

### Roadmap
- [Plano de Desenvolvimento](docs/roadmap.md)
- [PRD v3.0](docs/prd_v3.0.md)

## 🤝 Contribuindo

### Como Contribuir

1. Fork o projeto
2. Crie uma branch para suas alterações (`git checkout -b feature/nova-funcionalidade`)
3. Commit suas mudanças (`git commit -m 'Feat: nova funcionalidade'`)
4. Push para a branch (`git push origin feature/nova-funcionalidade`)
5. Abra um Pull Request

### Diretrizes de Contribuição

- **Commits claros**: Use mensagens descritivas
- **Código limpo**: Siga padrões PEP8
- **Testes**: Escreva testes para novas funcionalidades
- **Documentação**: atualize docs quando necessário

## 📜 Licença

Este projeto é **proprietário** e está licenciado pela **[RedGest](https://redgest.com.br)**.

- **Uso comercial**: Requer licença do RedGest
- **Código fonte**: Propriedade da RedGest
- **Distribuição**: Não permitida sem autorização prévia

Para questões de licenciamento, entre em contato com o provedor RedGest.

## 📈 Versões

| Versão | Data | Descrição |
|--------|------|-----------|
| **0.3.6** | 01/11/2026 | Correção PermissionError SSL, tratamento de exceções no daemon, migrations idempotentes |
| **0.3.5** | 01/11/2026 | Migração para Neon (PostgreSQL gerenciado em nuvem), PostgreSQL embarcado removido, 40% redução no tamanho do instalador |
| **0.3.4** | 31/10/2026 | Timeout de sessão, validação de integridade, fix WinError 10061 |
| **0.3.3** | 31/10/2026 | Sessão persistente, maximização |
| **0.3.2** | 31/10/2026 | Refatoração de UI, sistema de atualização |
| **0.3.1** | 30/10/2026 | Sistema de atualização, helpers de UI |
| **0.3.0** | 27/10/2026 | Projetos Kanban, PDV, Ativação |
| **0.2.2** | 16/10/2026 | Melhorias em UI/UX, correções |
| **0.2.1** | 11/10/2026 | Agendamento, correções |
| **0.2.0** | 11/10/2026 | Financeiro, Fiscal, Configuração |
| **0.1.0** | - | Versão inicial |

## 📞 Suporte

**Email**: suporte@printgest.com.br  
**WhatsApp**: (11) 9 9999-9999  
**Portal**: https://suporte.printgest.com.br

---

> PrintGest ERP — Sistema de Gestão Completo para Gráficas