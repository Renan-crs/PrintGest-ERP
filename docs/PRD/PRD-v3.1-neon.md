# PRD v3.1 — PrintGest ERP

**Sistema de Gestão para Gráfica Rápida e Pequena Gráfica** · Versão 3.1.0 · 01 de novembro de 2026 · Status: planejamento

---

## 1. Visão Geral

### 1.1 Propósito

ERP desktop (Windows) em rede local, até 5 estações, para gráficas rápidas e pequenas gráficas. Sistema migrado para **Neon Database** (PostgreSQL gerenciado em nuvem) com:

- Conexão SSL obrigatória (`sslmode=require`)
- Channel binding habilitado (`channel_binding=require`)
- PostgreSQL embarcado removido do instalador (redução de 40% no tamanho)

### 1.2 Premissas mantidas do v3.0

- Local API Service obrigatório; estações-cliente nunca acessam o PostgreSQL diretamente
- RBAC e gating de plano aplicados no servidor; o desktop apenas oculta menu
- Licenciamento online-first via RedGest, com tolerância de 72 h e modo leitura
- Valores monetários e quantidades sempre `Decimal`/`NUMERIC`, nunca `float`
- LGPD proporcional (RBAC + backup)

### 1.3 Mudanças nesta versão

| # | Mudança | Seção |
|---|---------|-------|
| 1 | **Migração para Neon Database** como banco padrão | 4.1 |
| 2 | **PostgreSQL embarcado removido** do instalador | 4.2 |
| 3 | **Correção PermissionError 13** no daemon de saúde | 6.2 |
| 4 | **Instalador mais leve**: 44.1 MB (de 77.7 MB) | 4.3 |
| 5 | **Migrations idempotentes** para reexecução segura | 6.3 |

---

## 2. Arquitetura Atualizada

### 2.1 Stack Tecnológica

| Camada | Tecnologia |
|--------|------------|
| **Backend** | FastAPI, SQLAlchemy, Neon PostgreSQL, Alembic |
| **Desktop** | PySide6, Python 3.11+ |
| **Banco** | Neon Database (PostgreSQL gerenciado em nuvem) |
| **Licenciamento** | Integração RedGest API |

### 2.2 Conexão com Neon

- **DATABASE_URL**: `postgresql://neondb_owner:...@neon.tech/neondb?sslmode=require&channel_binding=require`
- **SSL obrigatório**: Conexão comprovada via `sslmode=require`
- **Channel binding**: Proteção contra *man-in-the-middle*
- **Timeout de conexão**: 2-3 segundos (testado e otimizado)

---

## 3. Requisitos Funcionais

### 3.1 Mantidos do PRD v3.0

TODOS os requisitos do PRD v3.0 são mantidos, incluindo:

- Motor de precificação configurável
- Orçamento com fornecedor
- Custo real por OS
- Estoque por consumo
- Arte, prova e aprovação
- Produção por etapas
- Compras e cotação
- Financeiro e Fiscal completos

---

## 4. Especificações Técnicas da Migração Neon

### 4.1 Configuração de Banco de Dados

```env
# .env - Configuração Neon
PRINTGEST_DATABASE_URL=postgresql://neondb_owner:...@ep-xxx.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require
PRINTGEST_ENV=dev  # dev, local, test, producao
PRINTGEST_ADMIN_INICIAL_SENHA=SuaSenhaSegura2026!
```

### 4.2 Conexão SSL

```python
# Suporte a SSL e Channel Binding
from sqlalchemy import create_engine

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "sslmode": "require",
        "channel_binding": "require"
    }
)
```

### 4.3 PostgreSQL Embarcado Removido

**Antes (v0.3.4):**
- Instalador: 77.7 MB
- Requisito: PostgreSQL 14+ instalado localmente
- Diretório `{app}\postgres\pgsql\bin`

**Depois (v0.3.7+):**
- Instalador: 44.1 MB (40% menor)
- Banco: Neon PostgreSQL gerenciado em nuvem
- Conexão automática via DATABASE_URL

---

## 5. Instaladores e Distribuição

### 5.1 Arquivos de Instalação

| Arquivo | Tamanho | Data | Status |
|---------|---------|------|--------|
| PrintGest-Setup-0.3.7.exe | 44.1 MB | 01/11/2026 | ✅ Ativo |
| PrintGest-Setup-0.3.7Estacao.exe | 17.4 MB | 01/11/2026 | ✅ Ativo |

### 5.2 Fluxo de Instalação

1. **Download**: Usuário baixa instalador do GitHub Releases
2. **Execução**: Instalador detecta automaticamente configuração Neon
3. **Ativação**: Telaa de ativação com RedGest
4. **Login**: Primeiro login com credenciais configuradas no `.env`

---

## 6. Correções Técnicas

### 6.1 PermissionError 13 - Correção

**Problema:**
```
PermissionError: [Errno 13] Permission denied: '\\\\?\\Volume{...}\\virtual_file.log'
```

**Solução:**
```python
def saude(timeout: float = 1.0) -> bool:
    """Verifica saúde do backend com fallback de porta."""
    import httpx
    import socket
    
    try:
        httpx.get(SAUDE_URL, timeout=timeout)
        return True
    except PermissionError:
        # Fallback: verificar se porta está aberta
        return _porta_aberta(timeout)
    except OSError:
        return _porta_aberta(timeout)
    except httpx.HTTPError:
        return _porta_aberta(timeout)

def _porta_aberta(timeout: float = 1.0) -> bool:
    """Verifica se a porta 8000 está aberta via socket."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex(('127.0.0.1', 8000))
        sock.close()
        return result == 0
    except (OSError, socket.error):
        return False
```

### 6.2 Migrations Idempotentes

**Problema anterior:**
```sql
-- Falhava se valores já existiam
ALTER TYPE status_os ADD VALUE 'aguardando_arte'
```

**Correção:**
```sql
-- Torna migration reexecutável sem erro
ALTER TYPE status_os ADD VALUE IF NOT EXISTS 'aguardando_arte'
```

### 6.3 Enum Type Safety

**Problema:**
```sql
-- Type não existia antes de ser usado
ALTER TABLE ordem_servico ADD COLUMN refacao_erro refacao_erro
```

**Correção:**
```python
# Criar type antes de usá-lo
refacao_erro = sa.Enum("grafica", "cliente", name="refacao_erro")
refacao_erro.create(op.get_bind(), checkfirst=True)
```

---

## 7. Modelo de Dados

### 7.1 Tabelas Principais

| Tabela | Relacionamento |
|----------|---------------|
| `usuario` | FK para `funcionario` (campo `funcionario_id`) |
| `funcionario` | FK para `usuario` (campo `usuario_id`) |
| `ordem_servico` | Enum `status_os`, `refacao_erro` |
| `cliente` | Campo `pagamento_adiantado`, `sinal` |
| `cartao` | Enum `status_os`, `status` |

### 7.2 Nova Coluna: primeiro_acesso

```sql
ALTER TABLE usuario ADD COLUMN primeiro_acesso BOOLEAN DEFAULT FALSE;
ALTER TABLE usuario ADD COLUMN funcionario_id BIGINT REFERENCES funcionario(id);
CREATE INDEX idx_usuario_funcionario ON usuario(funcionario_id);
```

---

## 8. Plano de Implantação

### 8.1 Fase 1: Preparação (2 dias)

- [ ] Configurar DATABASE_URL Neon
- [ ] Testar conexão SSL/TLS
- [ ] Aplicar migrations no banco de teste
- [ ] Verificar backup e restore

### 8.2 Fase 2: Build Instalador (1 dia)

- [ ] Gerar PrintGestAPI.exe com backend Neon
- [ ] Compilar instalador v0.3.7
- [ ] Testar instalação limpa
- [ ] Verificar logs e erros

### 8.3 Fase 3: Deploy Produção (1 dia)

- [ ] Subir v0.3.7 no GitHub Releases
- [ ] Notificar clientes
- [ ] Monitorar conexões Neon
- [ ] Atualizar documentação

---

## 9. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| **Timeout de conexão SSL** | Médio | Alto | Timeout configurável, fallback de verificação |
| **Migrations não aplicadas** | Baixo | Médio | Migrations idempotentes, verificação prévia |
| **Permissões de firewall** | Médio | Alto | Executar como Administrador, documentação |
| **Dados locais vs nuvem** | Baixo | Alto | Planejamento de migração, backup completo |

---

## 10. Decisões Técnicas

| Decisão | Status | Data |
|---------|--------|------|
| Neon como banco padrão | ✅ Decidido | 30/10/2026 |
| PostgreSQL embarcado removido | ✅ Decidido | 30/10/2026 |
| Conexão SSL obrigatória | ✅ Decidido | 30/10/2026 |
| Channel binding habilitado | ✅ Decidido | 30/10/2026 |
| PermissionError fallback | ✅ Implementado | 01/11/2026 |

---

## 11. Glossário

| Termo | Definição |
|-------|-----------|
| **Neon** | PostgreSQL gerenciado em nuvem (neon.tech) |
| **SSLmode** | Modo SSL: `require`, `prefer`, `disable` |
| **Channel Binding** | Proteção contra ataque *man-in-the-middle* |
| **PermissionError 13** | Erro de acesso ao sistema de arquivos Windows |
| **Idempotente** | Operação que pode ser reexecutada sem efeitos colaterais |

---

## 12. Changelog

| Versão | Data | Alterações |
|--------|------|------------|
| **v0.3.7** | 01/11/2026 | Correção PermissionError SSL, migrations idempotentes |
| **v0.3.6** | 01/11/2026 | Correções de migration, ajustes finais Neon |
| **v0.3.5** | 01/11/2026 | Migração completa para Neon Database |
| **v0.3.4** | 31/10/2026 | Timeout de sessão, validação de integridade |

---

> PrintGest ERP v3.1 — Sistema de Gestão para Gráficas com Neon Database