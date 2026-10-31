# Changelogs

Os changelogs oficiais estão em [CHANGELOG.md](CHANGELOG.md).

## Últimas Releases

### [0.3.3] - 2026-11-01

#### Novos Recursos
- **Sessão persistente:** sessão do usuário não expira entre reinicializações do computador
  - Token e dados de usuário são salvos localmente após login
  - Sessão é limpa automaticamente quando o usuário clica em "Sair"
  - Aguarda daemon estar pronto antes de restaurar (evita WinError 10061)
- **Janelas maximizadas:** todas as janelas abrem maximizadas, respeitando a barra do Windows automaticamente

#### Corrigido
- WinError 10061: sessão salva espera daemon estar saudável antes de tentar conectar

### [0.3.2] - 2026-11-01

#### Novos Recursos
- **Sistema de notificação de atualização (M3 §3.11):** widget `NotificacaoAtualizacao`
- **Auto-assinatura gratuita:** script `scripts/empacotar_autosign.ps1`
- **Helper methods para estados visuais:** `estado_sucesso()`, `estado_erro()`, etc.

#### Refatoração
- **Helpers de UI:** 84 substituições de `setProperty("role", ...)` por helpers

### [0.3.1] - 2026-10-30

- Sistema de atualização, referência de IP

---

## Instaladores

| Versão | Servidor | Estação |
|--------|----------|---------|
| 0.3.3 | 77.7 MB | 37.9 MB |
| 0.3.2 | 77.7 MB | 37.9 MB |

## Assinar

Para manter seu fork atualizado:

```bash
git fetch --tags --all
git tag -f v0.3.3  # Atualiza sua cópia local
```

## Releases Anteriores

| Versão | Data | Principais Mudanças |
|--------|------|---------------------|
| 0.3.3 | 31/10/2026 | Sessão persistente, maximização |
| 0.3.2 | 31/10/2026 | Refatoração de UI, sistema de atualização |
| 0.3.1 | 30/10/2026 | Sistema de atualização, helpers de UI |
| 0.3.0 | 27/10/2026 | Projetos Kanban, PDV, Ativação |
| 0.2.2 | 16/10/2026 | Paginador, agendamento |
| 0.2.1 | 11/10/2026 | Agendamento, PDF |
| 0.2.0 | 11/10/2026 | Primeiro release completo |
| 0.1.0 | - | Versão inicial |

---

**Nota:** Para ver o histórico completo, veja [CHANGELOG.md](CHANGELOG.md)