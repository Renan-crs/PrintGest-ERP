# Tokens de design do PrintGest (claro/escuro) + mapeamento WPF

Fonte única para o QSS atual (`desktop/printgest/ui/theme.py`, `CORES`) e
referência para a migração WPF/.NET 10 (PRD v2.3, fase M1). Tema escuro é
**proposta medida** (razões verificadas; implementação fica pendente — P6).
Razões WCAG medidas por `desktop/tools/contraste_ativacao.py`.

## Tabela de tokens

| Token | Claro | Escuro (proposta) | Uso | Razão (claro) |
| --- | --- | --- | --- | --- |
| canvas | #F5F5F7 | #1C1C1E | fundo de janela | texto 15,46:1 |
| surface | #FFFFFF | #2C2C2E | cartões, campos | texto 16,83:1 |
| surface-muted | #F5F5F7 | #3A3A3C | hover/repouso de controles | — |
| borda | #D8D8DC | #38383A | hairline de cartões/separadores | 1,35:1 (decorativo) |
| borda-forte | #C7C7CC | #48484A | hover de contornos genéricos | — |
| borda-campo | #8E8E93 | #8A8A91 | borda de campo de formulário crítico (≥ 3:1) | 3,26:1 |
| texto | #1D1D1F | #F5F5F7 | texto principal | 16,83:1 |
| texto-muted | #6E6E73 | #98989F | secundário, ajuda, placeholder | 5,07:1 |
| primary | #0071E3 | #005BB8 | ação primária (fundo) | branco 4,70:1 |
| primary-hover | #0077ED | #3076C9 | hover da ação primária | — |
| primary-active | #0068C8 | #2A66AC | pressionado | — |
| primary-container | #EAF3FF | #0B3B66 | tint de seleção | — |
| on-primary | #FFFFFF | #FFFFFF | texto sobre primary | — |
| acao | #0066CC | #66B2FF | texto/botões planos sobre canvas | 5,11:1 (claro) / 7,60:1 (escuro) |
| focus | #0071E3 | #66B2FF | anel de foco 2 px | 4,70:1 / 6,22:1 |
| sucesso | #1B7031 | #66C17A | texto de sucesso | 6,16:1 / 6,29:1 |
| sucesso-container | #E3F3E7 | #0E3D1E | fundo de sucesso | — |
| atencao | #B25000 | #FFB340 | texto de atenção | (escopo: badges de outras telas) |
| atencao-container | #FFF4E8 | #3D2A10 | fundo de atenção | — |
| erro | #D70015 | #FF6966 | erro (texto e borda) | 5,38:1 / 4,95:1 |
| erro-container | #FCEEEE | #3A1113 | fundo de erro | — |
| erro-borda | #F2B8BC | #7A2B30 | borda de erro suave | — |

Tipografia (Inter; Segoe UI na migração): título 24/700 (-0,02em), título de
cartão 20/700, corpo 13–14/400 (entrelinha 1,4–1,5), rótulo de campo 13/600
sentence case, auxiliar 12/400, botão 14/600.

Espaçamentos: 4/8/12/16/24/32/48. Raios: controles 6–8, cartões 12. Botões com
altura ≥ 40 px; anel de foco 2 px.

## Mapeamento WPF (ResourceDictionary)

```xml
<!-- Resources/DesignTokens.xaml -->
<ResourceDictionary
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    xmlns:sys="clr-namespace:System;assembly=mscorlib">

    <Color x:Key="CanvasColor">#F5F5F7</Color>
    <Color x:Key="SurfaceColor">#FFFFFF</Color>
    <Color x:Key="SurfaceMutedColor">#F5F5F7</Color>
    <Color x:Key="BordaColor">#D8D8DC</Color>
    <Color x:Key="BordaForteColor">#C7C7CC</Color>
    <Color x:Key="BordaCampoColor">#8E8E93</Color>
    <Color x:Key="TextoColor">#1D1D1F</Color>
    <Color x:Key="TextoMutedColor">#6E6E73</Color>
    <Color x:Key="PrimaryColor">#0071E3</Color>
    <Color x:Key="PrimaryHoverColor">#0077ED</Color>
    <Color x:Key="PrimaryActiveColor">#0068C8</Color>
    <Color x:Key="PrimaryContainerColor">#EAF3FF</Color>
    <Color x:Key="OnPrimaryColor">#FFFFFF</Color>
    <Color x:Key="AcaoColor">#0066CC</Color>
    <Color x:Key="FocusColor">#0071E3</Color>
    <Color x:Key="SucessoColor">#1B7031</Color>
    <Color x:Key="SucessoContainerColor">#E3F3E7</Color>
    <Color x:Key="AtencaoColor">#B25000</Color>
    <Color x:Key="AtencaoContainerColor">#FFF4E8</Color>
    <Color x:Key="ErroColor">#D70015</Color>
    <Color x:Key="ErroContainerColor">#FCEEEE</Color>
    <Color x:Key="ErroBordaColor">#F2B8BC</Color>

    <SolidColorBrush x:Key="CanvasBrush" Color="{StaticResource CanvasColor}"/>
    <SolidColorBrush x:Key="SurfaceBrush" Color="{StaticResource SurfaceColor}"/>
    <SolidColorBrush x:Key="SurfaceMutedBrush" Color="{StaticResource SurfaceMutedColor}"/>
    <SolidColorBrush x:Key="BordaBrush" Color="{StaticResource BordaColor}"/>
    <SolidColorBrush x:Key="BordaForteBrush" Color="{StaticResource BordaForteColor}"/>
    <SolidColorBrush x:Key="BordaCampoBrush" Color="{StaticResource BordaCampoColor}"/>
    <SolidColorBrush x:Key="TextoBrush" Color="{StaticResource TextoColor}"/>
    <SolidColorBrush x:Key="TextoMutedBrush" Color="{StaticResource TextoMutedColor}"/>
    <SolidColorBrush x:Key="PrimaryBrush" Color="{StaticResource PrimaryColor}"/>
    <SolidColorBrush x:Key="PrimaryHoverBrush" Color="{StaticResource PrimaryHoverColor}"/>
    <SolidColorBrush x:Key="PrimaryActiveBrush" Color="{StaticResource PrimaryActiveColor}"/>
    <SolidColorBrush x:Key="PrimaryContainerBrush" Color="{StaticResource PrimaryContainerColor}"/>
    <SolidColorBrush x:Key="OnPrimaryBrush" Color="{StaticResource OnPrimaryColor}"/>
    <SolidColorBrush x:Key="AcaoBrush" Color="{StaticResource AcaoColor}"/>
    <SolidColorBrush x:Key="FocusBrush" Color="{StaticResource FocusColor}"/>
    <SolidColorBrush x:Key="SucessoBrush" Color="{StaticResource SucessoColor}"/>
    <SolidColorBrush x:Key="SucessoContainerBrush" Color="{StaticResource SucessoContainerColor}"/>
    <SolidColorBrush x:Key="AtencaoBrush" Color="{StaticResource AtencaoColor}"/>
    <SolidColorBrush x:Key="AtencaoContainerBrush" Color="{StaticResource AtencaoContainerColor}"/>
    <SolidColorBrush x:Key="ErroBrush" Color="{StaticResource ErroColor}"/>
    <SolidColorBrush x:Key="ErroContainerBrush" Color="{StaticResource ErroContainerColor}"/>
    <SolidColorBrush x:Key="ErroBordaBrush" Color="{StaticResource ErroBordaColor}"/>

    <!-- Dimensões compartilhadas -->
    <sys:Double x:Key="BotaoAlturaMin">40</sys:Double>
    <sys:Double x:Key="RaioControle">8</sys:Double>
    <sys:Double x:Key="RaioCartao">12</sys:Double>
    <Thickness x:Key="FocoMargem">1</Thickness> <!-- simula o anel de 2 px -->
</ResourceDictionary>
```

Notas de uso na migração:

- Consuma **sempre** `Brush`/`Double`, nunca o hex: um único dicionário por
  tema (claro/escuro) trocado em runtime; nada de cor fixa em controle.
- `AutomationProperties.Name` assume o papel do `accessibleName` do Qt;
  rótulos de campo acima do campo (não flutuantes) para o Narrador.
- O anel de foco de 2 px: `Border` com `FocusBrush` em `Thickness=1` + margem
  (efeito de 2 px fora do controle), `KeyboardNavigation.TabNavigation`.
- Tema escuro: mesmo conjunto de chaves com a coluna "escuro"; revalidar as
  razões de WCAG ao implementar (a coluna escura acima já foi medida ≥ 4,5/3,0
  exceto onde indicado em `docs/revisao_tela_ativacao.md`).
