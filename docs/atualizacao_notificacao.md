# Aviso de nova versão (Fase 1)

Implementado na v0.5.35. **Apenas notifica** — não baixa nem instala nada
automaticamente. O fluxo continua sendo: ver o aviso → clicar → abrir a página
da release no navegador → baixar e instalar.

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
   com até 3 notas. Os botões "Ver atualização" e "Mais informações" abrem a
   release no navegador via `QDesktopServices.openUrl`.

6. A checagem roda uma vez, 2 s após o dashboard, em `QThread` (`tarefas.rodar`).
   Também há a ação "Verificar atualização" no menu do usuário.

## O que deliberadamente NÃO faz

- Não descarrega nem executa o instalador.
- Não encerra desktop/API nem mexe na sessão salva.
- Não depende de licença, login ou da API local — falha de rede nunca bloqueia
  o uso do sistema (tolerância offline de 72 h continua valendo).
- Não confia em URL de domínio arbitrário vinda do manifesto.

## Próximas fases (analisadas, não implementadas)

- **Fase 2:** um clique baixa e instala. Exige certificado de code signing
  (SmartScreen), validação SHA256 do download, lançamento do instalador em
  processo destacado (o `PrepareToInstall` do `.iss` já mata desktop e API) e
  reabertura do app — o `[Run]` atual usa `skipifsilent`. Gate de RBAC no
  servidor (somente ADMIN/GERENTE) e confirmação se houver caixa aberto.
- **Fase 3:** manifesto servido pelo próprio backend para estações sem
  internet (reaproveitando a ideia do antigo `tipo=estacao|servidor`).
