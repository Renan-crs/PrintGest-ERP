# Política de Segurança

Este documento descreve nossa política de segurança e como reportar vulnerabilidades.

## 🛡️ Segurança do Projeto

O PrintGest ERP implementa diversas medidas de segurança para proteger dados dos usuários e do sistema:

### Controles de Acesso
- **Autenticação** baseada em tokens JWT validados pelo RedGest
- **Autorização** granular por níveis: Admin, Gerente, Operador
- **Primeiro acesso** com definição obrigatória de senha
- **Modo leitura** quando licença expirada

### Proteção de Dados
- **Criptografia** de credenciais no cofre do SO (DPAPI)
- **Hash SHA-256** para fingerprint de máquinas
- **Não armazenamento** de senhas em texto plano
- **Logs** controlados sem dados sensíveis

### Validação e Sanitização
- **Validação de input** em todos os endpoints da API
- **Negativa de arte** para extensões executáveis (.exe, .bat, .dll, .js, etc.)
- **Tamanho máximo** de arquivos (50 MB)
- **Path traversal** corrigido em uploads de arte

### Rede e Conexão
- **HTTPS** obrigatório para comunicação com RedGest
- **Timeout configurável** para requisições (90s)
- **Back-off progressivo** em falhas de rede
- **Tolerância de 72h** offline

## 🔍 Reportando Vulnerabilidades

### Procedimento Responsável

**Não abra issues públicos** para vulnerabilidades de segurança. Em vez disso, siga este processo:

1. **Envie um e-mail** para: **security@printgest.com.br**
   - Assunto: `[SECURITY] Vulnerabilidade no PrintGest ERP`

2. **Inclua as seguintes informações**:
   - Descrição detalhada da vulnerabilidade
   - Passos para reproduzir o problema
   - Impacto e escopo
   - Versão afetada
   - Possíveis sugestões de correção

3. **Aguarde nosso contato** (idealmente dentro de 48 horas)

4. **Trabalhe conosco** para corrigir o problema

### O que Consideramos Vulnerabilidades

- ✗ **Autenticação**: Bypass, força bruta, vazamento de credenciais
- ✗ **Autorização**: Escalonamento de privilégios, acesso indevido
- ✗ **Injeção**: SQL, comando, path traversal
- ✗ **Confidencialidade**: Vazamento de dados, informações sensíveis
- ✗ **Integridade**: Modificação indevida de dados
- ✗ **Disponibilidade**: DoS, condições de corrida
- ✗ **Criptografia**: Fracassos de encriptação, mãe de cachorro (weak crypto)

### O que NÃO Consideramos

- ✗ **Problemas de usability** que não envolvem segurança
- ✗ **Erros de UI/UX** sem impacto de segurança
- ✗ **Problemas menores** que não possam ser explorados
- ✗ **Vulnerabilidades já reportadas** em issues fechadas
- ✗ **Problemas em dependências** que já temos patches

## 🚨 Resposta a Incidentes

### Timeline de Resposta

| Ação | Prazo |
|------|-------|
| Confirmação do receipt | 48h |
| Avaliação inicial | 7 dias úteis |
| Patch de correção | 14-30 dias (dependendo da complexidade) |
| Divulgação responsável | Após patch disponível |

### Processo de Correção

1. **Triagem**: Equipe de segurança analisa o relato
2. **Validação**: Reproduzimos a vulnerabilidade
3. **Priorização**: Classificamos por impacto (Baixo/Médio/Alto/Crítico)
4. **Correção**: Desenvolvemos patch em branch segura
5. **Teste**: Validamos correção sem quebrar funcionalidades
6. **Release**: Incluímos em próxima versão
7. **Divulgação**: Notificamos reporter e divulgamos (se aplicável)

## 🧪 Testes de Segurança

### Scan de Vulnerabilities
- **Dependências**: Scans automatizados com `pip-audit` e dependabot
- **Código**: Revisões manuais e ferramentas estáticas
- **Integração**: CI/CD com checks de segurança

### Recomendações para Deploy

- ✅ **Ambiente de produção**: Nunca expor diretamente ao público
- ✅ **HTTPS**: Usar certificado válido (Let's Encrypt ou similar)
- ✅ **Firewall**: Restringir acesso à porta do PostgreSQL (5432)
- ✅ **Variáveis sensíveis**: Nunca commitar no código
- ✅ **Logs**: Configurar rotação e retenção apropriadas

## 📋 Lista de Verificação de Segurança

### Pré-Deploy
- [ ] Variáveis de ambiente sensíveis configuradas
- [ ] HTTPS configurado com certificado válido
- [ ] PostgreSQL restrito a IPs autorizados
- [ ] Token do RedGest validado
- [ ] Backup configurado
- [ ] Monitoramento de logs em funcionamento

### Pós-Deploy
- [ ] Teste de conexão segura
- [ ] Verificação de permissões de arquivos
- [ ] Monitoramento de recursos
- [ ] Documentação atualizada

## 🤝 Contribuições de Segurança

Agradecemos a todos que nos ajudam a melhorar a segurança do projeto!

### Reconhecimento

- Reportes válidos são destacados em nossa [página de contribuições](docs/CONTRIBUTING.md#contribuicoes-de-seguranca)
- Nós tentamos contatar reportes via e-mail, mas não temos política formal de recompensas

### Créditos

Até a data, não temos histórico público de vulnerabilidades corrigidas.

---

**Última atualização**: 31/10/2026  
**Versão**: 0.3.2