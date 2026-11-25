# Aviso e instalação de nova versão (Fases 1 e 2)

Fase 1 implementada na v0.5.35, Fase 2 na v0.5.36. O fluxo agora é: ver o aviso
→ clicar em **Instalar atualização** → confirmar → baixar, validar e instalar.
O botão "Ver atualização" continua disponível como alternativa manual.

**O instalador ainda não é assinado**: o Windows SmartScreen pode exibir um
aviso durante a instalação. Isso é informado na confirmação e não pode ser
suprimido em código — a única correção é adquirir certificado de code signing.

## Como funciona

1. Cada build gera `dist_installer/latest.json` (sem BOM) com:

   ```json
   {
     "versao": "0.5.35",
     "arquivo": "PrintGest-Setup-0.5.35.exe",
     "sha256": "<64 hex>",
     "data": "2026-11-25",
     "url": "https://github.com/Renan-crs/PrintGest-ERP/releases/tag/v0.5.35",
     "notas": ["Instalador servidor - sem UAC, dados do cliente preservados."]
   }
   ```

   O arquivo é anexado como asset da release junto com o instalador.

2. O desktop consulta a URL fixa
   `https://github.com/Renan-crs/PrintGest-ERP/releases/latest/download/latest.json`
   (`core/atualizacao.py`), com timeout de 5 s, **fora do daemon** e sem token.

3. O manifesto é validado: versão `MAIOR.MENOR.PATCH`, nome de `.exe`, SHA-256
   com 64 hex e `url` obrigatoriamente em `github.com`. Qualquer falha (404,
   JSON inválido, rede indisponível, manifesto malformado) é logada em
   `logs/printgest.log` e vira `None` — sem exceção na UI.

4. A comparação é por tupla de inteiros (`0.5.34 < 0.5.35 < 0.6.0`); prefixo
   `v` e sufixos são ignorados.

5. Se houver versão nova, `TelaPrincipal` insere um banner amarelo não
   bloqueante no topo (mesmo padrão dos banners de modo leitura/tolerância),
   com até 3 notas. "Ver atualização" e "Mais informações" abrem a release no
   navegador via `QDesktopServices.openUrl`; "Instalar atualização" inicia a
   Fase 2.

6. A checagem roda uma vez, 2 s após o dashboard, em `QThread` (`tarefas.rodar`).
   Também há a ação "Verificar atualização" no menu do usuário.

## Fase 2 — um clique (v0.5.36)

1. **Confirmação e RBAC:** diálogo avisa que o app será reiniciado e que pode
   haver aviso do SmartScreen. No **servidor**, somente ADMIN/GERENTE pode
   instalar (a API é compartilhada pelas estações); em **estação**, qualquer
   usuário (instalação por usuário).

2. **Download:** `core/instalador_atualizacao.py` baixa o `.exe` para
   `%LOCALAPPDATA%\PrintGest\updates`, com stream, limite de 200 MB e validação
   do SHA-256 do manifesto **antes de qualquer execução**. Se o arquivo já
   existe e o hash confere, é reaproveitado. Hash divergente → nada é executado.

3. **Disparo:** o Setup é lançado com `/VERYSILENT /NORESTART` em processo
   destacado (`DETACHED_PROCESS | CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`).
   Isso é obrigatório porque o `PrepareToInstall` do `.iss` encerra
   `PrintGest.exe` e `PrintGestAPI.exe` — o processo que disparou o download
   não pode ser o desktop.

4. **Reabertura:** a `[Run]` do `.iss` teve o sinalizador `skipifsilent`
   removido, então o app é reaberto ao fim da instalação silenciosa.

5. **Falhas:** qualquer erro (HTTP, rede, hash, arquivo ausente) gera aviso com
   opção de baixar manualmente; nada é executado e a sessão local não é tocada.

## O que deliberadamente NÃO faz

- Não descarrega nem executa o instalador.
- Não encerra desktop/API nem mexe na sessão salva.
- Não depende de licença, login ou da API local — falha de rede nunca bloqueia
  o uso do sistema (tolerância offline de 72 h continua valendo).
- Não confia em URL de domínio arbitrário vinda do manifesto.

## Pendências

- **Code signing:** sem certificado, o SmartScreen pode bloquear o instalador
  baixado; pipeline e `-Assinar` já estão prontos, falta adquirir o certificado.
- **Fase 3 (proposta):** manifesto servido pelo próprio backend para estações
  sem internet (reaproveitando a ideia do antigo `tipo=estacao|servidor`).
