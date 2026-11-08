"""Modelo local da licença — chave de produto validada online no RedGest.

O RedGest emite uma **chave de ativação** (`XXXX-XXXX-XXXX-XXXX`, Contrato C do
manual de integração — `/api/v1/licencas-software/`) que o usuário digita na
primeira execução. Esta tabela guarda a chave e o resultado da última validação
online: vigência (`expira_em`), limite de ativações e o fingerprint da máquina.
Uma única linha representa a licença da instalação.

Resiliência (`docs/plano_resiliencia_licenca.md`): a licença vale até
`expira_em`; depois disso a instalação opera em tolerância por
`licenca_tolerancia_horas` (72 h por padrão) antes do modo leitura. Falhas de
transporte nunca revogam — só uma resposta explícita do RedGest.

Colunas de fluxos anteriores (`licenca_redgest_id`, `cnpj`, `codigo_licenca`,
`token_jwt`, `token_expira_em`) seguem no schema
como anuláveis, sem uso, para não quebrar bases já migradas.
"""

from datetime import datetime

from sqlalchemy import CHAR, BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Licenca(Base):
    __tablename__ = "licenca"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    licenca_redgest_id: Mapped[str | None] = mapped_column(
        String(40), nullable=True, unique=True
    )
    sistema: Mapped[str] = mapped_column(
        String(60), nullable=False, server_default="printgest"
    )

    # Contrato C — chave de produto. Guardada **cifrada no cofre do SO** (DPAPI,
    # escopo de máquina — doc de integração §9.4): o blob tem ~385 caracteres e
    # depende do provedor, então a coluna é `Text` (linhas antigas, em texto
    # puro, seguem legíveis). O `fingerprint` é o SHA-256 canônico da máquina
    # (enviado no corpo do `/validar`).
    chave_ativacao: Mapped[str | None] = mapped_column(Text)
    maquina_fingerprint: Mapped[str | None] = mapped_column(String(64))
    expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    limite_ativacoes: Mapped[int | None] = mapped_column(Integer)
    ativacoes_realizadas: Mapped[int | None] = mapped_column(Integer)

    # Legado (fluxo `online_periodic` por CNPJ + código; sem uso no Contrato C).
    cnpj: Mapped[str | None] = mapped_column(CHAR(14), nullable=True)
    codigo_licenca: Mapped[str | None] = mapped_column(String(40), nullable=True)

    plano: Mapped[str | None] = mapped_column(String(20))
    # Status local: ativa | bloqueada | revogada | expirada.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="aguardando"
    )
    # `client_id`/`client_secret` (Contrato B, `/api/v1/licencas/`): o par M2M é
    # guardado **num único blob no cofre** (`client_id|client_secret`, DPAPI) e
    # `client_secret` é `Text` como `chave_ativacao`. `client_id` fica nulo.
    client_id: Mapped[str | None] = mapped_column(String(120))
    client_secret: Mapped[str | None] = mapped_column(Text)
    entitlements: Mapped[dict | None] = mapped_column(JSONB)
    token_jwt: Mapped[str | None] = mapped_column(Text)
    token_expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Tolerância offline: enquanto `agora <= tolerancia_expira_em` o sistema opera
    # normalmente mesmo com a vigência vencida (RedGest inacessível).
    tolerancia_expira_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # Diagnóstico (mensagem correta na UI): quando foi a última tentativa e qual
    # foi o último erro observado.
    ultima_tentativa_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    ultimo_erro: Mapped[str | None] = mapped_column(Text)
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
