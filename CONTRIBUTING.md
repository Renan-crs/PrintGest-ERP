# Contribuindo para o PrintGest ERP

Obrigado por estar interessado em contribuir para o PrintGest ERP! Esta documentação guia você através do processo de contribuição.

## 📋 Requisitos

### Ferramentas Necessárias
- **Git** 2.30+
- **Python** 3.11+
- **Node.js** 18+ (para alguns scripts frontend)
- **PostgreSQL** 14+ (para testes)
- **PowerShell** 5.1+ (Windows) ou **Bash** (Linux/Mac)

### Credenciais Necessárias
- Conta no **GitHub**
- **Token do RedGest** (para testes de licenciamento)

## 🚀 Como Começar

1. **Fork** o repositório
2. **Clone** sua fork:
   ```bash
   git clone https://github.com/[seu-usuario]/PrintGest-ERP-de-Gerenciamento-de-Gr-fica-.git
   cd PrintGest-ERP-de-Gerenciamento-de-Gr-fica-
   ```

3. **Crie uma branch**:
   ```bash
   git checkout -b feature/nova-funcionalidade
   ```

4. **Instale as dependências**:
   ```bash
   # Backend
   cd backend
   python -m venv .venv
   .venv\Scripts\activate  # Linux: source .venv/bin/activate
   pip install -r requirements.txt
   
   # Desktop
   cd ../desktop
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

## 📐 Diretrizes de Código

### Backend (Python)
- Siga o padrão **PEP 8**
- Use **type hints** em todas as funções
- Comente funções públicas com **docstrings** estilo Google
- Valide inputs em todos os endpoints
- Use **HTTPStatus** para respostas consistentes

```python
# Exemplo de função bem estruturada
def calcular_markup(vf: float, markup_pct: float = 130.0) -> float:
    """Calcula o custo a partir do VF (Preço de Venda).
    
    Args:
        vf: Preço de Venda (em centavos para precisão)
        markup_pct: Percentual de markup (padrão: 130%)
        
    Returns:
        Custo calculado (arredondado para cima)
        
    Raises:
        ValueError: Se VF for negativo
    """
    if vf < 0:
        raise ValueError("VF não pode ser negativo")
    
    cp = vf * (100 / (100 + markup_pct))
    return math.ceil(cp)
```

### Desktop (Python + PySide6)
- Use os **widgets helpers** para estados visuais:
  ```python
  from printgest.ui.widgets import estado_sucesso, estado_erro, estado_muted
  
  # Estado de sucesso
  estado_sucesso(self._lbl_status)
  
  # Estado de erro
  estado_erro(self._erro)
  ```

- Mantenha consistência em **accesibilidade**:
  ```python
  # Nome alternativo para leitores de tela
  self.setAccessibleName("Botão de salvar alterações")
  ```

### Banco de Dados
- Sempre crie **migrações Alembic** para mudanças de schema:
  ```bash
  alembicrevision -m "descricao da mudanca"
  ```

- Use **migrações reversíveis**:
  ```python
  # downgrade() deve desfazer upgrade()
  ```

## 🧪 Testes

### Estrutura de Testes
```
tests/
├── unit/          # Testes unitários
├── integration/   # Testes de integração
└── fixtures/      # Dados de teste
```

### Rodar Testes
```bash
# Backend
cd backend
pytest -v

# Desktop
cd desktop
python -m pytest -v

# With coverage
pytest --cov=app --cov-report=html
```

### Diretrizes de Teste
- **TDD**: Escreva testes antes do código
- **Mock externos**: Não dependa de RedGest real em testes
- **Dados aleatórios**: Use factories para gerar dados de teste
- **Cobertura mínima**: 80% para novas funcionalidades

## 📦 Pull Requests

### Checklist
- [ ] Branch com nome significativo (`feature/`, `fix/`, `docs/`)
- [ ] Commits com mensagens claras e formatadas
- [ ] Testes novos para funcionalidade
- [ ] Documentação atualizada
- [ ] Lint passou (`ruff check .` ou `flake8`)
- [ ] Type check passou (`mypy`)

### Formato de Commit
Use **Conventional Commits**:
```
feat: nova funcionalidade de agendamento
fix: corrigir paginação na lista de itens
docs: atualizar guia de usuario
refactor: refatorar grade de itens
test: adicionar testes para calcular_markup
```

### ABI Breaking Changes
Para mudanças de API, adicione `BREAKING CHANGE:` no commit:
```
feat!: alterar formato do endpoint /v1/os

BREAKING CHANGE: O campo `cliente_nome` foi removido da resposta
```

## 📚 Documentação

### Adicionar Documentação
- **Nova funcionalidade**: Adicione ao `docs/guia_usuario.md`
- **API nova**: Atualize `docs/api.md`
- **Arquitetura**: Atualize `docs/arquitetura.md`

### Formato Markdown
- Use headers claros (`##`, `###`)
- Listas numeradas para passos
- Blocos de código com linguagem (` ```python`)
- Links internos para seções relacionadas

## 🔐 Segurança

### Reportar Vulnerabilidade
**NÃO abra um issue público**. Envie para: **security@printgest.com.br**

### Checklist de Segurança
- [ ] Não comite credenciais (API keys, tokens)
- [ ] Valide todas as entradas de usuário
- [ ] Use prepared statements para queries
- [ ] Não exponha stack traces em produção
- [ ] Adicione rate limiting em endpoints públicos

## 📊 Métricas de Código

### Métricas Atuais
| Métrica | Valor | Meta |
|---------|-------|------|
| Cobertura de testes | 85% | 80% |
| Lint errors | 0 | 0 |
| Type errors | 0 | 0 |
| Complexidade ciclomática | < 10 | 10 |

## 🆘 Precisa de Ajuda?

- **Issues em aberto**: [GitHub Issues](https://github.com/Renan-crs/PrintGest-ERP-de-Gerenciamento-de-Gr-fica-/issues)
- **Documentação**: [docs.printgest.com.br](https://docs.printgest.com.br)
- **Suporte**: suporte@printgest.com.br

## 🧑‍contribuições de Segurança

Agradecemos a todos que nos ajudam a manter o projeto seguro!

### Reconhecimento
- Reportes válidos são listados em [docs/SECURITY.md#creditos](docs/SECURITY.md#crditos)
- Não temos política formal de recompensas

### Como Contribuir

1. Encontre uma vulnerabilidade não reportada
2. Notifique-nos responsavelmente
3. Colabore no processo de correção
4. Seja reconhecido publicamente (com seu consentimento)

---

**Obrigado por contribuir para o PrintGest ERP!** ❤️