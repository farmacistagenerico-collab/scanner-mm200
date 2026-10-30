# Risultati backtest Italia — revisione 2026-10-30

Ricalcolo eseguito su GitHub Actions con dati Yahoo Finance aggiornati.

- Run: https://github.com/farmacistagenerico-collab/scanner-mm200/actions/runs/41098305759
- PR: https://github.com/farmacistagenerico-collab/scanner-mm200/pull/1
- Periodo: 2010-01-31 → 2026-10-31
- Universo: 128 titoli italiani nella lista attuale
- Costi: 0,20% per lato sul nozionale comprato/venduto
- Benchmark principale: paniere liquido equipesato con stesse date/liquidità/ingressi/costi
- `validato: false`: nessun holdout intatto, survivorship bias non rimosso

| Variante | CAGR % | Sharpe | Max DD % | Turnover %/mese |
|---|---:|---:|---:|---:|
| ① Base MOM 12-1 top10 + MM200 (mensile) | 14,90 | 0,81 | -32,44 | 27,2 |
| ② + buffer di rank 5 | 15,27 | 0,85 | -31,66 | 19,3 |
| ③ + ribilanciamento trimestrale (buffer 5) | 14,76 | 0,91 | -26,89 | 19,7 |
| ①-bis Base senza filtro MM200 | 15,41 | 0,80 | -36,55 | 24,9 |
| ⓪ Controllo casuale (media 20 seed) | 10,94 | 0,71 | -30,86 | — |
| Paniere liquido equipesato (stessi costi/date) | 9,67 | 0,58 | -38,36 | 6,0 |
| Paniere liquido + MM200 (stessi costi/date) | 12,55 | 0,76 | -31,27 | 24,6 |
| Universo storico equipesato (buy & hold, non comparabile) | 11,50 | 0,68 | -33,10 | — |
| FTSE MIB (indice, non comparabile) | 5,17 | 0,36 | -42,70 | — |

## Lettura prudente

Nel ricalcolo, la variante con buffer 5 è sopra il paniere liquido equipesato di circa
5,6 punti percentuali di CAGR e ha Sharpe più alto. Anche il paniere liquido + MM200 è
sopra il paniere liquido senza trend: una parte del vantaggio viene dal filtro di trend,
non solo dalla selezione momentum.

Questo **non** è ancora una prova operativa di edge:

- l'universo è la lista attuale di titoli, quindi c'è survivorship bias;
- lo split storico non è un holdout intatto;
- costi forfettari, niente tasse, spread, impatto di mercato o sospensioni reali;
- sono segnalati 11 gap dati nel JSON di audit.

Prossimo passo serio: universo storico punto-per-punto, costi/tasse realistiche,
controllo dei gap e un holdout futuro veramente intatto.
