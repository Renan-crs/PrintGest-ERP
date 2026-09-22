"""Modelo local da licença do sistema junto ao RedGest (`online_periodic`).

Guarda o vínculo ativo (CNPJ + código + credenciais retornadas na ativação) e o
último JWT validado, para que o serviço renove por polling em `/validar` e negocie
o modo de leitura quando o token expira (PRD v2.0 §3). Uma única linha representa
a licença da instalação.
"""

from datetime import datetime

from sqlalchemy import BigInteger, CHAR, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Licenca(Base):
    __tablename__ = "licenca"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    licenca_redgest_id: Mapped[str] = mapped_column(
        String(40), nullable=False, unique=True
    )
    sistema: Mapped[str] = mapped_column(
        String(60), nullable=False, server_default="grafica_erp"
    )
    cnpj: Mapped[str] = mapped_column(CHAR(14), nullable=False)
    codigo_licenca: Mapped[str] = mapped_column(String(40), nullable=False)
    plano: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="aguardando"
    )
    client_id: Mapped[str | None] = mapped_column(String(120))
    client_secret: Mapped[str | None] = mapped_column(String(255))
    entitlements: Mapped[dict | None] = mapped_column(JSONB)
    token_jwt: Mapped[str | None] = mapped_column(Text)
    token_expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultima_validacao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )