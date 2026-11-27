# IBS/CBS — Reforma Tributária do Consumo (LC 214/2025)

Implementado na v0.5.43. O novo IVA Dual (CBS da União + IBS de estados e
municípios) entra em vigor em **01/01/2027**.

## Princípio

**O sistema não inventa alíquota.** CBS/IBS são informadas pelo **contador** da
gráfica para o **CNAE** do negócio e gravadas com vigência. A fonte pode ser
declarada como `contador` ou `receita` (conferência na calculadora oficial da
Receita Federal), mas não há consulta automática.

Referência oficial: https://github.com/ReceitaFederal/calculadora-rtc-regime-regular
(API do Regime Geral: CBS, IBS, Imposto Seletivo, CST/cClassTrib, NCM/NBS e
alíquotas de referência).

## Configuração

`Configurações > IBS/CBS` (somente ADMIN):
- CNAE, CBS %, IBS-UF %, IBS-Município %, vigência inicial/final, fonte e
  observações.
- Pelo menos uma alíquota deve ser informada; vigência final > inicial;
  CNAE + início não podem se repetir (409).
- A alíquota vigente em cada data é usada para exibição e cálculo local.

Endpoints: `GET/POST /v1/config/ibs-cbs-aliquotas` e
`PUT /v1/config/ibs-cbs-aliquotas/{id}/encerrar`.

## Fiscal

- Cada documento fiscal gravado guarda `ibs_cbs_snapshot` com as alíquotas
  vigentes na emissão (CNAE, percentuais, início e fonte).
- A tela de documentos mostra o snapshot na seção "Reforma Tributária".
- A tela de contingência exibe o badge **IBS/CBS NÃO PARAMETRIZADO** quando
  não há alíquota vigente.

## Envio ao gateway — DESLIGADO por padrão

O bloco `ibs_cbs` **só** entra no payload enviado ao gateway quando
`PRINTGEST_FISCAL_ENVIAR_IBS_CBS=true`. Motivo: o gateway é REST genérico de
terceiro (Focus NFe, PlugNotas etc.) e pode rejeitar campos desconhecidos.
Validar em homologação com o provedor antes de ligar a flag.

Nada foi alterado nas chaves antigas do payload (`valor_total`, `valor_itens`,
`desconto`, `itens`, pagamento), na emissão em contingência nem no cálculo de
impostos legado.

## Migration

`f2a4b8c9d0e1` — aditiva: cria `ibs_cbs_aliquota` e adiciona
`documento_fiscal.ibs_cbs_snapshot` (JSONB anulável). Aplicada ao Neon em
27/11/2026 com backup em branch `br-shiny-bread-b52l4cd9` (LSN 0/3CDA7D0).
Nenhum dado existente foi alterado e nenhuma alíquota padrão foi gravada.

## Fora do escopo
- CST/cClassTrib, NCM/NBS e natureza da operação nos itens (exigem cadastro
  tributário por produto/serviço).
- `split payment` de tributos (previsto para o 2º semestre de 2027 B2B).
- Apuração mensal de CBS/IBS e obrigações acessórias.
- Regimes de transição (Simples puro/híbrido) — hoje apenas o texto livre
  `empresa.regime_tributario`.
