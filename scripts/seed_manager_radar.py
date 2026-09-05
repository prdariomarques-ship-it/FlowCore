#!/usr/bin/env python3
"""One-off seed: inserts the 05/09/2026 "Radar de Cartas de Gestão" report
(Verde Asset + Legacy Capital) as a "radar" note so it shows up in the
FlowCore web dashboard's Notas page (expandable card, rendered markdown).

Run once per device after pulling this commit:

    python3 scripts/seed_manager_radar.py

Safe to re-run — it always creates a new document (radar entries are
dated snapshots, not something you'd want silently overwritten), so
running it twice will just create a duplicate entry.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from storage import DocumentRepository  # noqa: E402

TITLE = "Radar de Cartas de Gestão | 05/09/2026"

CONTENT = """## Radar de Cartas de Gestão | 05/09/2026

Fiz a busca tomando como corte a **última verificação de 03/09 às 11h**. Encontrei **dois materiais novos e relevantes que vieram a público em 04/09** e que realmente mudam o nosso mapa: **Verde Asset** e **Legacy Capital**.

Não repeti Occam, Alaska, TAG ou Kinea.

---

### 1. Verde Asset | Carta de agosto

A carta da Verde foi divulgada a clientes em **04/09** e traz uma mudança importante de postura: a gestora **aumentou a exposição à Bolsa brasileira em meados de agosto**.

[Verde Asset | site oficial](https://www.verdeasset.com.br/)

**Tese central**

A Verde entende que a eleição brasileira entrou em uma fase muito mais competitiva e que isso começa a criar **assimetria positiva para os ativos locais**.

A lógica é simples: eleição mais disputada → maior incerteza sobre o resultado → maior possibilidade de mudança na percepção sobre o futuro econômico → ativos brasileiros ainda carregando prêmio de risco → oportunidade na Bolsa.

A gestora passou a usar **opções compradas** para capturar essa assimetria sem precisar assumir uma exposição totalmente direcional.

**O ponto importante**

Isso é uma mudança clara em relação ao comportamento mais defensivo que vínhamos observando em algumas casas. A Verde não está dizendo que o Brasil ficou "resolvido". Está dizendo: o preço já carrega bastante risco e a distribuição de resultados possíveis ficou mais interessante.

---

### 2. Verde | Juros, inflação e atividade

Aqui a Verde é bem mais cautelosa. Na renda fixa brasileira, a gestora afirma que está **sem posição direcional relevante**. Mesmo reconhecendo que o juro real brasileiro está historicamente elevado, a Verde entende que o prêmio ainda não é suficiente para assumir uma posição forte em juros.

Isso cria uma diferença muito interessante: 🟢 mais exposição em Bolsa brasileira, 🟡 sem aposta direcional em juros reais. Ou seja: "Gosto mais da assimetria das ações do que da assimetria da curva."

---

### 3. Verde | O grande alerta está nos EUA

Essa é provavelmente a parte mais importante da carta. A Verde vê um possível início de **repressão financeira nos Estados Unidos**.

A tese é que a dívida americana está crescendo em um ambiente em que governo emite mais títulos + empresas de tecnologia emitem mais dívida para financiar capex de IA + juros longos já estão elevados + o Tesouro tenta influenciar a curva. A tentativa de conter os juros longos não teria funcionado de maneira persistente, na leitura da gestora.

**Consequência para a Verde**: a gestora continua vendo **ouro** e **prata** como instrumentos importantes de proteção. O ouro subiu cerca de **10,68% em agosto** e a prata **15,78%**, segundo os dados citados na carta.

---

### 4. Verde | O que mudou na tese?

Aqui temos uma revisão de posicionamento, embora não uma admissão de erro. A gestora: aumentou Bolsa Brasil, manteve ouro, manteve prata, manteve ativos globais, manteve hedges, não aumentou duration brasileira.

O ponto mais interessante é que ela está separando **risco de juros** de **risco de Bolsa**. Isso é sofisticado — a gestora não precisa acreditar em uma grande queda da Selic para acreditar que determinadas ações estão baratas.

---

### 5. Legacy Capital | Carta Mensal Agosto

A Legacy publicou sua **Carta Mensal de agosto**, disponível no próprio site da gestora.

[Legacy Capital | Carta Mensal Agosto 2026](https://www.legacycapital.com.br/wp-content/uploads/202608_Carta-Mensal.pdf)

Uma carta particularmente rica para o nosso radar porque mexe simultaneamente em: Fed, juros globais, Brasil, eleição, dólar, Bolsa, IA e commodities.

---

### 6. Legacy | A tese central

A Legacy identifica dois grandes fatores mantendo os juros reais longos elevados no mundo:

1. **Fiscal** — mais dívida pública → mais emissão de títulos → maior term premium.
2. **IA** — mais investimento em data centers e infraestrutura → mais necessidade de financiamento privado → maior competição por capital.

A conclusão da gestora é que esses dois movimentos podem manter os juros reais longos elevados por mais tempo. Essa tese conversa diretamente com o alerta da Verde.

---

### 7. Legacy | Fed

Mudança importante: a Legacy interpreta o discurso de Kevin Warsh em Jackson Hole como mais hawkish do que o mercado esperava. Na visão da gestora, se atividade e inflação seguirem próximas das expectativas atuais, o Fed poderá **voltar a subir juros** em algo entre **25 e 50 pontos-base no segundo semestre**. Isso é uma visão mais dura do que a leitura de algumas das casas que acompanhamos anteriormente.

Risco adicional: se inflação ou mercado de trabalho surpreenderem para cima, o ciclo de aperto pode durar ainda mais.

---

### 8. Legacy | Europa

A Legacy também trabalha com a possibilidade de mais uma alta do BCE, embora com menor convicção. O motivo é a combinação energia + inflação + atividade relativamente resiliente. A gestora considera que o choque energético pode voltar a contaminar inflação subjacente, salários e serviços.

---

### 9. Legacy | Brasil

A Legacy vê atividade desacelerando, empresas começando a cortar custos, demissões aumentando, crédito mais pressionado — e trabalha com PIB de **1,8% em 2026** e **1,5% em 2027**, ambos com viés de baixa.

Na inflação: **4,9% em 2026** e **4,7% em 2027**. Os serviços continuam pressionados, mas a inflação de bens está melhorando.

---

### 10. Legacy | Selic

Diferença importante em relação à Kinea: a Legacy ainda acredita que o Banco Central pode continuar cortando **25 pontos-base nas próximas reuniões**. Mas reconhece que a assimetria piorou por causa de juros globais + risco eleitoral + possível desvalorização do real depois das eleições.

Portanto: 🟢 ainda vê cortes, 🟡 mas com risco maior.

---

### 11. Legacy | Uma mudança de tese interessante

A gestora reconhece explicitamente uma **"piora na assimetria"** no cenário de continuidade dos cortes. Não é uma admissão de erro — é uma revisão do balanço de riscos.

Antes: inflação melhor + atividade desacelerando. Agora: inflação melhor + atividade desacelerando, mas Fed mais hawkish + eleição + risco cambial. Isso reduz a convicção na tese de queda contínua dos juros.

---

### 12. Legacy | Bolsa americana

Apesar do cenário de juros mais complicado, a Legacy continua 🟢 construtiva em ações americanas. O argumento é lucro: as estimativas de lucro do S&P 500 continuam sendo revisadas para cima e a casa espera crescimento de dois dígitos em 2027. Por isso, considera prematuro ficar estruturalmente bearish em Bolsa americana.

Mas: valuation alto + Fed mais hawkish = mais seletividade.

---

### 13. Legacy | Dólar

Mudança interessante: a Legacy passou a ter uma posição **mais equilibrada em dólar**.

Contra dólar: fiscal americano ruim + intervenção do governo nos mercados. A favor do dólar: Fed mais hawkish + diferencial de juros maior. Portanto: a Legacy reduziu a convicção em uma posição estrutural vendida em dólar — uma revisão de tese relevante.

---

### 14. Legacy | Brasil virou uma assimetria

Apesar do cenário global mais difícil, a Legacy ficou **mais construtiva com ativos brasileiros**. A casa destaca pesquisas eleitorais + piora da avaliação do governo + dinâmica técnica mais favorável como fatores que melhoraram a relação risco/retorno do Brasil.

O consenso está começando a se dividir: Verde 🟢 aumentando Bolsa Brasil, Legacy 🟢 aumentando a disposição para ativos brasileiros, Kinea 🟡 exposição reduzida, TAG 🟡 foco em proteção real, Occam 🟡 hedge elevado.

---

### 15. Legacy | Posições globais

Preferência por ações americanas, cautela com duration americana. A Legacy considera que o Treasury longo pode continuar pressionado por fiscal + IA + Fed + Japão — bastante coerente com a tese da Verde sobre ouro e repressão financeira.

---

### 16. A grande comparação

| Tema | Verde | Legacy | Kinea | TAG |
|---|---|---|---|---|
| Bolsa Brasil | 🟢 Aumentou | 🟢 Mais favorável | 🟡 Cautela | 🟡 |
| Juros Brasil | 🟡 Neutro | 🟢 Cortes | 🟡 Pausa | 🟢 NTN-B |
| Duration EUA | 🔴 Cautela | 🔴 Cautela | 🔴 Cautela | 🟡 |
| Ouro | 🟢 | 🟢 | 🟢 | 🟢 |
| Dólar | 🟡 | 🟡 Mais equilibrado | 🟢 Comprado | 🟢 Hedge |
| IA | 🟢 | 🟢 | 🟢🟢 | 🟡 |
| Fiscal EUA | 🔴 | 🔴 | 🔴 | 🟡 |
| Eleição Brasil | 🟢 assimetria | 🟢 assimetria | 🔴 risco | 🔴 risco |

---

### 17. A convergência mais importante

Verde e Legacy dizem praticamente a mesma coisa: **o problema dos juros longos americanos não desapareceu.**

Verde: dívida + capex de IA → juros longos pressionados. Legacy: dívida + capex de IA + Fed → juros reais longos elevados. Isso reforça uma tese que vem crescendo no nosso radar: o Treasury longo deixou de ser automaticamente o porto seguro da carteira.

---

### 18. A divergência mais importante

Brasil: Verde comprando, Legacy mais construtiva — versus Kinea com exposição reduzida, TAG defensiva, Occam com hedge alto. Os gestores estão começando a discordar não tanto sobre os dados atuais, mas sobre quanto do risco eleitoral já está incorporado nos preços.

---

### 19. Reconhecimento de erros e mudanças de tese

**Verde**: não identificamos reconhecimento explícito de erro. Houve mudança de exposição — mais Bolsa Brasil, sem posição direcional em juros locais.

**Legacy**: também sem admissão de erro, mas com duas revisões claras — (1) piora da assimetria para cortes do BC; (2) dólar passou de uma visão estruturalmente mais vendida para uma postura mais equilibrada.

---

### 20. O novo mapa do nosso radar

🟢 Mais fortes: Ouro, Prata, Ações americanas seletivas, Infraestrutura de IA, Semicondutores, Bolsa brasileira seletiva.

🟡 Construir aos poucos: NTN-B curta/intermediária, Bolsa Brasil, Dólar como hedge, Duration brasileira.

🔴 Cautela: Treasury longo, Crédito com spread comprimido, Grandes apostas direcionais no Brasil.

---

## 5 insights para acompanhar

1. **Verde + Legacy começaram a enxergar assimetria no Brasil.** Ainda não é consenso, mas duas casas relevantes passaram a enxergar uma relação risco/retorno melhor nos ativos brasileiros.
2. **O Treasury longo está virando o grande problema global** — não é apenas inflação, é dívida pública + capex privado de IA + Fed + Japão + term premium.
3. **Ouro e prata ganharam função estrutural** — a tese está evoluindo de hedge de guerra para proteção contra deterioração fiscal + perda de poder de compra + repressão financeira.
4. **A disputa eleitoral começa a virar catalisador, não apenas risco.** Para Kinea e TAG, eleição = risco. Para Verde e Legacy, eleição = fonte de assimetria.
5. **Próxima confirmação a procurar**: se mais uma grande gestora disser "Brasil está barato + eleição mais competitiva + risco já precificado" e simultaneamente reduzir hedge em Bolsa, teremos um sinal muito mais forte de mudança de regime.

---

## Leitura final

O radar ficou **mais construtivo com Brasil e mais cauteloso com Treasury longo**.

Brasil: 🟢🟡 melhorando · Bolsa brasileira: 🟢🟡 · NTN-B curta/intermediária: 🟢 · NTN-B longa: 🟡 · CDI: 🟢 carrego · Crédito: 🟡 seletivo · EUA: 🟢 Bolsa / 🔴 duration · IA: 🟢🟢 estrutural · Ouro/prata: 🟢🟢 · Dólar: 🟡 sem consenso.

O ponto que eu colocaria em vermelho no nosso radar agora é: se Verde e Legacy estiverem certas, o mercado pode estar começando a precificar a eleição brasileira como uma oportunidade de reprecificação dos ativos, e não apenas como fonte de risco.

Ainda é **tese de gestor, não fato**. Mas é uma mudança de narrativa que vale acompanhar muito de perto nas próximas cartas.
"""


def main() -> int:
    doc_id = DocumentRepository().insert_sync(TITLE, CONTENT, "radar")
    print(f"Radar salvo como nota #{doc_id} — abra o dashboard web, aba Notas, para ver.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
