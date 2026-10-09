"""Constantes de domínio compartilhadas entre páginas (protocolo: sem duplicação).

Valores de negócio que não pertencem a nenhuma tela em particular ficam aqui —
a UI apenas consome. O daemon continua sendo a fonte de verdade das regras;
estas listas espelham os enums aceitos pelo backend.
"""

from __future__ import annotations

FORMAS_PAGAMENTO = [
    ("dinheiro", "Dinheiro"),
    ("cartao_credito", "Cartão de Crédito"),
    ("cartao_debito", "Cartão de Débito"),
    ("pix", "PIX"),
    ("boleto", "Boleto"),
    ("fiado", "Fiado"),
]