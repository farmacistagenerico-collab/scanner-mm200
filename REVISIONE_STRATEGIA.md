# Revisione strategia — 2026-10-30

Obiettivo dichiarato: provare a battere il mercato, partendo dall'**Italia** e usando come
confronto principale un **paniere equipesato**. Questa revisione non ottimizza parametri sui
rendimenti storici: prima rende il confronto onesto, poi si potrà cercare un segnale migliore.

## Scelte confermate

- Mercato prioritario: **IT**.
- Benchmark principale: **paniere liquido equipesato**, non il solo indice e non il vecchio
  buy & hold dell'intero universo.
- Il paniere deve condividere con la strategia: universo eleggibile, filtro di liquidità,
  date di segnale, prezzo di ingresso, costi per lato e trattamento della liquidità.
- Nessun parametro viene scelto in questa prima passata guardando il CAGR storico.

## Problemi trovati e corretti

1. **Segnale live diverso dal backtest.** La selezione operativa usava una finestra 12-1
   diversa da quella mensile. Ora `momentum_core.py` è la fonte unica: mesi conclusi,
   `P(t-1)/P(t-13)-1`, liquidità sulle tre mediane mensili precedenti.
2. **Mese corrente scambiato per mese concluso.** Ora si usa il calendario di borsa
   (`XMIL`, `XETR`, `XPAR`) e una barra è considerata definitiva solo dopo le 18:00 Europe/Rome.
3. **Fallback che riempiva gli slot.** Sotto MM200 o illiquido non si compra per forza.
   Gli slot mancanti restano liquidità.
4. **Costi incompleti.** Il vecchio risk backtest pagava solo il cambio nomi in ribilanciamento.
   Ora si paga il nozionale comprato/venduto su ogni transizione, incluse riduzioni/aumenti
   di esposizione e deriva dei pesi.
5. **Esecuzione troppo ottimistica.** Il segnale matura alla chiusura dell'ultima sessione del
   mese; l'ingresso ipotetico è alla prima chiusura successiva. L'eleggibilità non dipende più
   dal fatto che il titolo abbia dati nel mese successivo.
6. **Benchmark non comparabile.** Il paniere liquido equipesato è ora il confronto principale.
   Indice e vecchio buy & hold restano come diagnostiche etichettate “non comparabile”.
7. **Controllo casuale più debole della strategia.** I portafogli casuali usano stesso universo
   trend, stesso buffer e stessi costi; la media è sui rendimenti mensili, non sulle equity curve.
8. **Statistiche e report fuorvianti.** CAGR annualizzato sui rendimenti effettivi, split
   2010-2017/2018-2026 chiamato esplorativo, report per mercato, JSON con `validato: false`,
   gap dati e metodologia.
9. **Dashboard e guide troppo assertive.** Rimosse le promesse hardcoded di “metodo validato”
   e i numeri di riserva non ricalcolati.

## File principali

- `momentum_core.py`: regole condivise, calendari, pesi, turnover, costi, deriva.
- `momentum.py`: pannello mensile con mesi conclusi e prezzo di esecuzione; statistiche corrette.
- `momentum_risk.py`: simulatore con costi completi, cash slot, gap dati, paniere comparabile.
- `selezione_oggi.py`: selezione operativa allineata al core, pesi per slot, liquidità residua.
- `momentum_risk_report.py`, `dashboard.py`, `operativo.py`, `previsione.py`: etichette caute.
- `tests/`: regressione sintetica su calendari, segnale, filtri, costi, benchmark, CAGR.
- `.github/workflows/aggiorna.yml`: esegue i test prima di bootstrap/backtest.

## Cosa NON è ancora risolto

- **Survivorship bias**: l'universo è la lista attuale di titoli, non la composizione storica
  punto-per-punto. Questo può gonfiare i risultati.
- **Tasse e frizioni reali**: costi forfettari, niente imposte sul capital gain, spread,
  impatto di mercato, sospensioni, dividendi lordi/netti e cambi valuta.
- **Nessun holdout intatto**: le varianti sono state scelte dopo aver osservato entrambi i
  periodi storici. Lo split non è una validazione indipendente.
- **Dati reali non ricalcolati in questa revisione locale**: i test sono sintetici. Il prossimo
  passo è eseguire bootstrap/backtest su GitHub Actions o in locale con cache Yahoo aggiornata.

## Risultato del ricalcolo reale

Il backtest Italia è stato ricalcolato su GitHub Actions con dati Yahoo aggiornati.
La variante con buffer 5 risulta sopra il paniere liquido equipesato nel periodo
2010-2026, ma il risultato resta esplorativo. Dettagli e tabella:
[`RISULTATI_BACKTEST_IT.md`](RISULTATI_BACKTEST_IT.md).

## Protocollo per la prossima passata

1. Eseguire i test: `python -m unittest discover -s tests -v`.
2. Ricalcolare i dati: `python bootstrap_dati.py --mercato IT --forza`.
3. Ricalcolare il confronto: `python momentum_risk.py --mercato IT --dal 2010-01-01`.
4. Leggere `output/momentum_risk_riepilogo.json`: controllare `gaps_dati`, `validato`,
   universo, costi e benchmark principale.
5. Confrontare la variante di riferimento con il paniere liquido equipesato, non con l'indice.
6. Solo dopo: valutare survivorship-bias-free universe, costi/tasse realistiche, e un holdout
   futuro veramente intatto. Nessuna promessa di sovraperformance.
