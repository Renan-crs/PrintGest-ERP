#!/usr/bin/env python
"""Semeia uma licença JÁ ATIVA no banco local (teste de sistema simulado).

Para o teste de sistema o time quer rodar o stack como se a licença já tivesse
sido ativada junto ao RedGest — sem depender do `scripts/redgest_stub.py` nem do
fluxo de ativação. Este script grava (upsert idempotente) uma linha em `licenca`
com status `ativa` e token válido por ~1 ano, o que faz:

- `GET /v1/licenca` retornar `status=ativa` e `modo_leitura=false`;
- o middleware de licença liberar escritas (sem HTTP 423);
- o `loop_renovacao` NÃO tentar renovar (expiração longe demais), então o
  RedGest continua desnecessário no ambiente de teste.

Uso (com o Postgres portable da `.dev` no ar):

    backend\\.venv\\Scripts\\python.exe scripts\\semear_licenca_ativa.py

Depois é só subir o backend SEM `PRINTGEST_LICENCA_DESABILITADA`:

    $env:PRINTGEST_LICENCA_DESABILITADA=""
    backend\\.venv\\Scripts\\python.exe backend\\run_dev.py
"""

import datetime as dt
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models.licenca import Licenca  # noqa: E402

LICENCA_REDGEST_ID = "lic-printgest-teste-sistema"
CNPJ = "11111111000111"  # mesmo CNPJ do bootstrap (Empresa demo)
CODIGO = "TESTE-SISTEMA-0001"
MODULOS = [
    "vendas",
    "producao",
    "estoque",
    "financeiro",
    "cadastros",
    "relatorios",
]
PLANO = "essencial"


def _semear() -> Licenca:
    db = SessionLocal()
    try:
        lic = db.query(Licenca).filter(Licenca.cnpj == CNPJ).order_by(Licenca.id).first()
        agora = dt.datetime.now(dt.timezone.utc)
        if lic is None:
            lic = Licenca(
                licenca_redgest_id=LICENCA_REDGEST_ID,
                sistema=settings.redgest_sistema,
                cnpj=CNPJ,
                codigo_licenca=CODIGO,
            )
            db.add(lic)
        else:
            lic.licenca_redgest_id = LICENCA_REDGEST_ID
            lic.codigo_licenca = CODIGO
        lic.plano = PLANO
        lic.status = "ativa"
        lic.client_id = "teste-sistema-client"
        lic.client_secret = "teste-sistema-secret"
        lic.entitlements = {
            "cnpj_vinculado": CNPJ,
            "max_estacoes": 5,
            "modulos_habilitados": MODULOS,
        }
        # Token fictício: o JWT só é armazenado, nunca validado localmente.
        lic.token_jwt = "jwt.teste.sistema"
        lic.token_expira_em = agora + dt.timedelta(days=366)
        lic.ultima_validacao = agora
        db.add(lic)
        db.commit()
        db.refresh(lic)
        return lic
    finally:
        db.close()


if __name__ == "__main__":
    lic = _semear()
    expira = lic.token_expira_em.strftime("%Y-%m-%d %H:%M UTC")
    print(f"OK. Licença ativa semeada:")
    print(f"  cnpj={lic.cnpj}  codigo={lic.codigo_licenca}  plano={lic.plano}")
    print(f"  status={lic.status}  modulos={len(MODULOS)}")
    print(f"  token valido ate {expira}")
    print("Subir o backend SEM PRINTGEST_LICENCA_DESABILITADA agora.")