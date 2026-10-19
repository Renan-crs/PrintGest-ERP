#!/usr/bin/env python
"""Semeia uma licença JÁ ATIVA no banco local (teste de sistema simulado).

Para o teste de sistema o time quer rodar o stack como se a chave de produto já
tivesse sido validada junto ao RedGest — sem depender do `scripts/redgest_stub.py`
nem do fluxo de ativação. Este script grava (upsert idempotente) uma linha em
`licenca` com status `ativa` e vigência de ~1 ano, o que faz:

- `GET /v1/licenca` retornar `status=ativa` e `modo_leitura=false`;
- o middleware de licença liberar escritas (sem HTTP 423);
- o `loop_renovacao` NÃO chamar o RedGest (a revalidação só ocorre a cada 6 h e a
  vigência está longe), então o RedGest continua desnecessário no ambiente de teste.

A chave semeada é a mesma do seed de `scripts/redgest_stub.py`, então o ambiente
também funciona se o stub estiver no ar.

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

from app.core import cofre
from app.core.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models.licenca import Licenca  # noqa: E402
from app.services import licensa_service  # noqa: E402

# Mesma chave do seed do `scripts/redgest_stub.py`.
CHAVE = "A3F1-9C2B-77DE-1045"
PLANO = "ANUAL"
LIMITE_ATIVACOES = 5


def _semear() -> Licenca:
    sessao = SessionLocal()
    try:
        agora = dt.datetime.now(dt.timezone.utc)
        expira = agora + dt.timedelta(days=365)
        lic = sessao.query(Licenca).order_by(Licenca.id).first()
        if lic is None:
            lic = Licenca()
            sessao.add(lic)
        # Doc de integração §9.4: a chave mora cifrada no cofre do SO.
        lic.chave_ativacao = cofre.proteger(CHAVE)
        lic.sistema = settings.redgest_sistema
        lic.plano = PLANO
        lic.status = "ativa"
        lic.expira_em = expira
        lic.tolerancia_expira_em = expira + dt.timedelta(
            hours=settings.licenca_tolerancia_horas
        )
        lic.limite_ativacoes = LIMITE_ATIVACOES
        lic.ativacoes_realizadas = 1
        lic.maquina_fingerprint = licensa_service._fingerprint()
        lic.ultima_validacao = agora
        lic.ultima_tentativa_em = agora
        lic.ultimo_erro = None
        lic.entitlements = {"origem": "semear_licenca_ativa"}
        sessao.commit()
        sessao.refresh(lic)
        return lic
    finally:
        sessao.close()


if __name__ == "__main__":
    lic = _semear()
    print("OK. Licença ativa semeada:")
    chave = licensa_service._chave_em_claro(lic)
    print(f"  chave={licensa_service._mascarar(chave)}  plano={lic.plano}")
    print(f"  status={lic.status}  limite_ativacoes={lic.limite_ativacoes}")
    print(f"  vigente ate {lic.expira_em:%Y-%m-%d %H:%M UTC}")
    print("Subir o backend SEM PRINTGEST_LICENCA_DESABILITADA agora.")
