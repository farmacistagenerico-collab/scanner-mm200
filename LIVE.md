# LIVE — renderlo sempre aggiornato, sempre acceso, raggiungibile da ovunque

Tre obiettivi, in ordine di difficoltà:

| Obiettivo | Cosa serve | Dove lo vedi |
|---|---|---|
| **1. Si aggiorna da sola** | `dashboard.py` (già pronto: refresh completo ogni N minuti, prezzi ogni minuto) | pagina servita dal server |
| **2. Resta accesa** | avvio automatico all'accensione del PC (systemd / launchd / Task Scheduler) | idem, senza aprirla a mano |
| **3. La vedi da ovunque** | rete locale, Tailscale (consigliato) o VPS | telefono, tablet, altro PC |
| **4. (alternativa) tutto in cloud** | **GitHub Actions + Pages**: si aggiorna da sola, senza PC | URL pubblico, sempre online |

> ☁️ **Se non vuoi tenere nessun computer acceso**, salta ai passi 1-3 e usa il deploy su GitHub:
> guida completa in [`deploy/PUBBLICA_SU_GITHUB.md`](deploy/PUBBLICA_SU_GITHUB.md) (gratis, aggiornamento
> 2 volte al giorno, tasto "Aggiorna su GitHub" per l'aggiornamento a richiesta).

---

## 1. Aggiornamento automatico (già incluso)

Il server ha un pianificatore interno:

- **prezzi ogni 60 secondi**, ma **solo a mercato aperto** (lun-ven 9:00-17:40, ora di Milano);
- **refresh completo ogni 20 minuti** a mercato aperto (dati, MM200, ranking, punteggi, classifica,
  curva equity, vista statica): configurabile con `ogni_minuti` in `config_live.json` o `--ogni-minuti 30`;
- **notifiche** quando cambia il verdetto o quando arriva il giorno della verifica (Telegram/email, vedi §4);
- il browser non deve restare aperto: **il lavoro lo fa il server**, la pagina è solo la finestra.

```bash
python3 dashboard.py --ogni-minuti 30        # refresh completo ogni 30 minuti
python3 dashboard.py --ogni-minuti 0         # solo prezzi, refresh completo solo su richiesta
```

---

## 2. Sempre acceso: avvio automatico

### Linux — systemd (utente)

```bash
cp deploy/scanner-dashboard.service ~/.config/systemd/user/
# sostituisci /percorso/scanner_mm200 con il percorso vero (2 punti: WorkingDirectory e Documentation)
nano ~/.config/systemd/user/scanner-dashboard.service
systemctl --user daemon-reload
systemctl --user enable --now scanner-dashboard
loginctl enable-linger $USER          # fa partire il servizio anche senza login
journalctl --user -u scanner-dashboard -f
```

### macOS — launchd

```bash
cp deploy/com.piazzaaffari.dashboard.plist ~/Library/LaunchAgents/
# sostituisci i 3 percorsi /percorso/scanner_mm200
launchctl load -w ~/Library/LaunchAgents/com.piazzaaffari.dashboard.plist
tail -f output/dashboard.log
```

### Windows — Task Scheduler (o cartella Esecuzione automatica)

Opzione A (consigliata): doppio click su `deploy\installa_windows.bat` — crea l'attività
"Dashboard Piazza Affari" che parte all'accesso e la avvia subito.

Opzione B: premi `WIN+R`, digita `shell:startup` e incolla lì un collegamento a `avvia_dashboard.bat`.

### Raspberry Pi / mini PC (opzione "sempre acceso" a basso costo)

Un Raspberry Pi 4/5 acceso 24/7 consuma ~5 W: è la soluzione tipica per tenere la dashboard sempre viva
senza lasciare il PC principale acceso. Stessa procedura systemd. La dashboard non fa calcoli pesanti
(il refresh completo dura ~15 s), quindi 2 GB di RAM bastano.

---

## 3. Vederla da ovunque

### 3.1 Solo rete di casa (il più semplice, zero configurazione)

Il server ascolta su `0.0.0.0`, quindi è già raggiungibile dagli altri dispositivi della stessa rete:

1. trova l'IP del PC che la ospita: `ipconfig` (Windows) o `ip addr` / `ifconfig` (mac/Linux);
2. dal telefono apri `http://192.168.1.XX:8000` (stessa rete Wi-Fi);
3. in Windows, alla prima richiesta, consenti l'accesso alla rete privata nel firewall.

### 3.2 Da fuori casa — **Tailscale** (consigliato)

Tailscale crea una rete privata cifrata fra i tuoi dispositivi: **non esponi nulla a Internet**, nessuna
configurazione di router, gratuito per uso personale.

```bash
# sul PC che ospita la dashboard e sul telefono (app Tailscale)
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip -4          # es. 100.101.102.103
```

Da qualsiasi posto: `http://100.101.102.103:8000`. Attiva l'`auth` nella configurazione (§5) e sei a posto.

Alternative: **Cloudflare Tunnel** (`cloudflared tunnel --url http://localhost:8000`) o **ngrok** — più
semplici da dimostrare, ma il servizio passa da un terzo. Un **VPS** (5-10 €/mese) è l'opzione più solida
se vuoi che la dashboard viva anche a PC spento: copia la cartella, avvia come servizio systemd e proteggi
con password + HTTPS (Caddy o Nginx con Let's Encrypt).

---

## 4. Notifiche (Telegram o email)

Copia `config_live.example.json` in `config_live.json` e compila solo la parte che ti interessa.

### Telegram (2 minuti)

1. su Telegram cerca **@BotFather** → `/newbot` → scegli un nome → ottieni il **token**;
2. scrivi un messaggio al tuo bot, poi apri
   `https://api.telegram.org/bot<IL_TUO_TOKEN>/getUpdates` e copia il **chat_id**;
3. nel file:

```json
{ "telegram": { "token": "123456:ABC-DEF...", "chat_id": "987654321" },
  "ogni_minuti": 20, "digest_ora": "09:10" }
```

### Email (SMTP)

```json
{ "smtp": { "host": "smtp.gmail.com", "porta": 587, "utente": "tuo@gmail.com",
             "password": "password-per-le-app", "a": "tuo@gmail.com" } }
```

Con Gmail serve una **password per le applicazioni** (non quella dell'account).

### Cosa arriva, e quando

| Evento | Messaggio |
|---|---|
| Cambio di verdetto (es. da "non fare nulla" a "attenzione") | "Cambio di verdetto: …" + il titolo con punteggio più alto |
| Giorno della verifica mensile | "È il momento della verifica del mese" (una volta al mese) |
| `digest_ora` (opzionale) | riepilogo del mattino: verdetto, titoli in portafoglio, prossima verifica |

Prova subito: `python3 dashboard.py --notifica-prova`

---

## 5. Protezione con password (se la esponi in rete)

```bash
python3 dashboard.py --utente mario --password unapasswordlunga
# oppure, in modo permanente:
# config_live.json -> "auth": {"utente": "mario", "password": "unapasswordlunga"}
```

Il browser chiede utente e password la prima volta (HTTP Basic). È sufficiente su Tailscale o in rete
locale; **se la esponi su Internet mettila dietro HTTPS** (Caddy/Nginx): le credenziali Basic senza TLS
viaggiano in chiaro.

---

## 6. Controlli che vale la pena fare una volta al mese

```bash
python3 operativita_oggi.py --solo-verdetto    # coerenza col server
python3 selezione_oggi.py --attuale output/portafoglio_attuale.csv   # la verifica vera del mese
tail -n 50 output/dashboard.log                # log del servizio (se avviato come servizio)
cat output/stato_live.json                     # ultimo verdetto notificato
```

Nota sui dati: il feed gratuito Yahoo Finance ha un **ritardo tipico di 15 minuti** e qualche volta
risponde 429 (troppe richieste). In quel caso la pagina lo segnala, conserva l'ultimo stato valido e il
refresh successivo riprova: nessun intervento necessario.

---

## 7. Riepilogo: la configurazione "live e completa" in 6 righe

```bash
cd scanner_mm200
python3 -m pip install -r requirements.txt   # oppure: pip install yfinance pandas numpy scipy
cp config_live.example.json config_live.json # compila telegram/smtp + ogni_minuti
python3 dashboard.py --no-browser            # oppure avvia_dashboard.sh / .bat
# poi: avvio automatico (§2) e accesso da fuori (§3.2), password (§5)
```

Da lì in avanti: apri la pagina quando vuoi, **i dati sono già aggiornati**, e quando serve fare
qualcosa **te lo dice lei** (notifica) invece che tu a controllare.
