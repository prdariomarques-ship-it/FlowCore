# Tickers yfinance verificados (13/08/2026) — fonte real obrigatória

Verificação programática `fast_info.last_price` com 26 de 26 OK em 19s. Nenhum ticker fabricado.

| Ativo | Ticker | Preço verificado |
|---|---|---|
| Ibovespa | ^BVSP | 167.033 |
| S&P 500 | ^GSPC | 7.801,74 |
| Nasdaq | ^IXIC | 26.836,33 |
| Dow Jones | ^DJI | 53.793,56 |
| Russell 2000 | ^RUT | 3.052,08 |
| Treasury 5Y | ^FVX | 4,311% |
| Treasury 2Y (IRX ~13wk) | ^IRX | 3,703% |
| Treasury 10Y | ^TNX | 4,637% |
| Treasury 30Y | ^TYX | 5,207% |
| Euro Stoxx 50 | ^STOXX50E | 6.545,47 |
| DAX | ^GDAXI | 26.299,74 |
| FTSE 100 | ^FTSE | 10.772,67 |
| Nikkei 225 | ^N225 | 68.308,59 |
| Hang Seng | ^HSI | 25.396,51 |
| Shanghai Composite | 000001.SS | 3.926,97 |
| WTI | CL=F | 80,94 |
| Brent | BZ=F | 86,78 |
| Ouro | GC=F | 4.414,80 |
| Prata | SI=F | 64,82 |
| Cobre | HG=F | 6,591 |
| VIX | ^VIX | 14,63 |
| USD/BRL | USDBRL=X | 5,189 |
| EUR/USD | EURUSD=X | 1,153 |
| USD/JPY | JPY=X | 159,49 |
| USD/CNY | CNY=X | 6,736 |
| DXY | DX-Y.NYB | 99,96 |

**Inviáveis no yfinance (ausência honesta, NÃO inventar):** DXY via ticker curto (`DX-Y.NYB` funciona mas é warning "possibly delisted" no primeiro lookup — usar com retry); Selic/DI curva brasileira (sem fonte real); small caps BR (ISUS3 sem ticker yfinance confiável); Fed Funds Futures (B0=Y falhou); inflação implícita (QL=F falhou).
