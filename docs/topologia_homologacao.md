# Topologia de homologação — 1 servidor + N estações

Aplicável a qualquer ambiente com vários PCs (homologação ou produção).

## Regra de ouro

**Um servidor por CNPJ/licença.** A chave de ativação (Contrato B) tem cota de
ativações (`limite_ativacoes`, normalmente **1**) e o RedGest vincula a licença
ao hardware da primeira máquina que valida. Ao tentar ativar num segundo PC, o
servidor de licenças responde `409` — "Licença já possui ativação ativa" /
"Limite de ativações atingido". Insistir não é erro de digitação: uma segunda
ativação **invalida a primeira** e exige **reset M2M no RedGest** (suporte), que
não é uma operação local.

Além disso, cada `/validar` **rotaciona o `client_secret` M2M**. Duas máquinas
validando a mesma licença se invalidam mutuamente: a última vence, a outra cai em
403 e pede novo reset. O cofre local (`%LOCALAPPDATA%\PrintGest\licenca.dat`)
usa **DPAPI com escopo de máquina** — não pode ser copiado entre PCs.

**Consequência:** os demais computadores são **Estações**. Eles não ativam
licença, não sobem daemon e apenas consomem a API do servidor pela rede.

## Layout recomendado (exemplo de homologação)

| Máquina | Sistema | Papel |
|---|---|---|
| ArtBalcão ren | Windows 10 | **Servidor** (licença ativada aqui) |
| Art03 rede | Windows 11 | Estação |
| Art02 | Windows 10 | Estação |
| Art04 (notebook) | Windows 11 | Estação |
| Desktop 3 (inativo) | — | Estação (não conta no limite de 7 dias) |

Limite padrão de estações ativas: **5** (`estacao_service.LIMITE_PADRAO`). Com
4 ativos + 1 inativo, o ambiente cabe sem ajuste.

## 1. Configurar o servidor (ArtBalcão)

1. Edite o `.env` ao lado de `PrintGestAPI.exe`:
   ```
   %LOCALAPPDATA%\Programs\PrintGest\PrintGestAPI\.env
   ```
   Troque/inclua:
   ```
   PRINTGEST_API_HOST=<IP fixo do ArtBalcão na LAN>
   ```
   Use o IP fixo da máquina (mais seguro que `0.0.0.0`; este último só se
   realmente precisar escutar em todas as interfaces). A porta permanece
   **8000/TCP**.
2. Reinicie o daemon: feche e abra o PrintGest, ou encerre `PrintGestAPI.exe`
   no Gerenciador de Tarefas.
3. Libere a **TCP 8000** no firewall do Windows e no Kaspersky para a rede
   local. O servidor continua com o banco Neon e a licença ativada.
4. Confira:
   ```bat
   curl http://127.0.0.1:8000/health
   curl http://127.0.0.1:8000/v1/licenca
   ```

## 2. Instalar as estações

1. Desinstale qualquer instalação **Servidor** nas outras máquinas. A
   desinstalação **preserva os dados do cliente** (eles ficam no Neon); só sai
   a configuração local.
2. Execute `PrintGest-Setup-<versao>Estacao.exe` (ex.:
   `PrintGest-Setup-0.5.46Estacao.exe`). O assistente pede o
   endereço do servidor — informe:
   ```
   http://<IP-do-ArtBalcão>:8000
   ```
3. **Não digite chave de ativação** — ela é do servidor. Faça login com um
   usuário criado no servidor.
4. Repita para Art03, Art02, Art04 e o desktop inativo.

A estação registra-se automaticamente como estação no servidor. Ela não
processa licença local, não executa migrations e não grava `licenca.dat`.

### Atualizações
- **Servidor:** usa o aviso de nova versão no dashboard e instala o Setup
  servidor.
- **Estação:** **não** consulta `latest.json` (o manifesto descreve o pacote
  servidor). Para atualizar, reinstale com o pacote Estação da nova versão.

## 3. Kaspersky

Não desligue o antivírus. Primeiro consulte a quarentena e os logs de execução
bloqueada; se houver bloqueio, adicione **exclusões por caminho**:

```
%LOCALAPPDATA%\Programs\PrintGest\
%LOCALAPPDATA%\Programs\PrintGest\PrintGestAPI\_internal\
%LOCALAPPDATA%\Programs\PrintGestEstacao\
%LOCALAPPDATA%\PrintGest\
```

O gerador de fingerprint de hardware chama `powershell.exe -ExecutionPolicy
Bypass` e usa CIM/WMI; bloqueios aqui fazem o perfil cair para
`{arquitetura, processador}` e divergir do servidor (`hardware_divergente →
rebind necessário`). Os binários são PyInstaller onedir (exes não assinados
ainda) e usam DPAPI — ambos são alvos comuns de heurística de AV.

## 4. Diagnóstico (somente leitura)

Em uma máquina com falha:

```bat
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/v1/licenca
netstat -ano | findstr :8000
tasklist /FI "IMAGENAME eq PrintGestAPI.exe"
```

Logs:
- `%LOCALAPPDATA%\Programs\PrintGest\PrintGestAPI\logs\printgest-api.log`
- `%LOCALAPPDATA%\Programs\PrintGest\PrintGest\logs\printgest.log`

Na interface (admin): **Configurações → Diagnóstico → Copiar diagnóstico**.
O pacote copiado não traz `motivo`/`ultimo_erro`; complemente com o `curl
/v1/licenca` e com `printgest-api.log`. Use **v0.5.46 ou superior** — nela os
logs do uvicorn passaram a ser gravados em arquivo.

Para ver o console do daemon (spec mantém `console=True`), execute
`PrintGestAPI.exe` manualmente pelo Explorador.

## Não fazer

- Não ativar a mesma chave em duas máquinas nem alternar ativações.
- Não copiar `.env`, `licenca.dat` ou blobs DPAPI entre PCs.
- Não rodar `scripts/limpar_licenca.py` nem migrations manuais em máquina de
  cliente.
- Não apontar uma estação para `latest.json` (já bloqueado no código na
  v0.5.46).

Se for inevitável ter **dois servidores**, serão necessários dois CNPJs/tenant e
duas licenças, com rebind gerenciado no RedGest.
