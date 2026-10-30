"""Schemas Pydantic dos cadastros (clientes, fornecedores, funcionários, produtos/categorias)."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field, model_validator

from app.models.enums import TipoPessoa, TipoProduto
from app.schemas.common import ORMModel


class EnderecoBase(ORMModel):
    logradouro: str | None = Field(default=None, max_length=160)
    numero: str | None = Field(default=None, max_length=12)
    complemento: str | None = Field(default=None, max_length=80)
    bairro: str | None = Field(default=None, max_length=80)
    cidade: str | None = Field(default=None, max_length=80)
    uf: str | None = Field(default=None, max_length=2)
    cep: str | None = Field(default=None, max_length=8)


class ClienteBase(EnderecoBase):
    tipo_pessoa: TipoPessoa = TipoPessoa.PF
    nome_razao: str = Field(min_length=1, max_length=200)
    cpf_cnpj: str | None = Field(default=None, max_length=18)
    inscricao_estadual: str | None = Field(default=None, max_length=20)
    data_nascimento: date | None = None
    email: str | None = Field(default=None, max_length=120)
    telefone: str | None = Field(default=None, max_length=20)
    celular: str | None = Field(default=None, max_length=20)
    foto_path: str | None = Field(default=None, max_length=500)
    observacoes: str | None = None
    pagamento_adiantado: bool = False
    sinal: bool = False
    sinal_pct: Decimal = Field(default=Decimal("50"), ge=0, le=100)

    @model_validator(mode="after")
    def _adiantamento_exclusivo(self) -> "ClienteBase":
        if self.pagamento_adiantado and self.sinal:
            raise ValueError(
                "O cliente não pode ser 'pagamento adiantado' e 'sinal' ao mesmo tempo."
            )
        return self


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(ClienteBase):
    nome_razao: str | None = Field(default=None, min_length=1, max_length=200)


class ClienteOut(ClienteBase):
    id: int
    filial_id: int
    ativo: bool
    created_at: datetime
    updated_at: datetime


class FornecedorBase(EnderecoBase):
    tipo_pessoa: TipoPessoa = TipoPessoa.PJ
    nome_razao: str = Field(min_length=1, max_length=200)
    cpf_cnpj: str | None = Field(default=None, max_length=18)
    inscricao_estadual: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=120)
    telefone: str | None = Field(default=None, max_length=20)
    celular: str | None = Field(default=None, max_length=20)
    contato_nome: str | None = Field(default=None, max_length=120)
    observacoes: str | None = None


class FornecedorCreate(FornecedorBase):
    pass


class FornecedorUpdate(FornecedorBase):
    nome_razao: str | None = Field(default=None, min_length=1, max_length=200)


class FornecedorOut(FornecedorBase):
    id: int
    filial_id: int
    ativo: bool
    created_at: datetime
    updated_at: datetime


class FuncionarioBase(ORMModel):
    nome: str = Field(min_length=1, max_length=120)
    cpf: str | None = Field(default=None, max_length=18)
    cargo: str | None = Field(default=None, max_length=60)
    email: str | None = Field(default=None, max_length=120)
    telefone: str | None = Field(default=None, max_length=20)
    data_nascimento: date | None = None
    data_admissao: date | None = None
    e_vendedor: bool = False
    e_atendente: bool = False
    e_producao: bool = False
    comissao_pct: Decimal | None = Field(default=Decimal("0"), ge=0, le=100)
    observacoes: str | None = None
    # M3 (§3.10): login do funcionário (fornecido pelo admin)
    login: str | None = Field(default=None, min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9_.-]+$")


class FuncionarioCreate(FuncionarioBase):
    login: str = Field(min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9_.-]+$")


class FuncionarioUpdate(FuncionarioBase):
    nome: str | None = Field(default=None, min_length=1, max_length=120)


class FuncionarioOut(FuncionarioBase):
    id: int
    filial_id: int
    ativo: bool
    login: str | None = None
    created_at: datetime
    updated_at: datetime


class CategoriaBase(ORMModel):
    nome: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=255)


class CategoriaCreate(CategoriaBase):
    pass


class CategoriaUpdate(CategoriaBase):
    nome: str | None = Field(default=None, min_length=1, max_length=80)


class CategoriaOut(CategoriaBase):
    id: int
    ativo: bool
    created_at: datetime
    updated_at: datetime


class ProdutoBase(ORMModel):
    categoria_id: int | None = None
    codigo: str = Field(min_length=1, max_length=30)
    codigo_barras: str | None = Field(default=None, max_length=30)
    nome: str = Field(min_length=1, max_length=160)
    descricao: str | None = None
    tipo: TipoProduto = TipoProduto.PRODUTO
    unidade: str = Field(default="un", max_length=12)
    controla_estoque: bool = True
    preco_custo: Decimal = Field(default=Decimal("0"), ge=0)
    preco_venda: Decimal = Field(default=Decimal("0"), ge=0)
    estoque_minimo: Decimal = Field(default=Decimal("0"), ge=0)
    dimensoes: str | None = Field(default=None, max_length=40)
    foto1_path: str | None = Field(default=None, max_length=500)
    foto2_path: str | None = Field(default=None, max_length=500)
    bloqueado_reajuste: bool = False


class ProdutoCreate(ProdutoBase):
    pass


class ProdutoUpdate(ProdutoBase):
    codigo: str | None = Field(default=None, min_length=1, max_length=30)
    nome: str | None = Field(default=None, min_length=1, max_length=160)


class ProdutoOut(ProdutoBase):
    id: int
    filial_id: int
    ativo: bool
    created_at: datetime
    updated_at: datetime


class ProdutoEstoqueOut(ORMModel):
    id: int
    produto_id: int
    filial_id: int
    saldo: Decimal
    reservado: Decimal
    atualizado_em: datetime