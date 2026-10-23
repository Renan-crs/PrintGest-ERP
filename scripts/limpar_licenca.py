#!/usr/bin/env python
"""Remove a licença local — simula uma REINSTALAÇÃO (volta a pedir o serial).

Como em programas licenciados por serial, a tela de ativação só aparece quando
não há licença na instalação. Na prática isso acontece numa instalação nova
(banco sem a linha em `licenca`). Este script reproduz esse estado sem apagar o
resto do banco: remove a linha de `licenca` — junto com ela vai o blob cifrado da
chave/credenciais, que é gravado nas colunas dessa linha — de modo que o próximo
`GET /v1/licenca` retorne `status=nao_ativada` e o desktop abra a tela de serial
antes do login.

Uso (com o Postgres portable da `.dev` no ar):

    backend\\.venv\\Scripts\\python.exe scripts\\limpar_licenca.py --sim

Sem `--sim` o script apenas mostra o que faria (dry-run).
"""

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.db import SessionLocal  # noqa: E402
from app.models.licenca import Licenca  # noqa: E402


def _limpar(confirmar: bool) -> int:
    sessao = SessionLocal()
    try:
        linhas = sessao.query(Licenca).all()
        if not linhas:
            print("Nenhuma licença local encontrada (já está no estado de instalação).")
            return 0
        for lic in linhas:
            print(
                f"  licenca id={lic.id} sistema={lic.sistema} status={lic.status}"
                + (" -> removida" if confirmar else " -> seria removida")
            )
        if confirmar:
            for lic in linhas:
                sessao.delete(lic)
            sessao.commit()
        return len(linhas)
    finally:
        sessao.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sim",
        action="store_true",
        help="confirma a remoção (sem esta opção é apenas dry-run)",
    )
    args = parser.parse_args()

    encontradas = _limpar(confirmar=args.sim)
    if not args.sim:
        print("Dry-run: nada foi alterado. Repita com --sim para remover a licença.")
        sys.exit(0)

    print(f"OK. {encontradas} licenca(s) removida(s).")
    print("Abra o desktop: a tela de serial será exibida antes do login.")
