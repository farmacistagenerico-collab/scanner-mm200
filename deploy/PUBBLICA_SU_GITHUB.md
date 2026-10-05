# Pubblicare su GitHub — dashboard sempre aggiornata, senza PC acceso

**Cosa ottieni:** un indirizzo tipo `https://tuonome.github.io/scanner-mm200/` che si aggiorna
**da solo due volte al giorno nei feriali** (mattina presto e dopo la chiusura di Milano), con i grafici,
i punteggi, la classifica e la curva della strategia. Nessun computer da tenere acceso, nessun server da
mantenere, costo zero.

Come funziona: **GitHub Actions** esegue un job programmato che scarica i dati, ricalcola tutto e
**GitHub Pages** pubblica la pagina. Il tasto "Aggiorna su GitHub" nella pagina pubblicata fa partire
il job a mano quando vuoi.

---

## Prima di iniziare

- un account [GitHub](https://github.com) (gratuito);
- il progetto sul tuo computer (questa cartella);
- opzionale: `git` installato. In alternativa si può caricare tutto dal sito, trascinando i file.

> **Attenzione — repo pubblico.** Su GitHub free con Pages il repository deve essere **pubblico**: chiunque
> potrà vedere il codice **e la pagina pubblicata** (che mostra il portafoglio e i punteggi). Se non vuoi
> rendere pubbliche le posizioni, vedi "Se vuoi tenere le posizioni private" in fondo.

---

## Passo 1 — Crea il repository

1. vai su [github.com/new](https://github.com/new);
2. **Repository name**: `scanner-mm200` (o il nome che preferisci);
3. **Public** ✔, **non** spuntare README/.gitignore/licenza (li hai già);
4. **Create repository**.

GitHub ti mostrerà una pagina con i comandi: tienila aperta per il passo 2.

---

## Passo 2 — Carica il codice

### Opzione A — da terminale (consigliata)

Nella cartella del progetto:

```bash
cd scanner_mm200

# il workflow di aggiornamento deve stare in .github/workflows/
mkdir -p .github/workflows
cp deploy/github-actions/aggiorna.yml .github/workflows/aggiorna.yml

git init
git add .
git commit -m "Dashboard Piazza Affari: scanner, strategia, punteggi"
git branch -M main
git remote add origin https://github.com/TUONOME/scanner-mm200.git
git push -u origin main
```

Al primo `push` GitHub chiede le credenziali: usa un **token personale** (Settings → Developer settings →
Personal access tokens → Fine-grained token, permesso *Contents: Read and write* sul repository) come
password, oppure configura una chiave SSH.

Il `.gitignore` è già pronto: **non** vengono caricati `cache/` (56 MB di dati, ricostruiti in automatico),
`config_live.json` (le tue credenziali) e i file di lavoro.

### Opzione B — dal sito, senza terminale

1. nella pagina del repository: **Add file → Upload files**;
2. trascina **tutti i file del progetto** (tranne `cache/`), e assicurati che fra questi ci sia
   `.github/workflows/aggiorna.yml` (crea la cartella così com'è: se hai difficoltà, carica prima tutto il
   resto e poi, con **Add file → Create new file**, scrivi come nome
   `.github/workflows/aggiorna.yml` e incolla il contenuto del file che trovi in `deploy/github-actions/`);
3. **Commit changes**.

---

## Passo 3 — Attiva GitHub Pages

1. nel repository: **Settings → Pages**;
2. **Source**: scegli **GitHub Actions** (non "Deploy from a branch");
3. salva.

---

## Passo 4 — Primo aggiornamento

1. scheda **Actions** → a sinistra **"Aggiorna dashboard"** → pulsante **Run workflow** → **Run workflow**;
2. attende 3-6 minuti (il primo giro scarica 130 titoli e costruisce la cache dei punteggi);
3. quando il job è verde ✅, la pagina è online:

```
https://TUONOME.github.io/scanner-mm200/
```

Aprilo dal telefono e aggiungilo alla schermata Home (Safari: Condividi → "Aggiungi a Home";
Chrome: menu ⋮ → "Aggiungi a schermata Home"): diventa un'app.

---

## Cosa succede da qui in avanti

| Quando | Cosa |
|---|---|
| ogni feriale ~08:30 e ~17:45 (ora di Milano) | il job gira da solo e ripubblica la pagina |
| quando tocchi "Aggiorna su GitHub" nella pagina | parte un job immediato (utile dopo un movimento di mercato) |
| il primo giorno del mese (o quando vuoi) | apri il job e guarda il riepilogo: il verdetto dice se è il momento della verifica |

Dettagli utili:

- **la cache dei dati** (56 MB) vive in Actions, non nel repository: dopo il primo giro i successivi
  partono in ~1 minuto;
- **se il job fallisce** GitHub ti manda un'email: quasi sempre è Yahoo Finance che risponde "troppe
  richieste" (`429`) — basta rilanciare il job;
- **il repository resta leggero** (~1 MB di codice + report HTML).

---

## Se vuoi cambiare qualcosa

| Cosa | Dove |
|---|---|
| orari di aggiornamento | `.github/workflows/aggiorna.yml`, righe `cron` (**in UTC**: `45 15 * * 1-5` = 17:45 a Milano d'estate) |
| parametri della strategia (liquidità, N titoli, buffer) | `dashboard.py`, costanti `N_TITOLI`, `BUFFER`, `LIQ` in alto |
| composizione dell'universo | `titoli_italiani.py` |
| pagine pubblicate | `.github/workflows/aggiorna.yml`, step "Prepara il sito" |

Dopo una modifica: `git add . && git commit -m "cambio" && git push`.

---

## Se vuoi tenere le posizioni private

Tre strade, dalla più semplice:

1. **non pubblicare le schede titolo**: nel workflow, dopo `dashboard.py --una-tantum`, sostituisci
   `output/index.html` con `output/punteggio.html` (mostra i punteggi ma non il portafoglio) — oppure
   pubblica solo i report di ricerca;
2. **repository privato**: Pages funziona anche con repo privato ma richiede **GitHub Pro** (~4 $/mese);
3. **aggiornamento in cloud senza pubblicare**: tieni il workflow che aggiorna e ti **manda i risultati via
   email/Telegram** (configura i secrets `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`, poi nel job aggiungi
   `env: TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}` e usa gli stessi comandi che usi in locale).

---

## Alternativa: come "sito normale" (senza Actions)

Se preferisci pubblicare da solo, senza job automatici, va bene qualsiasi hosting statico
(Cloudflare Pages, Netlify, Vercel): carica `output/index.html` (e `punteggio.html`) e rigenerali sul tuo
PC quando vuoi con `python3 dashboard.py --una-tantum`.

---

## Riepilogo dei file del deploy

| File | A cosa serve |
|---|---|
| `deploy/github-actions/aggiorna.yml` | il workflow: da copiare in `.github/workflows/aggiorna.yml` |
| `.gitignore` | tiene fuori credenziali, cache da 56 MB e file di lavoro |
| `bootstrap_dati.py` | ricostruisce le cache al primo avvio (in CI come sul tuo PC) |
| `dashboard.py --una-tantum` | fa un giro completo e scrive `output/index.html`, senza tenere il server acceso |
| `requirements.txt` | le dipendenze per la CI |
