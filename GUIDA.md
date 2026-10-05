# GUIDA PRATICA — come si usa questo progetto

Tre livelli d'uso, dal più semplice al più avanzato. Scegli in base a cosa ti serve.

| Livello | Strumento | Cosa ottieni | Frequenza |
|---|---|---|---|
| **1. Lista d'attenzione** | `scanner.py` | i titoli di Piazza Affari "pronti a rompere" la MM200, con punteggio e report HTML | settimanale (5 min) |
| **2. Portafoglio operativo** | `selezione_oggi.py` | il portafoglio momentum 12-1 validato, pronto da eseguire (nomi, pesi, quote, operazioni) | mensile (10 min) |
| **2-bis. Cruscotto del giorno** | `operativita_oggi.py` | la risposta a "**oggi cosa faccio?**": verdetto, margini di uscita, candidati, contesto | **ogni giorno (10 sec)** |
| **2-ter. Punteggio per titolo** | `punteggio.py` | il **punteggio 0-100** di probabilità storica di successo di ogni azione + affidabilità del dato | quando vuoi il dettaglio per titolo |
| **2-quater. Dashboard live** | `dashboard.py` | la stessa pagina **con il tasto di aggiornamento in tempo reale**, l'**auto-refresh**, la **classifica completa** e i grafici | mentre segui il mercato |
| **2-quinquies. Sempre accesa** | [`LIVE.md`](LIVE.md) | avvio automatico, accesso da telefono, notifiche Telegram/email, password | una volta sola |
| **3. Ricerca** | gli altri script | rifare/estendere le verifiche statistiche (filtri, OOS, costi, casualità) | quando vuoi |

> Livello 1 = **osservazione**: dagli esperimenti risulta che la rottura della MM200, con qualunque filtro,
> non batte il caso in portafoglio (§6 README). Serve a *capire il mercato*, non a guadagnare.
> Livello 2 = **la parte che ha un edge misurato e stabile** (README §7 e §7.5): è qui che sta l'operatività.

---

## 0. Installazione (una volta sola)

```bash
pip install yfinance pandas numpy scipy
cd scanner_mm200
```

Requisiti: Python 3.10+, connessione a Internet (Yahoo Finance). Su Windows usare `python` al posto di `python3`.
Se il download non va (Yahoo a volte risponde 429), aspettare qualche minuto e riprovare; `--no-download`
riusa i dati in `cache/`.

---

## 1. Uso settimanale — la lista d'attenzione (`scanner.py`)

```bash
python3 scanner.py                      # scansione completa (MIB + Mid Cap + STAR)
python3 scanner.py --indice MIB --soglia 60
python3 scanner.py --no-download        # riusa i dati scaricati poco fa
```

Produce a video la selezione e due file: `output/report_mm200_AAAAAMMGG.html` (navigabile, colonne ordinabili)
e `output/segnali_mm200_AAAAAMMGG.csv` (tutte le metriche).

**Come si legge il report.** L'ordine delle sezioni è la cosa importante:

1. `★★ Segnale settimanale` — la configurazione più rara (2-3 volte l'anno su tutto il listino).
2. `★★★ Score validato out-of-sample` — titoli con punteggio ≥ +3 su una scala di 5 indicatori calcolati
   fuori campione. Sul periodo di verifica 2016-2026 questo gruppo ha reso **+18,4% a 12 mesi contro +1,7%
   dei titoli con score ≤ +1** (dettagli README §1.5). È l'informazione più solida dello scanner.
3. `★ Selezione finale` (punteggio ≥ soglia), poi le liste operative A → E (rotture fresche, pronti a
   rompere, trend in corso, falsi breakout, ribassisti).

**Cosa NON fare con lo scanner.** Non comprare tutto ciò che ha punteggio alto e stop stretto: provato in
`portafoglio.py`, dà gli stessi risultati di ingressi casuali (README §6). Usalo come *imbuto*: da 130 titoli
a 10-15 nomi da studiare, con uno score che ha valore predittivo misurato.

---

## 1-bis. Ogni giorno — la risposta a "oggi cosa faccio?" (`operativita_oggi.py`)

```bash
python3 operativita_oggi.py                 # cruscotto + pagina HTML
python3 operativita_oggi.py --solo-verdetto # una riga sola, ideale per una notifica
```

Si apre in un secondo e risponde con un **verdetto** in cima, uno di quattro:

| Verdetto | Cosa significa |
|---|---|
| **OGGI NON DEVI FARE NULLA** | nessuna condizione operativa attiva: è la risposta corretta nella grande maggioranza delle sedute |
| **NESSUN ORDINE — SOLO DA OSSERVARE** | qualche titolo è a meno del 3% dal livello di uscita |
| **ATTENZIONE — TITOLI FUORI REGOLA** | un titolo è sotto la MM200 o oltre il rank 15: si decide **a fine mese**, non oggi |
| **È IL MOMENTO DELLA VERIFICA** | ultimo giorno di borsa del mese (o entro 3 giorni dalla chiusura): lancia `selezione_oggi.py` |

Poi mostra: **margine** di ogni titolo sul proprio livello di uscita (semaforo verde/giallo/rosso), performance
del portafoglio dal giorno della selezione, giorni di borsa che mancano alla verifica, **candidati in attesa**
con il prezzo di attivazione, e un blocco di **contesto** (FTSE MIB vs MM200, breadth, rotture recenti)
esplicitamente etichettato come non operativo.

Automazione opzionale (Linux/macOS), ogni mattina alle 9:00:

```cron
0 9 * * 1-5 cd /percorso/scanner_mm200 && python3 operativita_oggi.py --solo-verdetto >> log_giorno.txt 2>&1
```

---

## 1-ter. Il punteggio per singola azione (`punteggio.py`)

```bash
python3 punteggio.py              # pagina semplice: un punteggio per titolo
python3 punteggio.py --dettaglio  # mostra anche coefficienti e tabelle interne
```

Pagina `output/punteggio.html`: una riga per titolo, quattro informazioni.

| Cosa vedi | Cosa significa |
|---|---|
| **Punteggio 0-100** | probabilità storica di chiusura positiva a 12 mesi per un titolo con queste stesse caratteristiche. Verde ≥ 72, giallo 62-71, rosso < 62 |
| **Atteso a 12 mesi** | mediana storica applicata al prezzo di oggi + il livello sotto cui il titolo esce (MM200) |
| **Affidabilità del dato** | su quanti casi storici simili è costruito il punteggio: alta ≥ 200, media 80-199, bassa < 80. Con pochi casi il punteggio è tirato verso la media di proposito |
| **Verdetto in alto** | cosa fare oggi (di norma: nulla) |

**Come è costruito.** Un modello logistico (3 caratteristiche: momentum relativo nel paniere, distanza dalla
MM200, volatilità) stimato su 1.570 posizioni storiche della regola (2010-2026), validato **walk-forward**:
per ogni caso passato il modello è stato ri-stimato solo con i dati precedenti. Fuori campione (2018-2026):
punteggio alto → **71,1%** di esiti positivi, punteggio basso → **60,6%**; dentro lo stesso portafoglio
mensile, il terzo di titoli col punteggio più alto ha chiuso positivo nel **70,6%** dei casi contro il
**60,9%** del terzo più basso.

**Cosa alza il punteggio** (controintuitivo, ma è ciò che dicono i dati): titoli meno estremi — momentum
relativo non ai massimi, prezzo non troppo staccato dalla MM200, volatilità contenuta. Il punteggio è per
questo un ottimo *contrappeso* al ranking di momentum: segnala quali posizioni, tra le 10, sono le più fragili.

---

## 1-quater. La dashboard live con il tasto di aggiornamento (`dashboard.py`)

```bash
python3 dashboard.py                 # server su http://localhost:8000 (apre il browser)
./avvia_dashboard.sh                 # macOS/Linux: installa le dipendenze e avvia (doppio click)
avvia_dashboard.bat                  # Windows: doppio click
python3 dashboard.py --porta 8000 --no-browser
```

**Dove sta il tasto ⟳ AGGIORNA ORA** (domanda frequente): esiste **solo nella pagina servita dal server**,
cioè `http://localhost:8000` — e nella vista statica `output/dashboard_statico.html` *se il server è in
esecuzione* (in quel caso la pagina mostra "● server attivo" e il tasto funziona; il server risponde con CORS
abilitato proprio per questo). Un file HTML aperto da solo **non può** riscaricare dati: è una limitazione di
sicurezza dei browser, non una scelta del progetto. Quindi:

1. avvia il server (`./avvia_dashboard.sh` o `avvia_dashboard.bat`, o `python3 dashboard.py`);
2. si apre il browser su `http://localhost:8000`: lì c'è il tasto, con i prezzi che si aggiornano da soli
   ogni 60 secondi a mercato aperto;
3. da quel server puoi vedere anche la vista statica aggiornata su `http://localhost:8000/statico`.

La pagina statica (`punteggio.html`) non può riscaricare dati da sola: per aggiornarla in tempo reale serve un
piccolo server locale. `dashboard.py` fa esattamente questo, con la sola libreria standard di Python.

**Cosa vedi**: una **scheda per titolo** con, da sinistra a destra: nome e livello di uscita, **punteggio** con
barra e affidabilità, **grafico** (prezzo in blu, MM200/livello di uscita in arancio tratteggiato, atteso a 12
mesi in verde, ultimo prezzo in evidenza) e i numeri chiave (prezzo, variazione di giornata, atteso).
I grafici sono **SVG generati in casa** (nessuna libreria, nessuna risorsa esterna): funzionano anche offline.

In fondo alla pagina c'è la scheda **"La strategia nel tempo"**: la curva dell'equity dal 2010 (base 100, costi
inclusi) della strategia consigliata (**② buffer di rank 5**, verde) contro la versione base (arancio),
l'universo equipesato (blu) e i portafogli casuali (grigio), con le statistiche di ciascuna
(CAGR, Sharpe, drawdown massimo). Serve a tenere a mente *perché* si segue questa regola: nel 2010-2026 il
buffer 5 ha portato 100 a **1.473**, la versione base a 1.187, l'universo a 642 e i portafogli casuali a 261.

**Cosa fa il tasto ⟳ AGGIORNA ORA** (aggiornamento completo, ~15-20 s):
riscarica i 130 titoli, ricalcola MM200, ranking di momentum, distanze, livello di uscita, candidati in attesa,
contesto di mercato (FTSE MIB, breadth, rotture) e tutti i **punteggi** con i prezzi nuovi.

**Aggiornamento rapido prezzi** ("prezzi ogni 60 s" / tasto *prezzi adesso*, ~2 s):
legge i prezzi intraday a 15 minuti dei soli titoli in portafoglio e dei candidati, e ricalcola prezzo,
variazione di giornata, distanza dalla MM200 e **punteggio**. Attivo automaticamente **solo a mercato aperto**
(lun-ven 9:00-17:40, ora di Milano).

Note pratiche:

- i prezzi arrivano dal feed gratuito Yahoo Finance: **ritardo tipico 15 minuti**, non è un feed di trading;
- l'ora dell'ultimo aggiornamento completo e dei prezzi è scritta in alto a destra della pagina;
- a ogni aggiornamento completo viene riscritta anche **`output/dashboard_statico.html`**: la stessa pagina
  senza server, apribile come file (o condivisibile);
- **il grafico si muove con i prezzi**: l'aggiornamento rapido aggiunge/aggiorna il punto intraday e ricalcola
  la MM200 dei titoli seguiti, quindi la linea di uscita arancione può salire o scendere durante la seduta;
- il modello dei punteggi (1.570 posizioni storiche) è stimato all'avvio e non cambia durante la giornata:
  cambiano i prezzi, quindi la distanza dalla MM200, quindi il punteggio;
- per lasciarlo girare in background: `nohup python3 dashboard.py --no-browser &` (oppure una voce in cron con
  `@reboot`);
- se il download fallisce (Yahoo a volte risponde 429) la pagina lo segnala in giallo e conserva l'ultimo
  stato valido; riprova con il tasto.

---

## 2. Uso mensile — il portafoglio momentum (`selezione_oggi.py`)

### 2.1 La ricetta (quella che ha superato tutti i controlli)

| Elemento | Valore | Perché |
|---|---|---|
| Segnale | momentum **12-1** (rendimento a 12 mesi saltando l'ultimo) | il premio più documentato della letteratura, e confermato sui tuoi dati |
| Filtro | prezzo **sopra la MM200** | evita di comprare titoli in downtrend |
| Liquidità | turnover mediano **≥ 2 M€/giorno** | senza questo, l'edge è illusorio: non eseguibile (§7.3) |
| Titoli | **top 10**, equipesati (10% ciascuno) | oltre 20 diluisce, sotto 10 troppo concentrato |
| Buffer di rank | **5** | è il vero "risk management": dimezza il turnover e **migliora** rendimento e Sharpe |
| Frequenza | **mensile** (o trimestrale se conta il risparmio fiscale) | mensile = +18,7% CAGR; trimestrale = +15,9% con turnover 10,8% |
| Overlay sull'equity | **nessuno** | MA10 e stop sul drawdown distruggono il rendimento (whipsaw, §7.5) |

### 2.2 Il rituale di fine mese (5 minuti)

Da fare dopo la chiusura dell'ultimo giorno di borsa del mese:

```bash
# 1) aggiorna i dati e genera la nuova selezione, confrontandola col portafoglio attuale
python3 selezione_oggi.py --capitale 100000 --attuale output/portafoglio_attuale.csv

# 2) genera la pagina da tenere aperta (cosa fare / cosa aspettare / target)
python3 scheda_operativa.py --capitale 100000 --attuale output/portafoglio_attuale.csv

# 3) esegui a mercato le sole operazioni indicate (vendi / compra)
#    ... e nient'altro: il resto del portafoglio NON si tocca

# 4) il file output/portafoglio_attuale.csv è ora aggiornato: sarà l'input del mese prossimo
```

Varianti utili:

```bash
python3 selezione_oggi.py --solo-lista                        # solo i 10 ticker, da copiare
python3 selezione_oggi.py --capitale 25000 --liquidita 1000000  # conto piccolo: soglia più bassa
python3 selezione_oggi.py --no-download                        # riusa gli ultimi dati scaricati
python3 selezione_oggi.py --trimestrale                        # modalità trimestrale (etichetta i file)
```

### 2.3 Cosa leggi nell'output

- **`mom 12-1 %`**: il rendimento della finestra di formazione. La finestra è dichiarata in testa
  (es. `2025-09-30 → 2026-08-31`): la formula salta l'ultimo mese, quindi è **più conservativa del backtest**
  e a prova di look-ahead.
- **`dist MM200 %`**: quanto il prezzo è sopra la media a 200 giorni. Se è vicino a 0 il titolo è appena
  rientrato nel filtro.
- **`turnover M€`**: liquidità. Con `--liquidita 2000000` nessun titolo è sotto i 2 M€/giorno **oggi**.
  Regola pratica: non mettere in un titolo più di ~1-2 giorni di turnover, e comunque non oltre il 10%.
- **`già in ptf` / sezione OPERAZIONI**: cosa fare rispetto a quello che hai. Il buffer fa sì che nella
  maggior parte dei mesi le operazioni siano 0-2, non 10.
- **`quote` / `eur_effettivi`**: il numero di azioni da comprare con il capitale indicato (lotti interi).

### 2.4 Esempio reale (dati al 02/10/2026, capitale 100.000 €)

| # | Titolo | Prezzo € | Mom 12-1 | Dist. MM200 | Turnover M€ | Peso | Quote |
|---|---|---|---|---|---|---|---|
| 1 | Tesmec | 0,56 | +245,8% | +109,1% | 2,9 | 10% | 17.699 |
| 2 | Technoprobe | 35,06 | +221,6% | +49,3% | 23,1 | 10% | 285 |
| 3 | Banco di Desio e Brianza | 16,80 | +140,9% | +44,9% | 2,4 | 10% | 595 |
| 4 | Saipem | 4,32 | +92,8% | +12,1% | 67,9 | 10% | 2.313 |
| 5 | STMicroelectronics | 50,35 | +82,0% | +20,7% | 190,9 | 10% | 198 |
| 6 | d'Amico International | 8,77 | +80,2% | +22,9% | 2,1 | 10% | 1.140 |
| 7 | Mediobanca | 27,41 | +73,8% | +24,1% | 9,9 | 10% | 364 |
| 8 | Banca Monte dei Paschi | 11,28 | +69,0% | +20,3% | 119,6 | 10% | 886 |
| 9 | Tenaris | 24,74 | +63,9% | +6,5% | 27,5 | 10% | 404 |
| 10 | Eni | 24,19 | +63,0% | +14,5% | 184,0 | 10% | 413 |

(File completo: `output/selezione_2026-10-02.csv`; scheda compatta: `output/selezione_oggi.md`.)

Nota di realismo: momentum molto alti (Tesmec +246%) sono in genere titoli piccoli e volatili, con
liquidità appena sopra la soglia. Il filtro di liquidità **è** il controllo di rischio: se vuoi un portafoglio
più tranquillo alza la soglia (`--liquidita 5000000`), sapendo che il backtest mostra rendimenti decrescenti
al crescere della soglia (25,7% → 12,6% a 12 mesi secondo i decili di liquidità, §7.3).

#### 2.4-bis Il "target price" della scheda HTML: cosa è davvero

`scheda_operativa.py` produce una pagina HTML autonoma (apribile senza Internet) con quattro blocchi:
**cosa fare ora** (azione, importo, quote), **cosa aspettare** (data della prossima verifica, condizioni di
uscita, candidati in attesa), **target** e **in attesa**.

Il target **non è un prezzo obiettivo da analista**: è la **mediana storica** dei rendimenti realizzati dai
titoli scelti con questa stessa regola dal 2010 a oggi, applicata al prezzo di oggi (+14,6% a 12 mesi,
intervallo 25°-75° da −6,7% a +38,8%, positivi nel 68% dei casi su 1.570 osservazioni). Serve a sapere *cosa
aspettarsi*, non a decidere quando vendere: **si esce per regola** (perdita della MM200 o rank oltre
N+buffer), mai perché il prezzo ha toccato il target.

## 2.5 Conto piccolo (5.000-25.000 €)

- Sotto ~15.000 €, 10 titoli in quote intere diventano difficili: usa `--n 8` e titoli con prezzi non troppo
  alti, oppure accetta qualche punto di sbilanciamento nei pesi.
- Non saltare titoli "perché costano tanto" (es. STM a 50 €): con 10.000 € sono 200 azioni per 2.000 € nominali,
  ma il peso resta 10% — controlla che la quota minima non renda il peso reale molto diverso dal 10%.
- Con conti piccoli i **costi fissi per ordine** dominano: usa un broker a commissioni basse e non tradare
  più di quanto dica il buffer.

### 2.6 Costi e tasse

- Nel backtest è già incluso **0,2% per lato** su ogni operazione; il turnover medio mensile della
  configurazione consigliata è **14,5%** (con buffer 5), cioè ~1,5 operazioni al mese su 10 titoli.
- In Italia il capital gain è tassato al **26%** in regime dichiarativo (12,5% sulla quota di titoli di Stato,
  se ne hai in portafoglio). Il ribilanciamento **trimestrale** riduce turnover e numero di eventi fiscali,
  ma nel backtest costa ~2,8 punti di CAGR (+15,9% contro +18,7%). Scelta: mensile se vuoi massima
  reattività, trimestrale se ottimizzi il netto fiscale.
- Le minusvalenze compensano plusvalenze: il buffer che riduce le sostituzioni riduce anche gli eventi fiscali.

---

## 3. Rifare le verifiche (livello ricerca)

In ordine di importanza; ogni script scrive log e JSON/CSV in `output/`. Tempi indicativi su questo ambiente.

```bash
python3 backtest.py --dal 2005-01-01          # rottura grezza vs baseline (il punto di partenza)
python3 volume_lab.py --dal 2005-01-01        # le 13 misure di volume (esito: nulle)
python3 filtri_lab.py --dal 2005-01-01        # 22 filtri a confronto (~1 min)
python3 filtri_check.py --dal 2005-01-01      # filtro vs baseline dello STESSO stato (il test che elimina i falsi filtri)
python3 controllo_robustezza.py --dal 2005-01-01  # finestre non sovrapposte + leave-one-out
python3 out_of_sample.py                      # calibrazione 2005-2015 → verifica 2016-2026 + Europa (~1 min)
python3 portafoglio.py --dal 2010-01-01       # dal segnale alla strategia: stop, sizing, costi (~1 min)
python3 momentum.py --dal 2010-01-01          # momentum cross-sectional (~2 min)
python3 momentum_risk.py --dal 2010-01-01     # buffer, volatility targeting, overlay, crash (~1,5 min)
```

Regola d'oro se modifichi qualcosa (universo, parametri, filtri): **guarda prima fuori campione**. Ogni volta
che in questo progetto si è ottimizzato sul campione pieno, il risultato è svanito dopo il 2016 (è successo
con il market timing, con gli overlay, con i pesi del portafoglio).

---

## 4. Cosa NON fare (tutto già testato e fallito)

| Idea | Esito misurato |
|---|---|
| Comprare le rotture MM200 "pulite" in portafoglio | pari a ingressi casuali (README §6) |
| Stop stretto / trailing stop sull'operazione | distrugge i rendimenti (+10,5% → −2,9% con trailing) |
| Overlay trend sull'equity della strategia (MA10) | 57% dei mesi in cash, drawdown durato 123 mesi, CAGR +17% → +2,7% |
| Overlay di drawdown (15%/25%) | instabile fuori campione (+13,2% IS → −3,9% OOS) |
| Volatility targeting come "miglioramento" | riduce il rischio ma costa rendimento: usalo solo con vincoli di rischio |
| Filtri di volume | 13 misure, nessun effetto (README §1.1) |
| Usare lo `score_validato ≥ 3` come strategia di portafoglio | +6,7% CAGR contro +12,8% dell'universo equipesato |
| Ottimizzare i pesi sul campione pieno senza OOS | i pesi cambiano di segno da un periodo all'altro |

---

## 5. Parametri: quando cambiarli

| Parametro | Default | Se lo cambi… |
|---|---|---|
| `--liquidita` (selezione) | 2.000.000 €/giorno | alzalo (5 M€) per eseguibilità e minore volatilità, abbassalo per universi più ampi ma più fragili |
| `--n` | 10 | 8-15 è la zona sensata; 20+ diluisce l'edge, 5 concentra troppo |
| `--buffer` | 5 | **non abbassarlo sotto 3**: senza buffer il turnover mensile passa da 14,5% a 24,3% pagando costi inutili |
| `--trimestrale` | off | attivalo solo per ridurre tasse/commissioni, sapendo del costo in rendimento |
| `--capitale` (selezione) | 100.000 € | cambia solo il calcolo delle quote, non la selezione |
| `--soglia`, `--distanza`, `--volume` (scanner) | 55 / 8 / 1,5 | modificano solo la lista d'attenzione: non esiste una soglia che "crea" un edge (l'edge sta nella ricerca, non nella soglia) |

---

## 6. Dove sono i file

| Cosa vuoi guardare | File |
|---|---|
| Portafoglio da eseguire questo mese | `output/selezione_AAAA-MM-GG.csv`, `output/selezione_oggi.md` |
| **Dashboard live (aggiornabile)** | `dashboard.py` → http://localhost:8000 (schede con grafico, tasto "Aggiorna", prezzi intraday) |
| **Dashboard statica (senza server)** | `output/dashboard_statico.html` (riscritta a ogni aggiornamento) |
| **Pagina più semplice (punteggi)** | `output/punteggio.html` (punteggio 0-100 per titolo + affidabilità del dato) |
| **Cruscotto di oggi** | `output/operativita_oggi.html` (verdetto, margini di uscita, candidati, contesto) |
| **Pagina operativa del mese** | `output/scheda_operativa.html` (cosa fare, cosa aspettare, target, livelli di uscita, candidati in attesa) |
| Portafoglio da ripassare il mese prossimo | `output/portafoglio_attuale.csv` |
| Lista d'attenzione MM200 | `output/report_mm200_AAAAAMMGG.html` |
| Report della strategia momentum + risk | `output/report_momentum_risk.html` |
| Report del momentum semplice | `output/report_momentum.html` |
| Perché la rottura MM200 non funziona | `output/report_portafoglio.html` |
| La ricerca statistica | `output/filtri_lab*.csv`, `output/out_of_sample.json`, `output/*_log.txt` |
| Spiegazione completa di ogni risultato | `README.md` (§1 ricerca, §1.5 OOS, §6 portafoglio, §7 momentum, §7.5 risk) |

---

## 7. Limiti e avvertenze

- **Non è consulenza finanziaria.** È uno strumento statistico: i risultati passati (anche fuori campione) non
  garantiscono quelli futuri. Il momentum è una strategia con **crash violenti** documentati: nel periodo
  testato il portafoglio ha perso fino al **−33,7%** dal picco, con mesi come marzo 2020 a −24,7%.
- **Survivorship bias**: l'universo contiene i titoli quotati *oggi*; i delistati non ci sono, quindi i
  rendimenti del backtest sono leggermente ottimisti.
- **Dati Yahoo Finance**: aggiustati per dividendi/split, ma con errori occasionali su titoli minori.
  Se un numero sembra strano, controllalo sul sito della borsa.
- **Capienza**: con 130 titoli italiani e il filtro di liquidità, la strategia ha senso fino a qualche
  milione di euro; oltre, l'impatto di mercato erode l'edge.
- **Il segnale ha periodi lunghi di sottoperformance**: nel 2018 e nel 2022 il portafoglio ha perso oltre il
  20%. Nessun overlay lo evita senza distruggere anche i rendimenti (misurato, §7.5): la gestione del rischio
  passa dalla **diversificazione** e dalla **size**, non dagli stop sulla strategia.
