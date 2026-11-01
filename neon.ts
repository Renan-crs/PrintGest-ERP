// Neon configuration for PrintGest ERP v0.3.4
// Projeto: nameless-wind-76828025 | Branch: production

import { defineConfig } from "@neon/config/v1";

export default defineConfig({
  // Autenticação: Managed Better Auth (habilidado)
  auth: true,
  
  // Banco de dados: PostgreSQL 18 na região aws-us-east-2
  // DATABASE_URL gerado automaticamente via dotenv
  
  // Object Storage: bucket uploads (acesso privado)
  buckets: {
    uploads: {
      access: "private",
    },
  },
  
  // AI Gateway: habilitado (precisa upgrade para uso)
  aiGateway: true,
  
  // Realtime: opcional - habilitar se precisar de queries em tempo real
  // preview: { realtime: true },
  
  // Functions: configurar quando houver APIs serverless
  // functions: {},
  
  // Configurações da branch
  branch: (branch) => {
    if (!branch.exists) {
      return {};
    }
    
    // Configurações padrão para o ambiente
    return {
      postgres: {
        // Pooler recomendado para aplicações de produção
        // Conexões escalam automaticamente conforme demanda
      },
    };
  },
});

/*
RESUMO DOS SERVICOS NEON - PrintGest ERP
========================================

BANCO DE DADOS:
- DATABASE_URL (pooler): postgresql://neondb_owner...@ep-flat-unit-b51mdu64-pooler.c-7...
- DATABASE_URL_UNPOOLED: postgresql://neondb_owner...@ep-flat-unit-b51mdu64.c-7...

AUTENTICACAO:
- Neon Auth habilitado
- Endpoints: /auth, /auth/.well-known/jwks.json

STORAGE:
- Bucket: uploads (acesso privado)
- AWS_ACCESS_KEY_ID: nak_live_4e31327135014ab781db19fed6d74c62
- AWS_ENDPOINT_URL_S3: https://br-floral-pond-b54nvxxc.storage.c-7.us-east-2.aws.neon.tech

AI GATEWAY:
- Base URL: https://br-floral-pond-b54nvxxc-api.ai.c-7.us-east-2.aws.neon.tech
- Token: nt_live_8e18b070fafb_wiIJ8VTVjFKp85L5QWWBHUZZCTzhBacc

REALTIME:
- Nao habilitado (precisa habilitar manualmente)
- URL quando habilitado: wss://br-floral-pond-b54nvxxc.rt.c-7.us-east-2.aws.neon.tech/
*/