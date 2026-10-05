# Scanner MM200 — Borsa Italiana (Piazza Affari)

Scanner in Python che cerca, tra i titoli di **Borsa Italiana** (FTSE MIB, FTSE Italia Mid Cap, FTSE Italia STAR),
quelli **pronti a rompere la media mobile a 200 periodi** (o appena rotti), con un punteggio di "attenzione" e i
segnali costruiti — e continuamente verificati — su una ricerca empirica interna.

> ⚠️ Strumento di analisi automatizzata. Non è consulenza finanziaria né una raccomandazione di investimento.
> Il punteggio ordina l'*attenzione*, non la probabilità di profitto: leggi §1 e §5.
>
> 👉 **Come si usa, in pratica: [`GUIDA.md`](GUIDA.md)** — installazione, rituale mensile, lettura degli
> output, costi/tasse, cosa non fare. Per l'operatività il comando chiave è `python3 selezione_oggi.py`.
>
> 🔴 **Renderlo live e completo: [`LIVE.md`](LIVE.md)** — aggiornamento automatico, avvio all'accensione
> (systemd / launchd / Task Scheduler), accesso da telefono con Tailscale, notifiche Telegram/email, password.
>
> ☁️ **Pubblicarlo su GitHub** (gratis, si aggiorna da solo, nessun PC acceso): [`deploy/PUBBLICA_SU_GITHUB.md`](deploy/PUBBLICA_SU_GITHUB.md).

---

## 1. La ricerca (la parte che conta)

Tutto riproducibile con `backtest.py`, `volume_lab.py`, `filtri_lab.py` e `filtri_check.py` (2005 → oggi,
~130 titoli italiani). Domanda di fondo: *cosa rende una rottura della MM200 statisticamente significativa
e non un falso segnale?*

### 1.1 Il verdetto in tre righe

1. **La rottura "grezza" non ha edge**: +11,6% a 12 mesi contro +12,8% di un periodo qualunque.
2. **Il volume NON è un filtro**: 13 misure testate, nessun effetto, nemmeno aspettando la conferma a 3 giorni.
3. **L'unico filtro con informazione specifica è il CONTESTO DI PREZZO — e ora è validato fuori campione**
   (vedi §1.5): rotture in *deep recovery* (titolo ≥20% sotto i massimi a 12 mesi) → excess **+5,2 punti** nel
   2016-2026 mai usato per la ricerca (p=0,039; versione non sovrapposta +25,8% vs +11,2%, p=0,0004).
   Quasi tutto il resto è solo market timing.

### 1.2 La classifica dei filtri (filtri_lab.py, 22 candidati su 4.296 rotture)

| Filtro | n | Rend. a 12 mesi (sì / no) | Falsi breakout (sì / no) | Verdetto |
|---|---|---|---|---|
| Deep recovery (dd < −20% dai massimi) | 1.055 | **+16,3% / +10,0%** | **61% / 67%** | ✅ **l'unico con excess positivo** (+4,2 pp sulla baseline di stato; regge il non sovrapposto) |
| Forza relativa sopra la mediana | 1.968 | +14,9% / +8,6% | 68% / 64% | ⚠️ effetto alto ma **solo market timing** (baseline di stato +16,1% vs +9,4%): excess −1,2 pp |
| MM200 chiaramente in salita (>1%) | 862 | +16,6% / +10,3% | 74% / 64% | ⚠️ forte in campione pieno, **si azzera** col controllo non sovrapposto |
| Nessun incrocio da 6+ mesi | 740 | +15,1% / +10,9% | 58% / 67% | ⚠️ suggeritivo (p=0,04), instabile tra i decenni |
| Regime: MIB sopra la MM200 | 2.369 | +8,7% / +15,8% | 62% / 71% | ⚠️ **solo market timing** (baseline di stato +10,6% vs +16,5%): excess −1,9 pp |
| Breadth ≥50% | 2.436 | +9,1% / +15,6% | — | ⚠️ idem: misura il mercato, non la rottura |
| Bassa volatilità / compressione Bollinger | 2.209 / 1.475 | ≈ −4 pp | — | ❌ controproducente |
| Volume, RSI, medie allineate, vicino ai massimi | — | ≈ 0 o negativo | — | ❌ nessun valore |

### 1.3 Perché il controllo "baseline dello stesso stato" è decisivo

Se in certi stati (es. MIB sotto la MM200) **tutti** i periodi rendono di più, un filtro che seleziona quello
stato non dice nulla sulla qualità della rottura. Confrontando ogni filtro con la baseline del **medesimo
stato** (filtri_check.py, ~740.000 finestre):

| Stato | Baseline di stato | Rotture | Excess |
|---|---|---|---|
| MIB sopra la MM200 | +10,6% | +8,7% | **−1,9** |
| MIB sotto la MM200 | +16,5% | +15,8% | −0,7 |
| **Deep recovery (dd < −20%)** | **+12,1%** | **+16,3%** | **+4,2** ✅ |
| Vicino ai massimi (dd > −15%) | +12,7% | +9,8% | **−2,9** |
| Forza relativa sopra la mediana | +16,1% | +14,9% | −1,2 |

**Lettura pratica:** la scelta "vendo/evito i breakout nei mercati debolissimi" è sbagliata come filtro: quei
periodi rendono tanto *per tutti*, con win rate però più basso (payoff asimmetrico: falliscono più spesso ma
quando funzionano fanno grandi rialzi). L'unica cosa che distingue una rottura "buona" è **da dove arriva**:
recovery profonda sì, massimi no.

### 1.4 Approfondimenti e fonti

- **volume_lab.py**: dose-risposta, 2×2 volume×struttura, punteggio composito 0-6, validatore a 3 giorni,
  split decenni, fascia di liquidità. Sintesi: nessun effetto del volume, in nessuna configurazione.
- **controllo_robustezza.py**: finestre non sovrapposte (max 1 evento/titolo/anno) → il "setup" settimanale
  volume+struttura **resiste** (+34,6% vs +13,0% baseline, n=53, p≈0,006) ma con ~2-3 segnali/anno e resa
  dimezzata nell'ultimo decennio; gli effetti giornalieri invece si azzerano.
- Letteratura coerente: Brock-Lakonishok-LeBaron (1992), quantifiedstrategies (28% di trade vincenti con la
  regola secca sul 200-day), collinseow (breakout con volumi 2x: win 72% ma 18 segnali in 3 anni),
  adamhgrimes (effetto della rottura della 200-day "molto probabilmente dovuto al caso").

### 1.5 Verifica out-of-sample e validazione esterna (out_of_sample.py)

Protocollo fissato prima di guardare i risultati: **calibrazione 2005-2015 → verifica 2016-2026**, più una
**validazione esterna** su ~56 large cap europee (DE, FR, ES, NL, BE, UK) su cui non è stata fatta alcuna
calibrazione.

**A) Il filtro deep recovery si replica fuori campione**

| Periodo | Excess deep recovery | Welch deep vs altre | Non sovrapposte | Falsi breakout |
|---|---|---|---|---|
| 2005-2015 (calibrazione) | **+4,0 p.p.** (p=0,064) | t=1,67; p=0,094 | +10,9% vs +8,4% (p=0,51) | 59,6% vs 64,5% |
| **2016-2026 (OOS)** | **+5,2 p.p.** (p=0,039) | **t=3,18; p=0,0015** | **+25,8% vs +11,2% (p=0,0004)** | **61,9% vs 66,6%** |

Il filtro "vicino ai massimi" è negativo in **entrambe** le metà (−5,0 p.p. e −3,8 p.p., p≈0,0002 e p=0,0001).

**B) Lo score calibrato sull'excess e verificato OOS (monotòno)**

Componenti con punto positivo (significative nell'IS sull'excess): **deep recovery, MM200 in salita,
MM50>MM200, forza relativa ≥50° percentile**; punto negativo: **vicino ai massimi**. Peso zero (nessuna
significatività): volume, RSI, struttura settimanale, bassa volatilità, rendimento 12 mesi, assenza di incroci.

| Score | Excess medio IS (2005-2015) | Excess medio **OOS (2016-2026)** |
|---|---|---|
| +4 | +30,6% | **+18,4%** (n=55) |
| +3 | +6,8% | **+8,5%** (n=130) |
| +2 | +2,2% | +1,7% (n=522) |
| +1 | −4,2% | −1,7% (n=880) |
| ≤0 | −7,1% | −4,2% (n=786) |

Monotonia perfetta in entrambi i periodi: **≥+2 vs resto t=3,19 (p=0,0014)**; **≥+3 vs resto: +11,4% vs −2,9%
(n=185)**. La lezione metodologica: la stessa calibrazione fatta sui *rendimenti grezzi* è debole e instabile
(mescola la composizione degli stati con la qualità della rottura) — va fatta sull'**excess condizionato**.

**C) Validazione esterna: Europa 2005-2026 (nessuna calibrazione)**

| Gruppo | n | Rendimento | Baseline di stato | Excess | Win rate | Falsi breakout |
|---|---|---|---|---|---|---|
| **Deep recovery** | 317 | **+27,1%** | +18,9% | **+8,2** | **81,7%** | 60,2% |
| Vicino ai massimi | 1.866 | +7,8% | +9,3% | −1,5 | 63,6% | 62,4% |
| Tutte le rotture | 2.500 | +10,8% | +10,3% | +0,5 | 65,7% | 62,4% |

Non sovrapposte: deep **+22,4%** vs altre +11,2% (t=4,05; p=0,0001). Positivo in entrambe le metà
(+10,6 p.p. nel 2005-2015, +4,4 p.p. nel 2016-2026). **Il filtro funziona anche fuori dall'Italia**, mentre la
rottura "grezza" continua a non avere edge (+0,5 punti di excess su 2.500 casi).

**Sintesi:** l'unico strumento che, abbinato alla MM200, ha superato tutti i controlli (IS, OOS, mercati
esterni, finestre non sovrapposte, leave-one-out) è il **contesto di prezzo**: *da dove arriva il titolo quando
rompe la media*. Il resto — volume in testa — è rumore o market timing.

## 2. Installazione e uso

```bash
pip install yfinance pandas numpy scipy
cd scanner_mm200

python3 scanner.py                       # scansione completa (MIB + Mid Cap + STAR)
python3 scanner.py --indice MIB --volume 2.0 --soglia 60
python3 scanner.py --no-download         # riusa la cache locale

python3 backtest.py --dal 2005-01-01                 # ricerca base (rotture e filtri)
python3 volume_lab.py --dal 2005-01-01               # laboratorio volume (13 misure)
python3 controllo_robustezza.py --dal 2005-01-01     # finestre non sovrapposte + leave-one-out
python3 filtri_lab.py --dal 2005-01-01               # classifica di 22 filtri (rendimento + falsi breakout)
python3 filtri_check.py --dal 2005-01-01             # filtro vs baseline dello STESSO stato
python3 out_of_sample.py                             # calibrazione 2005-2015 → verifica 2016-2026 + Europa
python3 portafoglio.py --dal 2010-01-01              # strategia con stop, sizing e costi
python3 momentum.py --dal 2010-01-01 --liquidita 500000   # momentum cross-sectional mensile
python3 momentum_risk.py --dal 2010-01-01                 # momentum + volatilità target, overlay, buffer di mercato

# --- USO OPERATIVO (non ricerca): il portafoglio del mese ---
python3 selezione_oggi.py                                 # nuova selezione con dati freschi
python3 selezione_oggi.py --capitale 100000 --attuale output/portafoglio_attuale.csv
python3 selezione_oggi.py --solo-lista                    # solo i ticker selezionati
python3 scheda_operativa.py --attuale output/portafoglio_attuale.csv
                                                          # pagina HTML: cosa fare / aspettare / target
python3 operativita_oggi.py                               # cruscotto giornaliero: "oggi cosa faccio?"
python3 operativita_oggi.py --solo-verdetto               # una riga, per notifiche/cron
python3 punteggio.py                                      # punteggio statistico per titolo (pagina semplice)
python3 dashboard.py --porta 8000 --ogni-minuti 20        # DASHBOARD LIVE: grafici, tasto, auto-refresh, notifiche
python3 dashboard.py --notifica-prova                     # verifica le notifiche Telegram/email
python3 dashboard.py --una-tantum                        # UN giro completo, scrive la pagina ed esce (per CI/cron)
python3 bootstrap_dati.py                                # (ri)costruisce le cache: primo avvio o cloud
python3 dashboard.py --utente mario --password segreta    # con password (se la esponi in rete)
./avvia_dashboard.sh        # (Windows: avvia_dashboard.bat) avvio comodo con dipendenze
```

> Il tasto **⟳ AGGIORNA ORA** esiste solo nella pagina **servita dal server** (`http://localhost:8000`) e nella
> vista statica *quando il server è in esecuzione*. Il file `output/dashboard_statico.html` aperto da solo è
> solo una fotografia: senza server non può riscaricare dati (per sicurezza i browser lo impediscono).

| Parametro scanner | Default | Significato |
|---|---|---|
| `--indice` | TUTTI | `TUTTI`, `MIB`, `MID` |
| `--buffer` | 1.0 | fascia ±% attorno alla MM200 = zona di indecisione |
| `--distanza` | 8.0 | quanto sotto la media un titolo è ancora "a ridosso" |
| `--volume` | 1.5 | moltiplicatore volume per la conferma |
| `--soglia` | 55 | punteggio minimo per la selezione finale |

---

## 3. Come funziona

### 3.1 Etichette

| Etichetta | Significato |
|---|---|
| **ROTTURA CONFERMATA** | incrocio al rialzo ≤5 sedute fa **con** volume ≥1,5x |
| **ROTTURA DA CONFERMARE** | incrocio recente ma volume debole (rischio falso segnale) |
| **FALSO BREAKOUT / RIENTRO** | ha rotto da poco ed è già rientrato sotto la media |
| **IN PROSSIMITÀ (sotto/sopra)** | prezzo nella fascia ±1% attorno alla MM200 |
| **IN AVVICINAMENTO (sotto)** | sotto la media, entro l'8%, con rimbalzo già avviato |
| **TREND RIALZISTA / RIBASSISTA** | sopra/sotto la media da più di 5 sedute |

### 3.2 Punteggio 0-100 (pesi allineati alle evidenze)

| Blocco | Punti | Dettaglio |
|---|---|---|
| Contesto di trend | 35 | MM200 in salita +20 (piatta +8) · MM50 sopra MM200 +15 |
| Prossimità alla MM200 | 25 | a ridosso +25 · distanza ridotta +14 · già sopra +6 |
| **Contesto di prezzo** | **20** | **deep recovery (dd < −20%) +20 · recovery intermedio +10 · vicino ai massimi −5** |
| Qualità del movimento | 12 | RSI 45-75 +6 · rend. 6 mesi >0 +4 · volatilità compressa +2 |
| Volumi | 8 | volume ≥1,5x +5 (solo partecipazione: **non è un filtro validato**) · volumi in ripresa +3 |
| Bonus ★ segnale settimanale | +10 | l'unica combo che regge i controlli (rara) |
| Penalità anti-whipsaw | −15 | ≥6 attraversamenti della MM200 negli ultimi 3 anni |

Accanto a questo punteggio "di attenzione" c'è lo **score_validato OOS** (colonna "Score OOS" nel report),
con pesi fissi derivati dalla calibrazione 2005-2015 e confermati sul 2016-2026:
`+1` deep recovery · `+1` MM200 in salita · `+1` MM50>MM200 · `+1` forza relativa ≥50° pct · `−1` vicino ai
massimi. La soglia operativa consigliata è **≥+3** (excess OOS medio +11,4%; con ≥+2 l'excess è +4,2% ma la
selezione è molto più larga).

### 3.3 Sezioni del report (tabelle ordinabili cliccando le intestazioni)

`★★ Segnale settimanale` → `★ Selezione finale` → `A)` rotture fresche → `B)` pronti a rompere →
`C)` trend già in corso → `C-bis)` trend maturi validati → `D)` falsi breakout → `E)` ribassisti.

---

## 4. File prodotti

| File | Contenuto |
|---|---|
| `output/report_mm200_AAAAAMMGG.html` | report navigabile e ordinabile (autonomo) |
| `output/segnali_mm200_AAAAAMMGG.csv` / `.json` | metriche complete + selezione finale |
| `output/ricerca_significativita_mm200.json` | risultati del backtest per timeframe/filtro |
| `output/volume_lab.json` + `volume_lab_riepilogo.csv` | esito delle 13 misure di volume |
| `output/controllo_robustezza.json` | test non sovrapposti, stabilità, concentrazione |
| `output/filtri_lab.json` + `_riepilogo.csv` | classifica dei 22 filtri testati |
| `output/filtri_check.json` | filtro vs baseline condizionata allo stato |
| `output/out_of_sample.json` + `_log.txt` | verifica fuori campione e validazione esterna |
| `output/report_portafoglio.html` | report della strategia: equity, varianti, walk-forward |
| `output/portafoglio_*.csv` | varianti, rendimenti per anno, equity, operazioni, pesi walk-forward |
| `output/report_momentum.html` | report del modulo momentum: equity, controllo casuale, IS/OOS, liquidità |
| `output/momentum_*.csv` | varianti, per anno, IS/OOS, equity, sensibilità liquidità |
| `output/report_momentum_risk.html` | report risk management: varianti, crash, IS/OOS |
| `output/momentum_risk_*.csv` | varianti, diagnostica crash, per anno, equity, IS/OOS |
| `output/selezione_AAAA-MM-GG.csv` + `selezione_oggi.md` | **portafoglio operativo del mese** (`selezione_oggi.py`) |
| `output/portafoglio_attuale.csv` | posizioni correnti, da ripassare con `--attuale` il mese prossimo |
| `output/scheda_operativa.html` | **pagina operativa mensile** (autonoma): azioni, importi, target statistico, livelli di uscita, candidati in attesa |
| `output/operativita_oggi.html` | **cruscotto giornaliero**: verdetto ("oggi non fare nulla" / "verifica" / "attenzione"), margine di ogni titolo sul livello di uscita, candidati, contesto |
| `output/punteggio.html` | **pagina semplice**: punteggio 0-100 di probabilità storica di esito positivo per titolo + affidabilità del dato (numero di casi simili) |
| `dashboard.py` (server) | **dashboard live**: schede con grafico (prezzo, MM200/uscita, atteso), tasto "⟳ AGGIORNA ORA", prezzi intraday auto-aggiornati ogni 60 s a mercato aperto |
| `output/dashboard_statico.html` | stessa pagina **in versione statica** (senza server), riscritta a ogni aggiornamento completo |
| `grafici.py` | generatore di grafici **SVG autonomi** (nessuna libreria, nessun CDN): grafico prezzo/MM200/atteso, **curva equity della strategia** (buffer 5 vs base vs universo vs casuali) e grafici on-demand per la classifica |
| `config_live.json` (+ `.example`) | configurazione: intervallo di aggiornamento automatico, notifiche Telegram/SMTP, password |
| `deploy/` | avvio automatico: unit **systemd**, plist **launchd**, script **Task Scheduler** Windows |
| `deploy/github-actions/aggiorna.yml` | workflow GitHub Actions: aggiorna e pubblica su GitHub Pages (da copiare in `.github/workflows/`) |
| `deploy/PUBBLICA_SU_GITHUB.md` | guida passo-passo al deploy su GitHub |
| `bootstrap_dati.py` | ricostruisce le cache (56 MB) al primo avvio o in CI |
| `.gitignore` | esclude credenziali, cache e file di lavoro dal repository |
| `output/stato_live.json` | ultimo verdetto e data dell'ultima notifica (per non ripeterle) |
| `output/*_log.txt` | log completi delle esecuzioni di ricerca |

Codice: `titoli_italiani.py` (universo), `indicatori.py` (medie, punteggio), `scanner.py` (CLI + analisi),
`backtest.py` (ricerca base), `volume_lab.py` (laboratorio volume), `controllo_robustezza.py` (robustezza),
`report_html.py` (report).

---

## 5. Limiti

- **Finestre sovrapposte** → i t-test vanno sempre letti con i controlli di `controllo_robustezza.py`.
- **Survivorship bias**: universo = titoli quotati oggi (i delistati non ci sono).
- **Costi**: i moduli di portafoglio/momentum (`portafoglio.py`, `momentum.py`, `momentum_risk.py`,
  `selezione_oggi.py`) applicano 0,2% per lato sul turnover; nella ricerca sui singoli segnali i rendimenti
  sono lordi, quindi sottrarre 0,3-0,5% per operazione negli scenari operativi.
- **Il setup settimanale è rarissimo** (2-3 volte l'anno su tutto il listino) e più debole nell'ultimo decennio:
  serve un portafoglio, non un singolo titolo, e gestione del rischio (stop/size).
- **Medie mobili = indicatori ritardati**: confermano trend già iniziati.
- **Il volume non è un filtro statistico**: usalo come contesto/qualità dell'esecuzione.

---

## 6. Portafoglio: dal segnale alla strategia (esito: **nessun edge**)

`portafoglio.py` trasforma i segnali in una strategia misurabile: capitale 100.000 €, rischio 1% per
operazione, max 10 posizioni, stop 2,5 ATR, trailing 3-6 ATR, uscita al rientro sotto la MM200 o a 250 sedute,
**costi 0,2% per lato**. Periodo 2010-2026 (4.257 sedute, 130 titoli).

| Variante | CAGR | Sharpe | max DD | N | win | PF |
|---|---|---|---|---|---|---|
| **Universo equal-weight (buy & hold)** | **+12,8%** | **0,78** | −38,6% | — | — | — |
| Ingressi casuali · orizzonte 250 sedute (controllo) | +11,0% | 0,70 | −36,0% | 133 | 59% | 2,30 |
| Rottura grezza · orizzonte 250 sedute | +10,5% | 0,61 | −39,4% | 158 | 60% | 2,06 |
| Solo deep recovery · orizzonte 250 sedute | +9,0% | 0,38 | −53,6% | 143 | 58% | 2,09 |
| Score ≥ +3 · orizzonte 250 sedute | +6,7% | 0,46 | −49,5% | 120 | 49% | 1,73 |
| FTSE MIB (buy & hold) | +4,7% | 0,31 | −48,1% | — | — | — |
| Walk-forward (pesi ricalibrati ogni anno) · orizzonte | +2,7% | 0,34 | −23,3% | 48 | 69% | 2,06 |
| Score ≥ +3 · con trailing stop + uscita MM200 | +1,2% | 0,23 | −23,6% | 317 | 32% | 1,21 |
| Rottura grezza · con trailing stop + uscita MM200 | −2,9% | −0,14 | −53,0% | 1.670 | 29% | 0,89 |

**Cosa dicono questi numeri (lezione finale del progetto):**

1. **Niente batte il semplice buy & hold equal-weight dell'universo.** Né i filtri, né la rottura grezza,
   né gli ingressi casuali.
2. **Gli ingressi casuali rendono come le rotture** (+11,0% vs +10,5%): il timing della MM200 non aggiunge
   valore misurabile in portafoglio.
3. **Gli eventi selezionati non si traducono in alpha**: lo score ≥+3 aveva il miglior excess negli studi
   sugli eventi (+18,4% OOS) ma in portafoglio rende *meno* della rottura grezza. Motivo: gli slot di
   portafoglio finiscono su titoli correlati nel momento sbagliato — l'eccesso medio degli eventi non è
   un rendimento ottenibile.
4. **Il trail stop stretto distrugge un segnale a bassa frequenza** (−2,9% contro +10,5%): la gestione
   operativa è essa stessa una variabile, spesso più importante del segnale.
5. **Il walk-forward ricalibrato fallisce** (+2,7%): i pesi delle componenti cambiano di anno in anno
   (per esempio "vicino ai massimi" diventa +1 in 4 anni su 17, contro l'evidenza di lungo periodo).
6. **Cautela strutturale**: l'universo contiene i titoli ancora quotati oggi (survivorship) e molte mid/small
   cap che nel periodo hanno corso; il benchmark equal-weight è quindi distorto verso l'alto. La lettura
   onesta è che **il rialzo osservato è beta del mercato italiano, non alpha del metodo**.

**Conclusione operativa**: la rottura della MM200 su titoli italiani, anche filtrata con gli strumenti
migliori, **non è una strategia**. Lo scanner resta utile come strumento di *attenzione* (cosa sta cambiando
di stato), non come sistema di trading. Per proseguire servirebbe un'altra famiglia di segnali (es. ranking
cross-sectional, fattori, revisione degli utili, stagionalità) — non un ulteriore affinamento di questo.

## 7. Nuova famiglia di segnale: momentum cross-sectional (`momentum.py`)

Chiuso il filone "rottura della MM200" con esito nullo, il progetto cambia famiglia: invece di *quando* un
titolo rompe una media, si guarda **quali titoli sono più forti degli altri** (momentum cross-sectional),
la regolarità più documentata della letteratura finanziaria. Ribilanciamento mensile, costi inclusi,
controlli seri.

**Regole**: universo Piazza Affari; segnale = rendimento a 12 mesi terminante un mese prima del
ribilanciamento (P[i−1]/P[i−13]−1, il classico "12-1"); portafoglio dei 10 titoli migliori equipesati,
ribilanciato ogni mese; turnover reale con costi 0,2% per lato; filtri di liquidità.

### 7.1 Risultati (2010-2026, capitale 100.000 €, costi inclusi)

| Variante | CAGR | Sharpe | max DD | turnover/mese |
|---|---|---|---|---|
| **MOM 12-1, top 10 + filtro MM200** | **+17,7%** | **0,85** | −34% | 28% |
| **MOM 12-1, top 10** | **+17,2%** | **0,81** | −36% | 25% |
| MOM 6 mesi, top 10 | +16,0% | 0,78 | −39% | 35% |
| MOM 12-1, top 20 | +15,9% | 0,88 | −32% | 20% |
| MOM corretto per volatilità, top 10 | +15,4% | 0,84 | −37% | 26% |
| Universo equipesato (buy & hold) | +11,7% | 0,70 | −33% | — |
| FTSE MIB (buy & hold) | +5,1% | 0,35 | −44% | — |
| **Portafogli casuali (30 seed)** | **+5,0%** (5°-95°: +0,8%…+8,9%) | 0,35 | −41% | — |
| **Peggiori 10 (controllo inverso)** | **−5,4%** | −0,05 | −62% | 23% |

### 7.2 Le tre domande che contano (tutte con risposta positiva)

1. **L'ordinamento esiste?** Sì: migliori +17,2% contro peggiori −5,4% → **spread di 22,6 punti** l'anno.
2. **Battono il caso?** Sì: +17,2% contro +5,0% medio dei portafogli casuali, e **sopra il 95° percentile**
   di tutti i 30 seed (+8,9%).
3. **Battono il semplice beta italiano?** Sì: +17,2% contro +11,7% dell'universo equipesato (Sharpe 0,81 vs 0,70).

### 7.3 Stabilità e limiti

- **In-sample / out-of-sample**: 14,6% nel 2010-2017 → 18,5% nel 2018-2026 (nessuna ri-ottimizzazione);
  il controllo inverso resta negativo in entrambi i periodi (−3,9% → −6,8%). L'effetto è stabile, non un
  artefatto di un'unica finestra.
- **Liquidità**: senza filtro il CAGR sale a +25,7% (Sharpe 1,09) — una parte del rendimento è **premio di
  illiquidità** delle micro-cap. Con soglia 2 M€/giorno → +15,8%; con 5 M€/giorno → +12,6% (sempre sopra
  universo e random). Il segnale è reale ma la **capacità è limitata**.
- **Rischio**: momentum crash documentati — 2018 −21,6%, 2022 −23,9%; drawdown fino a −36%. Il fattore
  perde in modo brusco quando il regime gira: serve disciplina, non leva.
- **Limiti noti**: universo di soli titoli quotati oggi (survivorship), costi forfettari, nessuna tassa,
  ribilanciamento a prezzi di chiusura senza slippage.

### 7.5 Gestione del rischio sul momentum (`momentum_risk.py`)

Tre strumenti testati uno per uno e in combinazione (stessa disciplina: costi, controllo casuale, IS/OOS):

| Variante | CAGR | Sharpe | max DD | turnover/mese | esposizione |
|---|---|---|---|---|---|
| **② + buffer di rank 5** | **+18,7%** | **0,96** | −33,7% | **14,5%** | 100% |
| ③ + ribilanciamento trimestrale (buffer 5) | +15,9% | 0,89 | −30,9% | **10,8%** | 100% |
| ① Base mensile + filtro MM200 | +17,1% | 0,88 | −33,8% | 24,3% | 100% |
| ④ + volatility targeting 15% | +14,2% | 0,83 | −31,6% | 24,3% | 85% |
| Universo equipesato (benchmark) | +11,7% | 0,70 | −32,6% | — | 100% |
| ⓪ Controllo: portafogli casuali (20 seed) | +6,3% | 0,41 | −39,8% | — | 100% |
| ⑧ + buffer + VT + overlay drawdown | +5,0% | 0,43 | −28,6% | 14,5% | 49% |
| ⑥ + overlay drawdown (15%/25%) | +4,0% | 0,34 | −31,4% | 24,3% | 54% |
| ⑤ + overlay trend su equity (MA10) | +2,7% | 0,27 | −38,1% | 24,3% | 43% |
| ⑦ Combinato trimestrale + VT + MA10 | +1,8% | 0,23 | −34,5% | 10,8% | 37% |

**Le tre lezioni (in ordine di importanza):**

1. **Il buffer di rank è il vero "risk management"**: dimezza il turnover (24,3% → 14,5%) e *migliora* CAGR
   (+18,7%) e Sharpe (0,96). Riduce il rumore da ribilanciamento — cioè le vendite/acquisti inutili che
   generano costi senza informazione. Stabile IS/OOS (17,6% → 18,2%).
2. **Gli overlay sull'equity della strategia distruggono il rendimento**: l'overlay trend MA10 lascia il
   portafoglio in cash il **57% dei mesi**, riduce il CAGR a +2,7% e allunga la durata del drawdown a
   **123 mesi** (whipsaw: la volatilità del momentum è mensile, la media a 10 mesi arriva sempre tardi).
   L'overlay di drawdown è instabile (+13,2% IS → **−3,9% OOS**).
3. **Il volatility targeting riduce il rischio ma costa rendimento**: drawdown −31,6% contro −33,8%,
   ma CAGR +14,2% contro +17,1% e Sharpe leggermente inferiore. Utile solo se esiste un vincolo di rischio
   (es. marginazione, target di volatilità di mandato), non per migliorare i risultati.

**Raccomandazione finale del filone momentum**: segnale 12-1, top 10, filtro MM200, **buffer di rank 5**,
ribilanciamento mensile (o trimestrale se il risparmio fiscale conta più della reattività). Niente overlay
sull'equity: il modo giusto di gestire il rischio del momentum è la **diversificazione** (10+ titoli) e la
**size**, non lo stop sull'equity della strategia.

### 7.4 Il contrasto che chiude il progetto

| Famiglia di segnale | Esito |
|---|---|
| Rottura della MM200 (con qualunque filtro: volume, regime, volatility, struttura) | **nessun edge** in portafoglio (pari al caso) |
| **Momentum cross-sectional (12-1, top 10, mensile)** | **edge presente e stabile** IS/OOS, batte caso e beta |

Il motivo è concettuale: la rottura della media è un **segnale di timing** sullo stesso titolo (molto
rumore, poco contenuto informativo); il momentum è un **segnale di selezione** che ordina *tutti* i titoli
tra loro — e funziona perché sfrutta un premio al rischio documentato (e limiti all'arbitraggio), non un
pattern grafico.

## 8. Stato del progetto

**Fatto e funzionante**
- [x] Universo Piazza Affari (130 ticker MIB/Mid/STAR) + verifica dei delistati
- [x] Scanner MM200: metriche, etichette, punteggio, score validato OOS, report HTML
- [x] Ricerca rottura MM200: backtest, volume lab (13 misure), filtri lab (22 candidati)
- [x] Controlli: baseline di stato, finestre non sovrapposte, split decenni, leave-one-out
- [x] Verifica out-of-sample + validazione esterna su 56 titoli europei
- [x] Portafoglio (stop, sizing, costi, walk-forward) → **la rottura della MM200 non è una strategia**
- [x] Momentum cross-sectional → **edge presente e stabile** (batte caso e beta; capacità limitata)
- [x] **Risk management sul momentum**: buffer di rank (vince), volatility targeting (neutro),
      overlay di drawdown/trend (distruttivi: whipsaw) → **raccomandazione finale definita**
- [x] Documentazione: metodo, numeri, fonti e limiti per ogni modulo

**Esito complessivo in due frasi**: la rottura della media mobile a 200 periodi non ha edge in portafoglio
(nessun filtro la salva: volume inutile, filtri = market timing, excess di evento ≠ alpha). Il momentum
cross-sectional ha un edge reale e stabile, ma la sua gestione del rischio efficace è il **buffer di
ribilanciamento** e la diversificazione — non gli stop o gli overlay, che distruggono valore.

**Possibili estensioni**
- [ ] Combinazione momentum + low-volatility / qualità (fattori multipli, decorrelati)
- [ ] Fattori fondamentali (revisioni degli utili) come terza famiglia di segnale
- [ ] Notifiche post-chiusura del ranking e dei cambi di composizione del portafoglio modello
- [ ] Analisi fiscale (compensazione minus/plusvalenze) sul turnover trimestrale vs mensile
