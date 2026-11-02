from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import NivelAcesso, pg_enum


class Empresa(Base):
    __tablename__ = "empresa"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    razao_social: Mapped[str] = mapped_column(String(200), nullable=False)
    nome_fantasia: Mapped[str | None] = mapped_column(String(120))
    cnpj: Mapped[str] = mapped_column(CHAR(14), nullable=False, unique=True)
    inscricao_estadual: Mapped[str | None] = mapped_column(String(20))
    inscricao_municipal: Mapped[str | None] = mapped_column(String(20))
    regime_tributario: Mapped[str | None] = mapped_column(
        String(60), server_default="Simples Nacional"
    )
    ambiente_fiscal: Mapped[str] = mapped_column(CHAR(1), server_default="h")
    cnae_fiscal: Mapped[str | None] = mapped_column(String(10))
    logradouro: Mapped[str | None] = mapped_column(String(160))
    numero: Mapped[str | None] = mapped_column(String(12))
    complemento: Mapped[str | None] = mapped_column(String(80))
    bairro: Mapped[str | None] = mapped_column(String(80))
    cidade: Mapped[str | None] = mapped_column(String(80))
    uf: Mapped[str | None] = mapped_column(CHAR(2))
    cep: Mapped[str | None] = mapped_column(CHAR(8))
    telefone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(120))
    website: Mapped[str | None] = mapped_column(String(160))
    logotipo_path: Mapped[str | None] = mapped_column(String(500))
    fundo_tela_path: Mapped[str | None] = mapped_column(String(500))
    impressora_matricial: Mapped[str | None] = mapped_column(String(160))
    impressora_cupom: Mapped[str | None] = mapped_column(String(160))
    certificado_path: Mapped[str | None] = mapped_column(String(500))
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    filiais: Mapped[list["Filial"]] = relationship(back_populates="empresa")


class Filial(Base):
    __tablename__ = "filial"
    __table_args__ = (Index("idx_filial_empresa", "empresa_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("empresa.id"), nullable=False
    )
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    cnpj: Mapped[str | None] = mapped_column(CHAR(14))
    logradouro: Mapped[str | None] = mapped_column(String(160))
    numero: Mapped[str | None] = mapped_column(String(12))
    complemento: Mapped[str | None] = mapped_column(String(80))
    bairro: Mapped[str | None] = mapped_column(String(80))
    cidade: Mapped[str | None] = mapped_column(String(80))
    uf: Mapped[str | None] = mapped_column(CHAR(2))
    cep: Mapped[str | None] = mapped_column(CHAR(8))
    telefone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(120))
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    empresa: Mapped[Empresa] = relationship(back_populates="filiais")


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = (
        Index("idx_usuario_nome", "nome"),
        Index("idx_usuario_funcionario", "funcionario_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("filial.id"))
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    login: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=True)
    # M3 (§3.10): primeiro acesso - quando True, login sem senha válida pede nova senha
    primeiro_acesso: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    # Link com funcionário (preenchido pelo admin ao cadastrar)
    funcionario_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("funcionario.id")
    )
    nivel_acesso: Mapped[NivelAcesso] = mapped_column(
        pg_enum(NivelAcesso),
        nullable=False,
        server_default=NivelAcesso.OPERADOR.value,
    )
    email: Mapped[str | None] = mapped_column(String(120))
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    falhas_login: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    bloqueado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    sessoes: Mapped[list["UsuarioSessao"]] = relationship(back_populates="usuario")
    # Observação: funcionario_id é opcional para o usuário padrão
    # Funcionários podem ter um usuário de login associado


class UsuarioSessao(Base):
    __tablename__ = "usuario_sessao"
    __table_args__ = (Index("idx_sessao_usuario", "usuario_id", "expira_em"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    encerrada: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    usuario: Mapped[Usuario] = relationship(back_populates="sessoes")