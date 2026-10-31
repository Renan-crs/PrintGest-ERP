# Changelogs

Os changelogs oficiais estão em [CHANGELOG.md](CHANGELOG.md).

## Últimas Releases

### [0.3.2] - 2026-11-01

#### Novos Recursos
- **Sistema de notificação de atualização (M3 §3.11):** widget `NotificacaoAtualizacao`
  - Widget não bloqueante, visível e acessível
  - Endpoint `POST /v1/atualizacao/verificar` no backend
  - Método `api.verificar_atualizacao()` no cliente desktop
- **Auto-assinatura gratuita:** script `scripts/empacotar_autosign.ps1`
- **Helpers de estados visuais:** novos helpers em `widgets.py`:
  - `estado_sucesso()`, `estado_erro()`, `estado_atencao()`, `estado_muted()`
  - `estado_ghost()`, `estado_secundario()`, `estado_primario()`, `aplicar_estado()`

#### Refatoração
- **Helpers de UI:** 84 substituições de `setProperty("role", ...)` por helpers padronizados
- Padronização total de estados visuais

#### Melhorias
- IP do servidor exibido inline no header
- IP do servidor adicionado ao footer
- Tela de ativação redesenhada

#### Corrigido
- Path traversal em `arte_service.py` (M3 §3.5)

---

## Assinar

Para manter seu fork atualizado:

```bash
git fetch --tags --all
git tag -f v0.3.2  # Atualiza sua cópia local
```

## Releases Anteriores

| Versão | Data | Principais Mudanças |
|--------|------|---------------------|
| 0.3.1 | 30/10/2026 | Sistema de atualização, referência de IP |
| 0.3.0 | 27/10/2026 | M0 + M1, Projetos Kanban |
| 0.2.2 | 16/10/2026 | Paginador, agendamento |
| 0.2.1 | 11/10/2026 | Agendamento, PDF |
| 0.2.0 | 11/10/2026 | Projetos, Financeiro, Fiscal |
| 0.1.0 | - | Versão inicial |

---

**Nota:** Para ver o histórico completo, veja [CHANGELOG.md](CHANGELOG.md)