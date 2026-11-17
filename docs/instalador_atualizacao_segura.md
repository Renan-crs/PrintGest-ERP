# Atualização segura do instalador (PRD v3.3)

## Regra

> Ao instalar uma versão mais nova, o **PrintGest API deve ser encerrado** para
> a nova instalação. **Nunca perder dados de clientes.**

## Implementação (`installer/PrintGest.iss`)

1. **`PrepareToInstall`** (nova função no `[Code]`) roda **antes** de copiar
   qualquer arquivo. Se já existir `PrintGest.exe` na pasta de destino, chama
   `taskkill /F` para `PrintGestAPI.exe` e `PrintGest.exe`. Isso é necessário
   porque o Windows não permite sobrescrever `.exe`/`.dll` em uso — sem isso a
   atualização falhava ou deixava binários mistos (versão antiga + nova).
   - Primeira instalação: não há arquivo anterior, nada é encerrado.
   - O `taskkill` usa lista de argumentos curta e `ewWaitUntilTerminated`, com
     timeout de 10 s; não usa `shell` nem apaga arquivos.

2. **`[Files]` com `Excludes`**: o pacote **nunca** contém `.env`, `.env.*`,
   `*.dat` (cofres `licenca.dat`/`integracoes.dat`), `*.dump`, `*.log`,
   `backups\*` ou `logs\*`. Assim uma atualização não pode sobrescrever a
   identidade do tenant, as credenciais cifradas nem os backups.

3. **`Flags: ignoreversion`** preserva arquivos idênticos.

4. **`[UninstallDelete]`**: removidos apenas os logs. A linha que apagava
   `{app}\PrintGestAPI` inteiro foi **retirada** — ela destruía o `.env` e os
   cofres na desinstalação. O Inno Setup remove somente os arquivos que ele
   próprio instalou; arquivos criados em runtime permanecem.

## Validação automatizada

```
powershell -ExecutionPolicy Bypass -File scripts\validar_regra_instalador.ps1
```

O script falha se: `PrepareToInstall` sumir, o `taskkill` da API for removido,
os `Excludes` deixarem de proteger dados, ou a exclusão da pasta de dados
voltar a aparecer.

## Sequência segura de atualização

1. Fazer backup manual em `Configurações > Backup` (ou garantir o dump diário).
2. Executar o instalador da versão nova (ele encerra API/desktop).
3. `alembic upgrade head` é aplicado no startup da API (`PRINTGEST_AUTO_MIGRATE`);
   as migrations são aditivas e idempotentes.
4. Reabrir o PrintGest — sessão, tenant, licença e dados permanecem.
