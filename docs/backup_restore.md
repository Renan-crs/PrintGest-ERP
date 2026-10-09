# Backup e Recuperação (DR) — PrintGest

Protocolo 19 (Resiliência de Dados e Backup/Disaster Recovery).

## Objetivo

- **RPO** (perda máxima aceitável de dados): 24h em operação normal; a definir
  junto ao cliente para quem exigir menos.
- **RTO** (tempo de recuperação): < 1h para o banco local (dump custom restaurado).

## Rotina

| Item | Como |
| --- | --- |
| Gerar backup | `powershell -ExecutionPolicy Bypass -File scripts/backup_postgres.ps1` |
| Restaurar | `powershell -ExecutionPolicy Bypass -File scripts/restore_postgres.ps1 -Arquivo <dump> -Recriar` |
| Destino padrão | `.dev/backups/printgest_<AAAAMMDD_HHMMSS>.dump` (formato custom do `pg_dump`) |

Os scripts usam os binários do PostgreSQL portable em
`.dev/postgres/pgsql/bin` (ver `scripts/setup_postgres.ps1`).

## Boas práticas operacionais

1. **Frequência**: 1 backup diário completo; em fechamento de mês, guardar cópia
   imutável (fora da máquina, ex.: nuvem/HD externo).
2. **Retenção**: manter ao menos 7 diários, 4 semanais e 12 mensais.
3. **Verificação**: restaurar o dump periodicamente em banco de teste
   (`pg_restore -d printgest_restore`) para validar a integridade.
4. **Antes de migrações**: rodar `backup_postgres.ps1` antes de aplicar
   `alembic upgrade head`.
5. **Segredos**: os dumps contêm dados de clientes e hashes de senha — armazenar
   criptografados e com acesso restrito.

## Teste de restauração (recomendado)

```powershell
# 1) Backup
powershell -ExecutionPolicy Bypass -File scripts/backup_postgres.ps1

# 2) Restaurar em banco separado para conferência
.\.dev\postgres\pgsql\bin\createdb.exe -h 127.0.0.1 -U printgest printgest_restore
.\.dev\postgres\pgsql\bin\pg_restore.exe -h 127.0.0.1 -U printgest -d printgest_restore .dev\backups\<dump>
```
