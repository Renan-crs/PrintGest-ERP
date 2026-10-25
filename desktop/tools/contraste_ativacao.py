"""Relatório de contraste WCAG 2.1 da tela de ativação (A3).

Mede as razões realmente usadas pelo QSS (printgest/ui/theme.py, CORES) e
verifica os mínimos: texto 4,5:1; componentes/bordas 3:1. Uso:

    desktop\\.venv\\Scripts\\python.exe desktop\\tools\\contraste_ativacao.py
"""

from __future__ import annotations


def _luminancia(hex_cor: str) -> float:
    """Luminância relativa WCAG (https://www.w3.org/WAI/WCAG21/Understanding/)."""
    canal = []
    for parte in (hex_cor[1:3], hex_cor[3:5], hex_cor[5:7]):
        valor = int(parte, 16) / 255
        canal.append(valor / 12.92 if valor <= 0.04045 else ((valor + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canal[0] + 0.7152 * canal[1] + 0.0722 * canal[2]


def razao(frente: str, fundo: str) -> float:
    l1, l2 = _luminancia(frente), _luminancia(fundo)
    claro, escuro = max(l1, l2), min(l1, l2)
    return (claro + 0.05) / (escuro + 0.05)


# (nome, frente, fundo, mínimo, onde usa)
PARES = [
    ("texto/canvas", "#1D1D1F", "#F5F5F7", 4.5, "título e corpo sobre a janela"),
    ("texto/surface", "#1D1D1F", "#FFFFFF", 4.5, "texto dentro do cartão"),
    ("muted/canvas", "#6E6E73", "#F5F5F7", 4.5, "subtítulo, rodapé, tolerância 72 h"),
    ("muted/surface", "#6E6E73", "#FFFFFF", 4.5, "ajuda, placeholder (paleta)"),
    ("acao/canvas", "#0066CC", "#F5F5F7", 4.5, "botões planos (Sair/Detalhes/Tentar)"),
    ("on-primary/primary", "#FFFFFF", "#0071E3", 4.5, "botão Ativar licença (texto)"),
    ("texto/surface (secundário)", "#1D1D1F", "#FFFFFF", 4.5, "botão Testar conexão"),
    ("erro/surface", "#D70015", "#FFFFFF", 4.5, "mensagem de erro junto ao campo"),
    ("sucesso/surface", "#1B7031", "#FFFFFF", 4.5, "Servidor local: conectado"),
    ("borda-campo/surface", "#8E8E93", "#FFFFFF", 3.0, "borda dos campos de ativação"),
    ("focus/surface", "#0071E3", "#FFFFFF", 3.0, "anel de foco de 2 px"),
    ("erro/surface (borda estado)", "#D70015", "#FFFFFF", 3.0, "borda do campo com erro"),
    ("primary/canvas (dot atual)", "#0071E3", "#F5F5F7", 3.0, "indicador de passo atual"),
    ("sucesso/canvas (dot feito)", "#1B7031", "#F5F5F7", 3.0, "indicador de passo feito"),
    ("borda/canvas (dot pendente)", "#D8D8DC", "#F5F5F7", 1.0, "pendente: sem exigência (estado no texto)"),
]


def main() -> None:
    print(f"{'par':34} {'razão':>7}  {'mín':>4}  resultado  uso")
    print("-" * 100)
    falhas = 0
    for nome, frente, fundo, minimo, uso in PARES:
        valor = razao(frente, fundo)
        ok = valor >= minimo
        falhas += 0 if ok else 1
        print(
            f"{nome:34} {valor:6.2f}:1  {minimo:4.1f}  "
            f"{'OK ' if ok else 'FALHA'}      {uso}"
        )
    print("-" * 100)
    print("falhas:", falhas)


if __name__ == "__main__":
    main()
