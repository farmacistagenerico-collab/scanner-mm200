#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DASHBOARD LIVE — punteggi aggiornabili in tempo reale da un tasto
=================================================================

Server locale (solo libreria standard) che serve una pagina con:

  - il **punteggio statistico** di ogni titolo del portafoglio,
  - il **verdetto di oggi** ("oggi non fare nulla" / "verifica" / "attenzione"),
  - il **margine** di ogni titolo sul livello di uscita,
  - il tasto **⟳ AGGIORNA ORA**: riscarica i dati di mercato e ricalcola tutto,
  - l'auto-aggiornamento dei prezzi (ogni 60 s, solo a mercato aperto),
  - l'ora dell'ultimo aggiornamento e la fonte dei prezzi.

Uso:
    python3 dashboard.py                 # apre il server su http://localhost:8000
    python3 dashboard.py --porta 8000    # porta diversa
    python3 dashboard.py --no-browser    # non tentare di aprire il browser

Nel workspace il server è visibile come anteprima live; in locale si apre
http://localhost:8000 nel browser.

Note:
  - i dati arrivano da Yahoo Finance: i prezzi intraday hanno in genere 15 minuti
    di ritardo (feed gratuito). Non è un feed di trading;
  - l'aggiornamento completo (~10-20 s) riscarica 130 titoli e ricalcola MM200,
    ranking e punteggi; l'aggiornamento rapido (~2 s) aggiorna solo i prezzi dei
    titoli in portafoglio e dei candidati.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import warnings
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import titoli_italiani as tu      # noqa: E402
import selezione_oggi as so       # noqa: E402
import operativita_oggi as oo     # noqa: E402
import punteggio as pg            # noqa: E402
import grafici as gr              # noqa: E402
import indicatori as ind          # noqa: E402

ROMA = ZoneInfo("Europe/Rome")          # il server può girare in UTC: gli orari sono di Milano

CONFIG_PATH = os.path.join(BASE_DIR, "config_live.json")


def carica_config() -> dict:
    """Configurazione opzionale: aggiornamento automatico, notifiche, password."""
    cfg = {"ogni_minuti": 20, "digest_ora": "", "telegram": {}, "smtp": {}, "auth": {}}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception as e:
            print(f"[config] {CONFIG_PATH}: {e}")
    return cfg


CFG = carica_config()
STATO_FILE = os.path.join(BASE_DIR, "output", "stato_live.json")

# se giriamo dentro GitHub Actions, la pagina statica può rimandare al workflow per l'aggiornamento
# ---------------------------------------------------------------------------
#  Multi-mercato: pagine, etichette e affidabilità misurata
# ---------------------------------------------------------------------------
PAGINE_MERCATO = {"IT": "index.html", "DE": "de.html", "FR": "fr.html"}

AFFIDABILITA = {
    # numeri dal backtest 2010-2026 (momentum_risk.py --mercato XX)
    "IT": ("ok", "Selezione 12-1 + MM200 + buffer 5: +18,7% annuo contro +12,8% "
                 "dell'insieme dei titoli liquidi e +6,3% dei titoli estratti a caso. Metodo validato."),
    "DE": ("ok", "Selezione 12-1 + MM200: +17,0% annuo contro +13,4% dell'insieme dei titoli liquidi "
                 "e +6,2% dei titoli estratti a caso (primo periodo +17,1%, secondo +16,6%: stabile). Metodo validato."),
    "FR": ("attenzione", "In Francia la selezione NON ha battuto l'insieme dei titoli liquidi: "
                         "+10,8% contro +11,1% annuo dal 2010, e nel secondo periodo +6,0% contro +6,2%. "
                         "Usa questa pagina come monitor, non come strategia operativa."),
}


def _etichetta_mercato():
    m = tu.info()
    return f"{m['nome']} ({m['paese']})"


def _tabs_html():
    cod = tu.mercato
    pezzi = []
    for c in tu.elenco_mercati():
        m = tu.MERCATI[c]
        attivo = c == cod
        stile = ("background:#0f172a;color:#fff;font-weight:800"
                 if attivo else "background:#e2e8f0;color:#334155;font-weight:600")
        pezzi.append(f'<a href="{PAGINE_MERCATO[c]}" style="text-decoration:none;border-radius:9px;'
                     f'padding:8px 14px;font-size:13.5px;{stile}">{m["paese"]}</a>')
    return ('<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 10px">'
            '<span style="font-size:12px;letter-spacing:1px;text-transform:uppercase;color:#64748b;'
            'font-weight:700;margin-right:4px">Mercato</span>' + "".join(pezzi) + '</div>')


def _nota_affidabilita_html():
    stato, testo = AFFIDABILITA.get(tu.mercato, ("ok", ""))
    if stato == "ok":
        bordo, sfondo, icona = "#bbf7d0", "#f0fdf4", "✅"
        colore_titolo = "#166534"
    else:
        bordo, sfondo, icona = "#fde68a", "#fffbeb", "⚠️"
        colore_titolo = "#92400e"
    return (f'<div style="background:{sfondo};border:1px solid {bordo};border-radius:12px;padding:13px 16px;'
            f'margin-top:12px;font-size:13px;color:#334155;line-height:1.65">'
            f'<b style="color:{colore_titolo}">{icona} Affidabilità del metodo su questo mercato</b><br>{testo}</div>')


REPO_CI = os.environ.get("GITHUB_REPOSITORY", "")
URL_WORKFLOW = (f"https://github.com/{REPO_CI}/actions/workflows/aggiorna.yml"
                if REPO_CI else "")


def adesso() -> datetime:
    return datetime.now(ROMA)


OUT_DIR = os.path.join(BASE_DIR, "output")
CACHE_LIVE = os.path.join(BASE_DIR, "cache", "scanner_live.pkl")
CACHE_STORICO = os.path.join(BASE_DIR, "cache", "momentum_raw.pkl")
N_TITOLI, BUFFER, LIQ = 10, 5, 2_000_000.0

# ---------------------------------------------------------------------------
# stato condiviso
# ---------------------------------------------------------------------------

S = {
    "tab": None,            # tabella dei titoli (metriche di oggi)
    "modello": None,        # (b, mu, sd) del modello logistico
    "oss": None,            # casi storici (per affidabilità del dato)
    "tenuti": [],           # portafoglio attuale
    "attesa": None,         # candidati in attesa
    "righe": None,          # righe della tabella mostrata
    "verdetto": "", "prossima": None, "giorni_borsa": 0,
    "contesto": {},
    "ultimo_full": None, "ultimo_prezzo": None,
    "fonte": "avvio", "in_corso": False, "messaggio": "",
    "errore": "",
    "prezzi_intraday": {},
    "storico": {},          # ticker -> serie (date, close, mm200) per i grafici
    "chiusure_ufficiali": {},   # ticker -> ultima chiusura di seduta (riferimento per la variazione "oggi")
}
LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# notifiche
# ---------------------------------------------------------------------------

def invia_notifica(testo: str) -> bool:
    """Manda il messaggio su Telegram e/o via email; se non configurato, stampa."""
    inviato = False
    tg = CFG.get("telegram") or {}
    if tg.get("token") and tg.get("chat_id"):
        try:
            dati = urllib.parse.urlencode({
                "chat_id": tg["chat_id"], "text": testo, "disable_web_page_preview": "true"}).encode()
            req = urllib.request.Request(
                "https://api.telegram.org/bot" + tg["token"] + "/sendMessage", data=dati)
            with urllib.request.urlopen(req, timeout=12) as r:
                inviato = r.status == 200
        except Exception as e:
            print(f"[notifica] telegram: {e}")

    sm = CFG.get("smtp") or {}
    if sm.get("host") and sm.get("a"):
        try:
            import smtplib
            from email.message import EmailMessage
            msg = EmailMessage()
            msg["Subject"] = "Dashboard Piazza Affari"
            msg["From"] = sm.get("utente") or sm["host"]
            msg["To"] = sm["a"]
            msg.set_content(testo)
            with smtplib.SMTP(sm["host"], int(sm.get("porta", 587)), timeout=15) as srv:
                srv.starttls()
                if sm.get("utente"):
                    srv.login(sm["utente"], sm.get("password", ""))
                srv.send_message(msg)
            inviato = True
        except Exception as e:
            print(f"[notifica] email: {e}")

    print("[notifica] " + testo.replace(chr(10), " | "))
    return inviato


def _leggi_stato_file() -> dict:
    try:
        if os.path.exists(STATO_FILE):
            with open(STATO_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _scrivi_stato_file(d: dict):
    try:
        os.makedirs(os.path.dirname(STATO_FILE), exist_ok=True)
        with open(STATO_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[stato] {e}")


def _notifica_cambi(verdetto: str, dettaglio: str = ""):
    """Avvisa quando cambia il verdetto o quando è il momento della verifica."""
    prec = _leggi_stato_file()
    messaggi = []
    if prec.get("verdetto") and prec["verdetto"] != verdetto:
        messaggi.append("Cambio di verdetto: " + verdetto)
    if "verifica" in verdetto.lower() and prec.get("verifica_notificata") != f"{adesso():%Y-%m}":
        messaggi.append("È il momento della verifica del mese: " + verdetto)
        prec["verifica_notificata"] = f"{adesso():%Y-%m}"
    if messaggi:
        testo = "Dashboard Piazza Affari - " + f"{adesso():%d/%m %H:%M}" + chr(10) + chr(10).join(messaggi)
        if dettaglio:
            testo += chr(10) + dettaglio
        invia_notifica(testo)
    prec["verdetto"] = verdetto
    prec["aggiornato"] = adesso().isoformat(timespec="seconds")
    _scrivi_stato_file(prec)


# ---------------------------------------------------------------------------
# calcolo
# ---------------------------------------------------------------------------

def _carica_storico():
    if not os.path.exists(CACHE_STORICO):
        return None
    try:
        C, L, D, V = pg.pannelli_storici(pd.read_pickle(CACHE_STORICO))
        oss = pg.casi_storici(C, L, D, V)
        return oss if len(oss) >= 300 else None
    except Exception:
        return None


def _aggiorna_modello():
    oss = S["oss"]
    if oss is None:
        return
    X = oss[pg.FEATURES].values.astype(float)
    y = oss["positivo"].values.astype(float)
    S["modello"] = pg._fit(X, y)


def _storico_serie(raw, tickers, barre=200) -> dict:
    """Ultime `barre` chiusure + MM200 per ogni ticker (per i grafici)."""
    out = {}
    for t in tickers:
        try:
            c = raw[t].dropna(subset=["Close"])["Close"]
        except Exception:
            continue
        if len(c) < 60:
            continue
        mm = ind.sma(c, 200)
        out[t] = {"d": [str(x.date()) for x in c.index[-barre:]],
                  "c": [float(x) for x in c.values[-barre:]],
                  "mm": [float(x) if np.isfinite(x) else float("nan") for x in mm.values[-barre:]]}
    return out


def _aggiungi_punto(serie: dict, prezzo: float, oggi: str) -> dict:
    """Inserisce/aggiorna il prezzo intraday nella serie storica."""
    c = list(serie["c"])
    d = list(serie["d"])
    mm = list(serie["mm"])
    ultima_200 = c[-200:]
    nuovo_mm = float(np.mean(ultima_200)) if len(ultima_200) >= 200 else mm[-1]
    if not np.isfinite(nuovo_mm):
        nuovo_mm = prezzo
    if d and d[-1] == oggi:
        c[-1], mm[-1] = prezzo, nuovo_mm
    else:
        d.append(oggi); c.append(prezzo); mm.append(nuovo_mm)
        if len(c) > 200:
            c.pop(0); d.pop(0); mm.pop(0)
    return {"d": d, "c": c, "mm": mm}


def _grafico(ticker: str, nome: str, punteggio: float, target: float,
             delta: float | None) -> str:
    st = S["storico"].get(ticker)
    if not st or len(st["c"]) < 20:
        return ""
    prezzo = st["c"][-1]
    uscita = st["mm"][-1]
    if not np.isfinite(uscita):
        uscita = prezzo
    return gr.grafico_prezzo(nome, punteggio, st["d"], st["c"], st["mm"],
                             uscita, target, delta=delta)


def _score_righe(tab: pd.DataFrame, universo: pd.DataFrame | None = None,
                 con_grafico: bool = True) -> pd.DataFrame:
    """
    Punteggio per i titoli indicati.

    `universo` serve a calcolare il momentum relativo nel paniere esattamente come
    nel modello (percentile fra TUTTI i titoli liquidi sopra la MM200): senza,
    il percentile verrebbe calcolato sul sottoinsieme passato.
    """
    if S["modello"] is None:
        return pd.DataFrame()
    base = tab if universo is None else universo
    confini_mom = [float(S["oss"]["mom_%"].quantile(1 / 3)), float(S["oss"]["mom_%"].quantile(2 / 3))]
    confini_dist = [float(S["oss"]["dist_%"].quantile(1 / 3)), float(S["oss"]["dist_%"].quantile(2 / 3))]
    n_gruppi = pg.affidabilita_gruppi(S["oss"], confini_mom, confini_dist)
    med_globale = float(S["oss"]["esito_12m_%"].median())
    b, mu, sd = S["modello"]

    liq = base[base["turnover_mediano"] >= LIQ]
    elig = liq[liq["sopra_mm200"]]
    rk_elig = elig["mom_%"].rank(pct=True) * 100
    rk_liq = liq["mom_%"].rank(pct=True) * 100
    rk = rk_elig.reindex(base.index).fillna(rk_liq)      # fuori paniere: percentile fra i liquidi

    gm_h = pd.cut(S["oss"]["mom_%"], [-np.inf, *confini_mom, np.inf],
                  labels=["momentum moderato", "momentum alto", "momentum estremo"]).astype(str)
    gd_h = pd.cut(S["oss"]["dist_%"], [-np.inf, *confini_dist, np.inf],
                  labels=["vicino alla MM200", "sopra la MM200", "staccato dalla MM200"]).astype(str)

    righe = []
    for t in tab.index:
        r = tab.loc[t]
        feats = np.array([[float(rk.get(t, 50.0)), float(r["dist_mm200_%"]),
                           float(r["vol_annua_%"]) if np.isfinite(r["vol_annua_%"])
                           else float(S["oss"]["vol_%"].median())]])
        p = float(pg._pred(b, mu, sd, feats)[0] * 100)
        gm = pd.cut([r["mom_%"]], [-np.inf, *confini_mom, np.inf],
                    labels=["momentum moderato", "momentum alto", "momentum estremo"])[0]
        gd = pd.cut([r["dist_mm200_%"]], [-np.inf, *confini_dist, np.inf],
                    labels=["vicino alla MM200", "sopra la MM200", "staccato dalla MM200"])[0]
        gruppo = f"{gm} · {gd}"
        n = int(n_gruppi.get(gruppo, 0))
        sub = S["oss"][(gm_h == str(gm)) & (gd_h == str(gd))]
        if len(sub) < 30:
            sub = S["oss"][gm_h == str(gm)]
        med = float(sub["esito_12m_%"].median()) if len(sub) >= 30 else med_globale
        righe.append({
            "ticker": t, "nome": r["nome"], "prezzo": float(r["prezzo"]),
            "punteggio": round(p, 1), "gruppo": gruppo, "casi_simili": n,
            "affidabilita": "alta" if n >= 200 else ("media" if n >= 80 else "bassa"),
            "mediana_12m_%": round(med, 1),
            "livello_uscita": float(r["prezzo"] / (1 + r["dist_mm200_%"] / 100)),
            "dist_%": float(r["dist_mm200_%"]),
            "delta_oggi_%": float(r.get("delta_oggi_%", np.nan)),
            "mom_%": float(r["mom_%"]),
            "sopra_mm200": bool(r["sopra_mm200"]),
            "nel_paniere": bool(r["sopra_mm200"] and r["turnover_mediano"] >= LIQ),
            "turnover_M€": round(float(r["turnover_mediano"]) / 1e6, 1),
        })
    df = pd.DataFrame(righe).set_index("ticker").sort_values("punteggio", ascending=False)
    if con_grafico:
        grafici = {}
        for t, r in df.iterrows():
            grafici[t] = _grafico(t, r["nome"], r["punteggio"],
                                  r["prezzo"] * (1 + r["mediana_12m_%"] / 100),
                                  r["delta_oggi_%"] if np.isfinite(r["delta_oggi_%"]) else None)
        df["grafico"] = pd.Series(grafici)
    return df


def aggiorna_tutto(messaggio="aggiornamento completo"):
    """Riscarica i dati giornalieri dell'universo e ricalcola tutto."""
    with LOCK:
        S["in_corso"] = True
        S["messaggio"] = messaggio
        S["errore"] = ""
    try:
        try:
            raw = so.scarica("2y", usa_cache=False)
            fonte_dati = "download"
        except Exception as e:
            # senza rete (o senza yfinance) si usa l'ultima fotografia salvata: la pagina resta viva
            if os.path.exists(CACHE_LIVE):
                raw = pd.read_pickle(CACHE_LIVE)
                fonte_dati = "cache locale"
                with LOCK:
                    S["errore"] = f"download non disponibile ({type(e).__name__}): uso la cache locale"
            else:
                raise
        oggi = pd.Timestamp(adesso().date())
        tab = so.costruisci_tabella(raw, oggi)
        tab["livello_mm200"] = tab["prezzo"] / (1 + tab["dist_mm200_%"] / 100)
        tab["margin_%"] = tab["dist_mm200_%"]
        # variazione di giornata
        deltas = {}
        for t in tab.index:
            try:
                c = raw[t].dropna(subset=["Close"])["Close"]
                if len(c) >= 2:
                    deltas[t] = float(c.iloc[-1] / c.iloc[-2] - 1) * 100
            except Exception:
                continue
        tab["delta_oggi_%"] = pd.Series(deltas).reindex(tab.index)

        _, rank, breadth, regime, rotture, data_ultima = oo.stato_giorno(raw, oggi, LIQ, N_TITOLI, BUFFER)
        tenuti = leggi_portafoglio()
        # storico per TUTTO l'universo: i grafici vengono generati su richiesta
        S["storico"] = _storico_serie(raw, list(tab.index))
        S["chiusure_ufficiali"] = {t: float(tab.loc[t, "prezzo"]) for t in tab.index}
        stato = oo.verifica_stato(oggi, False, tab, rank, tenuti, N_TITOLI, BUFFER)

        if stato["oggi_verifica"]:
            verdetto = "È il momento della verifica: applica la regola per il mese nuovo"
        elif stato["sotto"] or stato["fuori_rank"]:
            verdetto = "Attenzione: qualche titolo è fuori regola (si decide a fine mese)"
        else:
            verdetto = "Oggi non devi fare nulla"

        with LOCK:
            S["tab"] = tab
            S["tenuti"] = tenuti
            S["verdetto"] = verdetto
            S["prossima"] = str(stato["prossima"].date())
            S["giorni_borsa"] = stato["giorni_borsa"]
            S["righe"] = _score_righe(tab.loc[[t for t in tenuti if t in tab.index]], tab)
            S["classifica"] = _classifica(tab)
            S["attesa"] = _candidati(tab)
            S["contesto"] = {
                "breadth_%": round(float(breadth), 0),
                "mib_sopra_mm200": bool(regime) if regime is not None else None,
                "rotture_5sedute": [t.replace(".MI", "") for t in rotture[:10]],
                "titoli": int(len(tab)),
            }
            S["ultimo_full"] = adesso().isoformat(timespec="seconds")
            S["ultimo_full_dt"] = adesso()
            S["fonte"] = f"chiusura {data_ultima} · {fonte_dati}"
        dettaglio = ""
        if S["righe"] is not None and len(S["righe"]):
            r0 = S["righe"].iloc[0]
            dettaglio = f"Titolo con punteggio più alto: {r0['nome']} ({r0['punteggio']:.0f}/100)"
        _notifica_cambi(verdetto, dettaglio)

        percorso = scrivi_snapshot()
        if percorso:
            print(f"vista statica aggiornata: {percorso}")
    except Exception as e:
        with LOCK:
            S["errore"] = f"{type(e).__name__}: {e}"
            S["messaggio"] = "errore durante l'aggiornamento"
        traceback.print_exc()
    finally:
        with LOCK:
            S["in_corso"] = False


def _candidati(tab: pd.DataFrame) -> list[dict]:
    liq = tab[tab["turnover_mediano"] >= LIQ]
    a = liq[~liq["sopra_mm200"]].sort_values("mom_%", ascending=False).head(5)
    a = a[a["mom_%"] > 0]
    out = []
    for t, r in a.iterrows():
        liv = float(r["livello_mm200"])
        out.append({"ticker": t.replace(".MI", ""), "nome": r["nome"],
                    "prezzo": round(float(r["prezzo"]), 3), "attiva_sopra": round(liv, 3),
                    "manca_%": round((liv / float(r["prezzo"]) - 1) * 100, 1)})
    return out


def _classifica(tab: pd.DataFrame) -> pd.DataFrame:
    """
    Tutti i titoli liquidi.

    Il punteggio esiste solo per i titoli **nel paniere** (sopra la MM200): il modello è
    stato stimato su quelli, e applicarlo a un titolo sotto la media sarebbe
    un'estrapolazione (darebbe punteggi alti e finti). Gli altri restano in elenco,
    ordinati per momentum, senza punteggio.
    """
    liquidi = tab[tab["turnover_mediano"] >= LIQ]
    if liquidi.empty:
        return pd.DataFrame()

    paniere = liquidi[liquidi["sopra_mm200"]]
    dentro = _score_righe(paniere, universo=tab, con_grafico=False) if len(paniere) else pd.DataFrame()

    fuori = liquidi[~liquidi["sopra_mm200"]].sort_values("mom_%", ascending=False)
    if len(fuori):
        fuori = pd.DataFrame({
            "nome": fuori["nome"],
            "prezzo": fuori["prezzo"].round(3),
            "punteggio": np.nan,
            "gruppo": "fuori paniere (sotto MM200)",
            "casi_simili": 0,
            "affidabilita": "n/d",
            "mediana_12m_%": np.nan,
            "livello_uscita": (fuori["prezzo"] / (1 + fuori["dist_mm200_%"] / 100)).round(3),
            "dist_%": fuori["dist_mm200_%"].round(2),
            "delta_oggi_%": fuori.get("delta_oggi_%", np.nan),
            "mom_%": fuori["mom_%"],
            "sopra_mm200": False,
            "nel_paniere": False,
            "turnover_M€": (fuori["turnover_mediano"] / 1e6).round(1),
        })
    return pd.concat([dentro, fuori]) if len(fuori) else dentro


def _riga_qualsiasi(ticker: str):
    """Cerca un titolo fra portafoglio e classifica completa."""
    for fonte in (S.get("righe"), S.get("classifica")):
        if isinstance(fonte, pd.DataFrame) and ticker in fonte.index:
            return fonte.loc[ticker]
    return None


def _grafico_da_classifica(ticker: str) -> str:
    if not ticker:
        return ""
    riga = _riga_qualsiasi(ticker)
    if riga is None:
        return ""
    delta = riga.get("delta_oggi_%", np.nan)
    return _grafico(ticker, riga["nome"], float(riga["punteggio"]),
                    float(riga["prezzo"]) * (1 + float(riga["mediana_12m_%"]) / 100),
                    float(delta) if np.isfinite(delta) else None)


def _equity_html() -> str:
    """Scheda con la curva della strategia (base 100) e le statistiche chiave."""
    perc_eq = os.path.join(OUT_DIR, "momentum_risk_equity.csv")
    perc_var = os.path.join(OUT_DIR, "momentum_risk_varianti.csv")
    if not os.path.exists(perc_eq):
        return ""
    try:
        d = pd.read_csv(perc_eq, sep=";", decimal=",", index_col=0)
        d.index = pd.to_datetime(d.index)
        serie = {
            "② buffer 5 (consigliata)": ("② + buffer di rank 5", "#0a7d3c"),
            "① base mensile": ("① Base MOM 12-1 top10 + MM200 (mensile)", "#b45309"),
            "Universo equipesato": ("◇ Universo equipesato (buy & hold)", "#1d4ed8"),
            "Casuali": ("⓪ Controllo: casuali equip. (media 20 seed)", "#94a3b8"),
        }
        svg = gr.grafico_equity(d, serie, "La strategia nel tempo — base 100 (2010-2026, costi inclusi)")
    except Exception:
        return ""

    def n(x, dec=1):
        return f"{x:,.{dec}f}".replace(",", "@").replace(".", ",").replace("@", ".")

    chips = []
    if os.path.exists(perc_var):
        try:
            v = pd.read_csv(perc_var, sep=";", decimal=",")
            v = v.set_index("variante")
            for chiave, etichetta, colore in (
                    ("② + buffer di rank 5", "② buffer 5", "#0a7d3c"),
                    ("◇ Universo equipesato (buy & hold)", "universo", "#1d4ed8"),
                    ("⓪ Controllo: casuali equip. (media 20 seed)", "casuali", "#64748b"),
                    ("◇ FTSE MIB (buy & hold)", "FTSE MIB", "#7c3aed")):
                if chiave not in v.index:
                    continue
                r = v.loc[chiave]
                chips.append(
                    f'<span style="display:inline-block;background:#f8fafc;border:1px solid #e2e8f0;'
                    f'border-radius:8px;padding:6px 10px;margin:3px 5px 3px 0;font-size:12.5px">'
                    f'<b style="color:{colore}">{etichetta}</b> · CAGR {n(r["CAGR_%"])}% · '
                    f'Sharpe {n(r["Sharpe"], 2)} · maxDD {n(r["max_drawdown_%"])}%</span>')
        except Exception:
            chips = []
    return f"""
  <div class="box" style="margin-top:14px">
    <div style="font-size:13px;letter-spacing:1px;color:#64748b;text-transform:uppercase;font-weight:700">
      La strategia nel tempo — perché fidarsi (e di cosa)</div>
    {svg}
    <div style="margin-top:10px">{''.join(chips)}</div>
    <div style="color:#64748b;font-size:12.5px;margin-top:6px">
      Curva dell'equity con i costi inclusi (0,2% per lato). Il punto non è la salita, ma il confronto:
      la strategia consigliata (verde) batte universo e portafogli casuali; gli overlay di rischio
      (in <code>README §7.5</code>) stavano sotto il caso e non sono mostrati qui.
    </div>
  </div>"""


def leggi_portafoglio() -> list[str]:
    att = os.path.join(OUT_DIR, tu.percorso("portafoglio_attuale.csv"))
    if not os.path.exists(att):
        return []
    try:
        p = pd.read_csv(att, sep=None, engine="python")
        col = next(c for c in p.columns if "ticker" in c.lower())
        return [str(x).strip() for x in p[col].dropna().tolist()]
    except Exception:
        return []


def aggiorna_prezzi():
    """Aggiornamento rapido: solo i prezzi intraday dei titoli seguiti (~2 s)."""
    with LOCK:
        tab, tenuti = S["tab"], list(S["tenuti"])
    if tab is None:
        return
    seguiti = [t for t in tenuti if t in tab.index]
    cand = [c["ticker"] + ".MI" for c in (S["attesa"] or [])]
    tickers = sorted(set(seguiti + cand))
    if not tickers:
        return
    try:
        import yfinance as yf
        raw = yf.download(tickers, period="2d", interval="15m", auto_adjust=True,
                          group_by="ticker", threads=True, progress=False)
        prezzi = {}
        for t in tickers:
            try:
                c = raw[t]["Close"].dropna()
                if len(c):
                    prezzi[t] = float(c.iloc[-1])
            except Exception:
                continue
        if not prezzi:
            return
        tab2 = tab.copy()
        for t, p in prezzi.items():
            if t in tab2.index:
                # la variazione "oggi" si misura dalla chiusura di seduta, non dall'ultimo intraday
                riferimento = float(S["chiusure_ufficiali"].get(t, tab2.loc[t, "prezzo"]))
                mm200 = float(tab2.loc[t, "livello_mm200"])
                tab2.loc[t, "prezzo"] = p
                tab2.loc[t, "dist_mm200_%"] = (p / mm200 - 1) * 100
                tab2.loc[t, "margin_%"] = tab2.loc[t, "dist_mm200_%"]
                tab2.loc[t, "sopra_mm200"] = bool(p > mm200)
                tab2.loc[t, "delta_oggi_%"] = (p / riferimento - 1) * 100 if riferimento else np.nan
        oggi_str = str(adesso().date())
        for t, p in prezzi.items():
            if t in S["storico"]:
                S["storico"][t] = _aggiungi_punto(S["storico"][t], p, oggi_str)
        with LOCK:
            S["tab"] = tab2
            # stesso universo del refresh completo: senza, il momentum relativo sarebbe gonfiato
            S["righe"] = _score_righe(tab2.loc[[t for t in tenuti if t in tab2.index]], tab2)
            S["classifica"] = _classifica(tab2)
            S["attesa"] = _candidati(tab2)
            S["prezzi_intraday"] = prezzi
            S["ultimo_prezzo"] = adesso().isoformat(timespec="seconds")
            S["ultimo_prezzo_dt"] = adesso()
            S["fonte"] = "prezzi intraday 15 min (Yahoo, ritardo tipico 15 min)"
    except Exception as e:
        with LOCK:
            S["errore"] = f"prezzi: {type(e).__name__}: {e}"


def pianificatore():
    """Aggiorna da solo: prezzi ogni minuto a mercato aperto, refresh completo ogni N minuti."""
    ultimo_digest = ""
    while True:
        time.sleep(20)
        try:
            if S["in_corso"]:
                continue
            ora = adesso()
            dh = (CFG.get("digest_ora") or "").strip()
            if dh and f"{ora:%H:%M}" == dh and ultimo_digest != f"{ora:%Y-%m-%d}":
                ultimo_digest = f"{ora:%Y-%m-%d}"
                with LOCK:
                    verdetto, tenuti, prossima = S["verdetto"], len(S["tenuti"]), S["prossima"]
                invia_notifica("Dashboard Piazza Affari - riepilogo del mattino" + chr(10)
                               + (verdetto or "in attesa del primo calcolo") + chr(10)
                               + f"portafoglio: {tenuti} titoli · prossima verifica {prossima}")
            if not mercato_aperto():
                continue
            ogni = int(CFG.get("ogni_minuti") or 0)
            ultimo = S.get("ultimo_full_dt")
            if ogni > 0 and ultimo and (ora - ultimo).total_seconds() > ogni * 60:
                aggiorna_tutto("aggiornamento automatico")
                continue
            ultimo_p = S.get("ultimo_prezzo_dt")
            if (not ultimo_p) or (ora - ultimo_p).total_seconds() >= 60:
                aggiorna_prezzi()
        except Exception:
            traceback.print_exc()


def mercato_aperto() -> bool:
    ora = adesso()
    if ora.weekday() >= 5:
        return False
    return dtime(9, 0) <= ora.time() <= dtime(17, 40)


# ---------------------------------------------------------------------------
# API JSON
# ---------------------------------------------------------------------------

def stato_json() -> dict:
    with LOCK:
        righe = ([] if S["righe"] is None
                 else S["righe"].reset_index().to_dict("records"))
        for r in righe:
            r.pop("gruppo", None)
        classifica = ([] if not isinstance(S.get("classifica"), pd.DataFrame) or S["classifica"].empty
                      else S["classifica"].reset_index().to_dict("records"))
        def _pulisci(record: dict) -> dict:
            for k, v in list(record.items()):
                if isinstance(v, float) and not np.isfinite(v):
                    record[k] = None
            return record

        for r in classifica:
            r.pop("gruppo", None)
            r.pop("grafico", None)
            for chiave in ("punteggio", "prezzo", "livello_uscita", "dist_%", "mom_%", "delta_oggi_%"):
                v = r.get(chiave)
                if v is not None and isinstance(v, float) and np.isfinite(v):
                    r[chiave] = round(v, 3 if chiave in ("prezzo", "livello_uscita") else 1)
            _pulisci(r)
        for r in righe:
            _pulisci(r)
        return {
            "aggiornato": S["ultimo_full"], "prezzi_aggiornati": S["ultimo_prezzo"],
            "fonte": S["fonte"], "in_corso": S["in_corso"], "messaggio": S["messaggio"],
            "errore": S["errore"], "verdetto": S["verdetto"],
            "prossima": S["prossima"], "giorni_borsa": S["giorni_borsa"],
            "mercato_aperto": mercato_aperto(), "righe": righe,
            "delta_etichetta": "oggi" if S["ultimo_prezzo"] else "ultima seduta",
            "attesa": S["attesa"] or [], "contesto": S["contesto"],
            "casi_storici": int(len(S["oss"])) if S["oss"] is not None else 0,
            "equity": _equity_html(),
            "classifica": classifica,
            "ogni_minuti": int(CFG.get("ogni_minuti") or 0),
            "notifiche_attive": bool((CFG.get("telegram") or {}).get("token")
                                     or (CFG.get("smtp") or {}).get("host")),
            "password_attiva": bool((CFG.get("auth") or {}).get("password")),
        }


def scrivi_snapshot():
    """Scrive output/dashboard_statico.html: la stessa pagina, senza server."""
    with LOCK:
        if S["righe"] is None:
            return None
        righe = S["righe"].reset_index()
        verdetto, prossima, sedute = S["verdetto"], S["prossima"], S["giorni_borsa"]
        fonte, quando, prezzi_q = S["fonte"], S["ultimo_full"] or "—", S["ultimo_prezzo"]
        attesa, contesto = list(S["attesa"] or []), dict(S["contesto"] or {})
        casi = len(S["oss"]) if S["oss"] is not None else 0
        cl = S.get("classifica")
        classifica = ([] if not isinstance(cl, pd.DataFrame) or cl.empty
                      else cl.head(20).reset_index().to_dict("records"))

    def col(p):
        return "#0a7d3c" if p >= 72 else ("#b45309" if p >= 62 else "#b91c1c")

    def eti(p):
        return "ALTA" if p >= 72 else ("MEDIA" if p >= 62 else "BASSA")

    def n(x, d=2):
        out = f"{x:,.{d}f}".replace(",", "@").replace(".", ",").replace("@", ".")
        return out.replace("-", "\u2212")

    schede = []
    for _, r in righe.iterrows():
        d = r["delta_oggi_%"]
        etichetta_delta = "oggi" if prezzi_q else "ultima seduta"
        delta_txt = ("—" if not np.isfinite(d)
                     else f"{'+' if d >= 0 else ''}{n(d, 2)}% {etichetta_delta}")
        delta_col = "#0a7d3c" if (np.isfinite(d) and d >= 0) else "#b91c1c"
        atteso = r["prezzo"] * (1 + r["mediana_12m_%"] / 100)
        schede.append(f"""
  <div class="scheda"><div class="griglia">
    <div style="flex:0 0 auto;min-width:186px">
      <div style="font-weight:800;font-size:17px">{r['nome']}</div>
      <div style="color:#64748b;font-size:12px">{r['ticker'].replace('.MI','')} · esce sotto
        <b>{n(r['livello_uscita'])} €</b></div>
      <div style="margin-top:8px">
        <span style="font-size:27px;font-weight:900;color:{col(r['punteggio'])}">{n(r['punteggio'], 0)}</span>
        <span style="color:{col(r['punteggio'])};font-weight:800;font-size:11px">&nbsp;{eti(r['punteggio'])}</span>
        <div style="background:#e2e8f0;border-radius:999px;height:6px;margin-top:5px;width:150px;overflow:hidden">
          <div style="width:{max(0, min(100, r['punteggio']))}%;height:6px;background:{col(r['punteggio'])}"></div></div>
        <div style="color:#64748b;font-size:11.5px;margin-top:5px">affidabilità {r['affidabilita'].upper()} ·
          {int(r['casi_simili'])} casi simili</div>
      </div>
    </div>
    <div style="flex:1 1 300px;min-width:250px">{r['grafico'] or ''}</div>
    <div style="flex:0 0 auto;min-width:158px;text-align:right">
      <div style="font-weight:800;font-size:17px">{n(r['prezzo'])} €</div>
      <div style="font-size:12.5px;font-weight:700;color:{delta_col}">{delta_txt}</div>
      <div style="color:#64748b;font-size:12px;margin-top:6px">atteso 12 mesi</div>
      <div style="font-weight:700">{n(atteso)} €</div>
      <div style="color:#64748b;font-size:12px">{n(r['mediana_12m_%'], 1)}% mediano</div>
    </div>
  </div></div>""")

    chips = " ".join(
        f'<span style="display:inline-block;background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;'
        f'padding:5px 9px;margin:3px 4px 3px 0">{a["nome"]} <b>sopra {n(a["attiva_sopra"])} €</b> '
        f'<span style="color:#b45309">(+{n(a["manca_%"], 1)}%)</span></span>' for a in attesa) or "nessun candidato"

    mib = "sopra" if contesto.get("mib_sopra_mm200") else "sotto"
    # --- etichette e schede del mercato corrente ---
    _m = tu.info()
    titolo_mercato = f"{_m['nome']} ({_m['paese']})"
    _index = "l'indice FTSE MIB" if tu.mercato == "IT" else f"l'indice {_m['benchmark_nome']}"
    sottotitolo = f"{_m['nome']} · {_m['paese']} · {_index} · vista statica (aggiornata {quando.replace('T', ' ')})"
    tabs_html, nota_html = _tabs_html(), _nota_affidabilita_html()
    html = f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Punteggi live (vista statica) — {titolo_mercato}</title>
<style>
  body {{ margin:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a }}
  .contenitore {{ max-width:860px;margin:0 auto;padding:16px 12px 36px }}
  svg {{ max-width:100%;height:auto;display:block }}
  .griglia {{ display:flex;flex-wrap:wrap;gap:14px;align-items:center }}
  .scheda {{ background:#fff;border-radius:12px;margin-bottom:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(15,23,42,.08) }}
  .box {{ background:#fff;border-radius:12px;padding:16px 18px;box-shadow:0 1px 3px rgba(15,23,42,.08) }}
</style></head>
<body><div class="contenitore">
  {tabs_html}
  <div style="background:#0f172a;color:#fff;border-radius:14px;padding:20px">
    <div style="font-size:12px;letter-spacing:1.2px;text-transform:uppercase;color:#94a3b8">
      {sottotitolo}</div>
    <div style="font-size:25px;font-weight:900;margin:8px 0 4px">{verdetto}</div>
    <div style="color:#cbd5e1;font-size:13.5px">prossima verifica {prossima} · fra {sedute} sedute · {fonte}</div>
  </div>
  {nota_html}
  <div class="box" style="margin-top:12px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
    <button id="btn" onclick="aggiorna()"
      style="background:#0a7d3c;color:#fff;border:0;border-radius:10px;padding:12px 18px;
             font-size:15px;font-weight:800;cursor:pointer;letter-spacing:.3px">⟳ AGGIORNA ORA</button>
    <span id="statoServer" style="font-size:12.5px;color:#64748b">verifico il collegamento col server…</span>
  </div>
  <div id="msg" style="font-size:12.5px;color:#7c2d12;margin:8px 2px 0"></div>
  {''.join(schede)}
  <div class="box" style="margin-top:6px">
    <div style="font-size:13px;letter-spacing:1px;color:#64748b;text-transform:uppercase;font-weight:700">In attesa di attivazione</div>
    <div style="font-size:14px;color:#334155;margin-top:8px">{chips}</div>
  </div>
  <div class="box" style="margin-top:14px">
    <div style="font-size:13px;letter-spacing:1px;color:#64748b;text-transform:uppercase;font-weight:700">
      Classifica completa — primi {len(classifica)} per punteggio</div>
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:8px">
      <thead><tr style="color:#64748b;font-size:11px;text-transform:uppercase">
        <th style="text-align:left;padding:6px 8px">Titolo</th>
        <th style="text-align:right;padding:6px 8px">Prezzo</th>
        <th style="text-align:right;padding:6px 8px">Mom 12-1</th>
        <th style="text-align:center;padding:6px 8px">Punteggio</th>
        <th style="text-align:center;padding:6px 8px">Affidabilità</th></tr></thead>
      <tbody>{''.join(f"""<tr>
        <td style="padding:6px 8px;border-bottom:1px solid #eef2f7">{r['nome']}
          <span style="color:#64748b;font-size:11.5px">{r['ticker'].replace('.MI','')}</span></td>
        <td style="padding:6px 8px;border-bottom:1px solid #eef2f7;text-align:right">{n(r['prezzo'])} €</td>
        <td style="padding:6px 8px;border-bottom:1px solid #eef2f7;text-align:right">{n(r['mom_%'], 0)}%</td>
        <td style="padding:6px 8px;border-bottom:1px solid #eef2f7;text-align:center">
          {"<b style='color:" + col(r['punteggio']) + "'>" + n(r['punteggio'], 0) + "</b>"
            if r['punteggio'] == r['punteggio'] else "<span style='color:#94a3b8'>— n/d</span>"}</td>
        <td style="padding:6px 8px;border-bottom:1px solid #eef2f7;text-align:center">{r['affidabilita']}</td>
      </tr>""" for r in classifica) if classifica else '<tr><td colspan="5">classifica non disponibile</td></tr>'}</tbody>
    </table>
    <div style="color:#64748b;font-size:12px;margin-top:8px">
      Nella dashboard servita dal server questa tabella è completa e ogni riga ha il grafico su richiesta.</div>
  </div>

  <div class="box" style="margin-top:14px;font-size:13px;color:#475569;line-height:1.7">
    <b>Contesto</b> (informativo): FTSE MIB {mib} la MM200 · breadth {contesto.get('breadth_%', '—')}% dei
    {contesto.get('titoli', '—')} titoli · rotture MM200 nelle ultime 5 sedute:
    {', '.join(contesto.get('rotture_5sedute') or []) or 'nessuna'}. Modello stimato su {casi} posizioni storiche
    (2010-2026), validato walk-forward.
  </div>
  {_equity_html()}
  <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;padding:14px 16px;margin-top:14px;
              font-size:12.5px;color:#7c2d12;line-height:1.7">
    Prezzi dal feed gratuito Yahoo Finance (ritardo tipico 15 minuti): non è un feed di trading. Il punteggio è
    una frequenza storica, non una previsione. Non è consulenza finanziaria.
  </div>
</div>
<script>
const BASI = ["", "http://localhost:8000", "http://127.0.0.1:8000"];
async function prova(metodo, base, percorso) {{
  const r = await fetch(base + percorso, {{method: metodo}});
  if (!r.ok) throw new Error(r.status);
  return r.json();
}}
async function serverAttivo() {{
  for (const b of BASI) {{ try {{ await prova("GET", b, "/api/stato"); return b; }} catch (e) {{}} }}
  return null;
}}
async function aggiorna() {{
  const b = document.getElementById("btn"), msg = document.getElementById("msg");
  b.disabled = true; b.textContent = "⟳ aggiornamento…"; b.style.background = "#475569";
  msg.textContent = "";
  for (const base of BASI) {{
    try {{
      await prova("POST", base, "/api/aggiorna");
      msg.style.color = "#0a7d3c";
      msg.textContent = "Aggiornamento avviato: la vista si ricarica fra ~20 secondi.";
      setTimeout(() => location.reload(), 21000);
      return;
    }} catch (e) {{}}
  }}
  msg.style.color = "#b45309";
  msg.innerHTML = "Server non raggiungibile: questa è la copia statica. Avvia <code>python3 dashboard.py</code> "
    + "e apri <code>http://localhost:8000</code> per usare il tasto.";
  b.disabled = false; b.textContent = "⟳ AGGIORNA ORA"; b.style.background = "#0a7d3c";
}}
(async () => {{
  const base = await serverAttivo();
  const el = document.getElementById("statoServer");
  el.innerHTML = base !== null
    ? "<b style='color:#0a7d3c'>● server attivo</b> — il tasto aggiorna i dati in tempo reale"
    : "<b style='color:#b45309'>● server non in esecuzione</b> — avvia <code>python3 dashboard.py</code> per usare il tasto";
}})();
</script>
</body></html>"""
    if URL_WORKFLOW:
        # ---- pagina pubblicata su GitHub Pages ----
        # Qui non c'è un server locale: il tasto ⟳ non può funzionare, quindi lo togliamo
        # (e con lui l'avviso "server non raggiungibile", che sul sito sarebbe fuorviante).
        # Al suo posto il link al workflow di aggiornamento.
        html = re.sub(r'\s*<button id="btn".*?</button>', '', html, count=1, flags=re.S)
        àncora = '<span id="statoServer" style="font-size:12.5px;color:#64748b">verifico il collegamento col server…</span>'
        html = html.replace(
            àncora,
            f'<a href="{URL_WORKFLOW}" style="display:inline-block;background:#0f172a;color:#fff;'
            f'border-radius:10px;padding:11px 16px;font-size:14px;font-weight:700;text-decoration:none">'
            f'Aggiorna su GitHub →</a> '
            '<span style="font-size:12.5px;color:#64748b">la pagina si aggiorna da sola più volte al giorno '
            '(a mercato aperto) e prima di ogni apertura; tocca il tasto per aggiornarla subito · '
            'dal telefono serve l\'app GitHub</span>')
        # via il controllo del server locale: sul sito non ha senso
        html = re.sub(r'<script>\s*const BASI.*?</script>',
                      '<script>/* pagina pubblicata su GitHub: si aggiorna automaticamente */</script>',
                      html, count=1, flags=re.S)

    cod = tu.mercato
    nome_statico = "dashboard_statico.html" if cod == "IT" else f"dashboard_statico_{cod.lower()}.html"
    percorso = os.path.join(OUT_DIR, nome_statico)
    with open(percorso, "w", encoding="utf-8") as f:
        f.write(html)

    # copia pronta per GitHub Pages (index.html / de.html / fr.html)
    try:
        with open(os.path.join(OUT_DIR, PAGINE_MERCATO[cod]), "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as e:
        print(f"[pages] {e}")
    return percorso


PAGINA = """<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Punteggi live — Piazza Affari</title>
<style>
  svg { max-width: 100%; height: auto; display: block; }
  .griglia { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; }
  .scheda { background:#fff; border-radius:12px; margin-bottom:10px; padding:14px 16px;
            box-shadow:0 1px 3px rgba(15,23,42,.08); }
</style></head>
<body style="margin:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a">
<div style="max-width:820px;margin:0 auto;padding:16px 12px 36px">

  <div style="background:#0f172a;color:#fff;border-radius:14px;padding:20px">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap">
      <div>
        <div style="font-size:12px;letter-spacing:1.2px;text-transform:uppercase;color:#94a3b8">
          Piazza Affari · <span id="stato-mercato">—</span></div>
        <div style="font-size:25px;font-weight:900;margin:8px 0 4px" id="verdetto">caricamento…</div>
        <div style="color:#cbd5e1;font-size:13.5px" id="sottotitolo">punteggio = probabilità storica di esito positivo a 12 mesi</div>
        <div style="color:#94a3b8;font-size:12px;margin-top:5px" id="config-live">—</div>
      </div>
      <div style="text-align:right">
        <button id="btn" onclick="aggiornaTutto()"
          style="background:#0a7d3c;color:#fff;border:0;border-radius:10px;padding:13px 18px;
                 font-size:15px;font-weight:800;cursor:pointer;letter-spacing:.3px">⟳ AGGIORNA ORA</button>
        <div style="color:#94a3b8;font-size:11.5px;margin-top:7px" id="agg">—</div>
      </div>
    </div>
  </div>

  <div style="display:flex;gap:10px;align-items:center;margin:12px 2px;font-size:13px;color:#475569;flex-wrap:wrap">
    <label style="display:flex;align-items:center;gap:6px;cursor:pointer">
      <input type="checkbox" id="auto" checked> aggiorna anche dal browser (il server lo fa già da solo)</label>
    <button onclick="aggiornaPrezzi(true)" style="background:#e2e8f0;border:0;border-radius:8px;
      padding:6px 11px;font-size:12.5px;font-weight:700;color:#334155;cursor:pointer">prezzi adesso</button>
    <span id="msg"></span>
  </div>

  <div id="corpo"></div>

  <div class="box" style="margin-top:14px">
    <details>
      <summary style="cursor:pointer;font-weight:800;color:#334155;font-size:14px">
        Classifica completa — tutti i titoli liquidi (premi <b>grafico</b> su una riga)</summary>
      <div id="classifica" style="margin-top:10px;overflow-x:auto">caricamento…</div>
      <div style="color:#64748b;font-size:12px;margin-top:8px">
        Punteggio calcolato con lo stesso modello delle schede; i titoli evidenziati in verde sono in
        portafoglio. <b>"Fuori paniere"</b> = sotto la MM200: <b>senza punteggio</b> — il modello è stimato
        solo sui titoli sopra la media, applicarlo lì sarebbe un'estrapolazione senza valore.</div>
    </details>
  </div>

  <div class="box" style="margin-top:14px">
    <div style="font-size:13px;letter-spacing:1px;color:#64748b;text-transform:uppercase;font-weight:700">In attesa di attivazione</div>
    <div id="attesa" style="font-size:14px;color:#334155;margin-top:8px">—</div>
  </div>

  <div style="background:#fff;border-radius:12px;padding:16px 18px;margin-top:14px;box-shadow:0 1px 3px rgba(15,23,42,.08);font-size:13px;color:#475569;line-height:1.7" id="contesto"></div>

  <div id="equity"></div>

  <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;padding:14px 16px;margin-top:14px;font-size:12.5px;color:#7c2d12;line-height:1.7">
    Prezzi dal feed gratuito Yahoo Finance (ritardo tipico 15 minuti): non è un feed di trading.
    Il punteggio è una frequenza storica, non una previsione. Non è consulenza finanziaria.
  </div>
</div>

<script>
const fmt = (x, d=2) => x===null||x===undefined||isNaN(x) ? "—" :
  Number(x).toLocaleString("it-IT", {minimumFractionDigits:d, maximumFractionDigits:d});
const col = p => p>=72 ? "#0a7d3c" : (p>=62 ? "#b45309" : "#b91c1c");
const eti = p => p>=72 ? "ALTA" : (p>=62 ? "MEDIA" : "BASSA");

function render(s) {
  document.getElementById("verdetto").textContent = s.verdetto || "—";
  document.getElementById("stato-mercato").textContent = s.mercato_aperto ? "mercato aperto" : "mercato chiuso";
  const agg = document.getElementById("agg");
  agg.textContent = "aggiornato: " + (s.aggiornato ? s.aggiornato.replace("T", " ") : "—")
      + (s.prezzi_aggiornati ? " · prezzi: " + s.prezzi_aggiornati.split("T")[1] : "");
  document.getElementById("sottotitolo").textContent =
      "prossima verifica " + (s.prossima || "—") + " · fra " + (s.giorni_borsa ?? "—") +
      " sedute · " + (s.fonte || "");
  const c = document.getElementById("corpo"); c.innerHTML = "";
  (s.righe||[]).forEach(r => {
    const d = r["delta_oggi_%"];
    const atteso = r.prezzo * (1 + r["mediana_12m_%"] / 100);
    const div = document.createElement("div");
    div.className = "scheda";
    div.innerHTML = `
      <div class="griglia">
        <div style="flex:0 0 auto;min-width:172px">
          <div style="font-weight:800;font-size:17px">${r.nome}</div>
          <div style="color:#64748b;font-size:12px">${r.ticker.replace(".MI","")} · esce sotto
            <b>${fmt(r.livello_uscita)} €</b></div>
          <div style="margin-top:8px">
            <span style="font-size:27px;font-weight:900;color:${col(r.punteggio)}">${Math.round(r.punteggio)}</span>
            <span style="color:${col(r.punteggio)};font-weight:800;font-size:11px;letter-spacing:.5px">
              &nbsp;${eti(r.punteggio)}</span>
            <div style="background:#e2e8f0;border-radius:999px;height:6px;margin-top:5px;width:150px;overflow:hidden">
              <div style="width:${Math.max(0,Math.min(100,r.punteggio))}%;height:6px;background:${col(r.punteggio)}"></div></div>
            <div style="color:#64748b;font-size:11.5px;margin-top:5px">affidabilità ${r.affidabilita.toUpperCase()} · ${r.casi_simili} casi simili</div>
          ${r.nel_paniere === false ? '<div style="color:#b45309;font-size:11.5px;margin-top:3px">⚠ sotto la MM200: punteggio fuori dal campo del modello</div>' : ''}
          </div>
        </div>
        <div style="flex:1 1 300px;min-width:250px">${r.grafico || ""}</div>
        <div style="flex:0 0 auto;min-width:158px;text-align:right">
          <div style="font-weight:800;font-size:17px">${fmt(r.prezzo)} €</div>
          <div style="font-size:12.5px;font-weight:700;color:${d>=0?'#0a7d3c':'#b91c1c'}">
            ${d===null||isNaN(d)?'—':(d>=0?'+':'')+fmt(d,2)+'% '+s.delta_etichetta}</div>
          <div style="color:#64748b;font-size:12px;margin-top:6px">atteso 12 mesi</div>
          <div style="font-weight:700">${fmt(atteso)} €</div>
          <div style="color:#64748b;font-size:12px">${fmt(r["mediana_12m_%"],1)}% mediano</div>
        </div>
      </div>`;
    c.appendChild(div);
  });
  document.getElementById("attesa").innerHTML = (s.attesa||[]).length
    ? s.attesa.map(a => `<span style="display:inline-block;background:#fff7ed;border:1px solid #fed7aa;
        border-radius:8px;padding:5px 9px;margin:3px 4px 3px 0">${a.nome}
        <b>sopra ${fmt(a.attiva_sopra)} €</b> <span style="color:#b45309">(+${fmt(a.manca_% ,1)}%)</span></span>`).join("")
    : "nessun candidato";
  const ct = s.contesto || {};
  document.getElementById("contesto").innerHTML =
    `<b>Contesto</b> (informativo): FTSE MIB ${ct.mib_sopra_mm200 ? "sopra" : "sotto"} la MM200 ·
     breadth ${ct.breadth_% ?? "—"}% dei ${ct.titoli ?? "—"} titoli · rotture MM200 nelle ultime 5 sedute:
     ${(ct.rotture_5sedute||[]).join(", ") || "nessuna"}.
     Modello stimato su ${s.casi_storici} posizioni storiche (2010-2026), validato walk-forward.`;
  document.getElementById("msg").textContent = s.errore ? "⚠ " + s.errore : (s.messaggio || "");
  if (s.equity) document.getElementById("equity").innerHTML = s.equity;
  if ((s.righe || []).length === 0) {
    document.getElementById("corpo").innerHTML =
      '<div class="scheda" style="color:#475569">' +
      (s.in_corso ? '⏳ primo caricamento dei dati in corso… la pagina si aggiorna da sola fra pochi secondi'
                  : (s.errore ? '⚠ ' + s.errore : 'nessun dato: premi ⟳ AGGIORNA ORA')) + '</div>';
  }
  renderClassifica(s);
  const cfgEl = document.getElementById("config-live");
  if (cfgEl) {
    const pezzi = [];
    pezzi.push(s.ogni_minuti > 0 ? `aggiornamento automatico ogni ${s.ogni_minuti} min` : "aggiornamento manuale");
    pezzi.push(s.notifiche_attive ? "notifiche attive" : "notifiche non configurate");
    pezzi.push(`${(s.classifica||[]).length} titoli in classifica`);
    if (s.password_attiva) pezzi.push("protezione con password attiva");
    cfgEl.textContent = pezzi.join(" · ");
  }
}

function renderClassifica(s) {
  const c = document.getElementById("classifica");
  const righe = s.classifica || [];
  if (!righe.length) { c.innerHTML = "<i>classifica non ancora calcolata</i>"; return; }
  const inPtf = new Set((s.righe || []).map(x => x.ticker));
  let h = `<table style="width:100%;border-collapse:collapse;font-size:13px">
    <thead><tr style="color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:.4px">
      <th style="text-align:left;padding:6px 8px">Titolo</th>
      <th style="text-align:right;padding:6px 8px">Prezzo</th>
      <th style="text-align:right;padding:6px 8px">Mom 12-1</th>
      <th style="text-align:right;padding:6px 8px">Dist. MM200</th>
      <th style="text-align:center;padding:6px 8px">Punteggio</th>
      <th style="text-align:center;padding:6px 8px">Affidabilità</th>
      <th style="padding:6px 8px"></th></tr></thead><tbody>`;
  righe.forEach(r => {
    const tk = r.ticker;
    h += `<tr style="${inPtf.has(tk) ? "background:#f0fdf4" : ""}">
      <td style="padding:7px 8px;border-bottom:1px solid #eef2f7">
        <b>${r.nome}</b>
        <span style="color:#64748b;font-size:11.5px">${tk.replace(".MI","")}${inPtf.has(tk) ? " · in portafoglio" : ""}${r.nel_paniere ? "" : " · fuori paniere"}</span></td>
      <td style="padding:7px 8px;border-bottom:1px solid #eef2f7;text-align:right">${fmt(r.prezzo)} €</td>
      <td style="padding:7px 8px;border-bottom:1px solid #eef2f7;text-align:right">${fmt(r["mom_%"],0)}%</td>
      <td style="padding:7px 8px;border-bottom:1px solid #eef2f7;text-align:right">${fmt(r["dist_%"],1)}%</td>
      <td style="padding:7px 8px;border-bottom:1px solid #eef2f7;text-align:center">
        ${r.punteggio === null || r.punteggio === undefined
            ? '<span style="color:#94a3b8;font-size:12.5px">— n/d</span>'
            : `<b style="color:${col(r.punteggio)};font-size:15px">${Math.round(r.punteggio)}</b>`}</td>
      <td style="padding:7px 8px;border-bottom:1px solid #eef2f7;text-align:center">
        ${r.affidabilita}<div style="color:#64748b;font-size:11.5px">${r.casi_simili} casi</div></td>
      <td style="padding:7px 8px;border-bottom:1px solid #eef2f7">
        <button onclick="caricaGrafico('${tk}')" style="background:#e2e8f0;border:0;border-radius:8px;
          padding:5px 10px;font-size:12px;font-weight:700;color:#334155;cursor:pointer">grafico</button></td></tr>
      <tr id="g-${tk}" style="display:none"><td colspan="7" style="padding:6px 8px;background:#f8fafc"></td></tr>`;
  });
  c.innerHTML = h + "</tbody></table>";
}

async function caricaGrafico(ticker) {
  const riga = document.getElementById("g-" + ticker);
  if (!riga) return;
  const cella = riga.firstElementChild;
  riga.style.display = "table-row";
  if (riga.dataset.pronto) return;
  cella.innerHTML = "carico il grafico…";
  try {
    const r = await fetch("api/grafico?ticker=" + encodeURIComponent(ticker));
    const j = await r.json();
    cella.innerHTML = j.grafico || "grafico non disponibile";
    riga.dataset.pronto = "1";
  } catch (e) { cella.textContent = "errore nel caricamento del grafico"; }
}

async function carica() {
  try { const r = await fetch("api/stato"); render(ultimoStato = await r.json()); } catch(e) {}
}
async function aggiornaTutto() {
  const b = document.getElementById("btn");
  b.disabled = true; b.textContent = "⟳ aggiornamento…";
  b.style.background = "#475569";
  try {
    await fetch("api/aggiorna", {method: "POST"});
    await attendi();
  } finally {
    b.disabled = false; b.textContent = "⟳ AGGIORNA ORA"; b.style.background = "#0a7d3c";
  }
}
async function attendi() {
  for (let i = 0; i < 120; i++) {
    const r = await fetch("api/stato"); const s = ultimoStato = await r.json(); render(s);
    if (!s.in_corso) return;
    await new Promise(res => setTimeout(res, 1500));
  }
}
let ultimoStato = null;
async function aggiornaPrezzi(manuale) {
  if (!manuale) {
    if (!document.getElementById("auto").checked) return;
    if (ultimoStato && !ultimoStato.mercato_aperto) return;   // a mercato chiuso non si interroga il feed
  }
  try { const r = await fetch("api/prezzi"); render(ultimoStato = await r.json()); } catch(e) {}
}
document.getElementById("auto").addEventListener("change", () => {
  if (document.getElementById("auto").checked) aggiornaPrezzi();
});
carica();
setInterval(() => aggiornaPrezzi(false), 60000);
// finché il primo caricamento non finisce, ricontrolla ogni 2 s
const primoAvvio = setInterval(async () => {
  if (ultimoStato && (ultimoStato.righe || []).length) { clearInterval(primoAvvio); return; }
  try { const r = await fetch("api/stato"); render(ultimoStato = await r.json()); } catch (e) {}
}, 2000);
</script>
</body></html>"""


# ---------------------------------------------------------------------------
# server
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, formato, *args):
        """In console solo se DASHBOARD_LOG=1 (serve a diagnosticare l'anteprima)."""
        if os.environ.get("DASHBOARD_LOG"):
            ua = (self.headers.get("User-Agent") or "")[:40]
            print(f"[accesso] {self.command} {self.path} - {ua}", flush=True)

    # -------- autenticazione opzionale (config_live.json -> auth) --------
    def _autorizzato(self) -> bool:
        au = CFG.get("auth") or {}
        utente, password = au.get("utente"), au.get("password")
        if not utente or not password:
            return True
        intestazione = self.headers.get("Authorization", "")
        if not intestazione.startswith("Basic "):
            return False
        try:
            decodificato = base64.b64decode(intestazione[6:]).decode("utf-8")
        except Exception:
            return False
        return decodificato == f"{utente}:{password}"

    def _chiedi_password(self):
        corpo = "Autenticazione richiesta".encode("utf-8")
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Dashboard"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        try:
            self.wfile.write(corpo)
        except BrokenPipeError:
            pass

    def _invia(self, corpo: bytes, tipo="application/json; charset=utf-8", code=200):
        self.send_response(code)
        self.send_header("Content-Type", tipo)
        self.send_header("Access-Control-Allow-Origin", "*")      # il file statico può usare il server
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(corpo)
        except BrokenPipeError:
            pass

    def do_OPTIONS(self):
        self._invia(b"{}")

    def do_HEAD(self):
        """Alcuni strumenti di anteprima verificano la pagina con HEAD: rispondiamo 200."""
        corpo = (PAGINA if self.path.split("?")[0] in ("/", "/index.html") else "{}").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self):
        if not self._autorizzato():
            return self._chiedi_password()
        percorso = self.path.split("?")[0]
        if percorso in ("/", "/index.html"):
            self._invia(PAGINA.encode("utf-8"), "text/html; charset=utf-8")
        elif percorso in ("/statico", "/statico.html"):
            f = os.path.join(OUT_DIR, "dashboard_statico.html")
            if os.path.exists(f):
                with open(f, encoding="utf-8") as fh:
                    self._invia(fh.read().encode("utf-8"), "text/html; charset=utf-8")
            else:
                self._invia(b"<h1>Nessuno snapshot disponibile: premi prima AGGIORNA nella pagina principale.</h1>",
                            "text/html; charset=utf-8", 404)
        elif percorso == "/api/stato":
            self._invia(json.dumps(stato_json(), ensure_ascii=False).encode("utf-8"))
        elif percorso == "/api/grafico":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            richiesto = (query.get("ticker") or [""])[0]
            self._invia(json.dumps({"ticker": richiesto, "grafico": _grafico_da_classifica(richiesto)},
                                   ensure_ascii=False).encode("utf-8"))
        elif percorso == "/api/prezzi":
            if not S["in_corso"]:
                aggiorna_prezzi()
            self._invia(json.dumps(stato_json(), ensure_ascii=False).encode("utf-8"))
        else:
            self._invia(b'{"errore":"percorso non trovato"}', code=404)

    def do_POST(self):
        if not self._autorizzato():
            return self._chiedi_password()
        percorso = self.path.split("?")[0]
        if percorso == "/api/aggiorna":
            if not S["in_corso"]:
                threading.Thread(target=aggiorna_tutto, daemon=True).start()
            self._invia(json.dumps({"avviato": True}, ensure_ascii=False).encode("utf-8"))
        else:
            self._invia(b'{"errore":"percorso non trovato"}', code=404)


def avvio(porta: int, apri_browser: bool):
    # 1) il server apre subito la porta: l'anteprima si aggancia anche mentre i dati arrivano
    srv = ThreadingHTTPServer(("0.0.0.0", porta), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://localhost:{porta}"
    print(f"Server in ascolto su {url} — caricamento dati in corso…", flush=True)

    # 2) poi i dati: casi storici, modello, primo refresh completo (in background)
    def primo_caricamento():
        try:
            S["in_corso"] = True
            S["messaggio"] = "primo caricamento in corso"
            S["oss"] = _carica_storico()
            _aggiorna_modello()
            aggiorna_tutto(messaggio="primo caricamento")
        except Exception:
            traceback.print_exc()
        finally:
            with LOCK:
                S["in_corso"] = False
                S["messaggio"] = ""

    threading.Thread(target=primo_caricamento, daemon=True).start()
    threading.Thread(target=pianificatore, daemon=True).start()

    print(f"Dashboard live su {url}")
    print(f"  aggiornamento automatico: completo ogni {CFG.get('ogni_minuti')} minuti a mercato aperto, "
          f"prezzi ogni minuto")
    print(f"  notifiche: {'attive' if ((CFG.get('telegram') or {}).get('token') or (CFG.get('smtp') or {}).get('host')) else 'non configurate (config_live.json)'}"
          + (" · password attiva" if (CFG.get('auth') or {}).get('password') else ""))
    with LOCK:
        print(f"  titoli: {len(S['righe']) if S['righe'] is not None else 0} · "
              f"verdetto: {S['verdetto']} · prossima verifica: {S['prossima']}")
    if apri_browser:
        try:
            import webbrowser
            threading.Timer(1.5, lambda: webbrowser.open(url)).start()
        except Exception:
            pass
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nChiuso.")
    finally:
        srv.shutdown()
        srv.server_close()


def main_con_mercato(codice: str, args) -> int:
    """Esegue la dashboard per il mercato indicato, con gli argomenti già letti.

    Imposta il mercato (liste titoli, benchmark, percorsi di cache e output) e
    poi fa quello che serve: un giro e scrittura della pagina (--una-tantum)
    oppure il server vero e proprio."""
    tu.imposta_mercato(codice)
    print(f"[mercato] {tu.info()['paese']} ({tu.info()['nome']}) · {len(tu.solo_ticker())} titoli · "
          f"benchmark {tu.BENCHMARK_NOME}")
    return _esegui(args)


def _esegui(args) -> int:
    if args.ogni_minuti is not None:
        CFG["ogni_minuti"] = args.ogni_minuti
    if args.digest_ora is not None:
        CFG["digest_ora"] = args.digest_ora
    if args.utente or args.password:
        CFG["auth"] = {"utente": args.utente or "dashboard", "password": args.password or ""}
    if args.notifica_prova:
        invia_notifica("Prova di notifica dalla dashboard.")
        return 0

    if args.una_tantum:
        print("Modalità una-tantum (CI): calcolo e scrittura della pagina…")
        S["oss"] = _carica_storico()
        _aggiorna_modello()
        if S["oss"] is None:
            print("[avviso] casi storici assenti: i punteggi non saranno disponibili "
                  "(lancia prima bootstrap_dati.py --mercato " + tu.mercato + ")")
        aggiorna_tutto(messaggio="aggiornamento CI")
        with LOCK:
            if S["righe"] is None or len(S["righe"]) == 0:
                print("[errore] nessun dato calcolato")
                return 1
            print(f"Fatto: {len(S['righe'])} titoli · verdetto: {S['verdetto']} · "
                  f"prossima verifica: {S['prossima']} · errore: {S['errore'] or 'nessuno'}")
            print(f"pagina: output/{PAGINE_MERCATO[tu.mercato]}")
        return 0
    avvio(args.porta, not args.no_browser)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Dashboard live con punteggi aggiornabili")
    ap.add_argument("--porta", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--ogni-minuti", type=int, default=None,
                    help="refresh completo automatico a mercato aperto (0 = disattivato)")
    ap.add_argument("--digest-ora", default=None, help="ora del riepilogo giornaliero, es. 09:10")
    ap.add_argument("--utente", default=None, help="utente per proteggere la pagina con password")
    ap.add_argument("--password", default=None, help="password (solo se esponi la pagina in rete)")
    ap.add_argument("--notifica-prova", action="store_true", help="manda una notifica di prova ed esce")
    ap.add_argument("--una-tantum", action="store_true",
                    help="un solo aggiornamento completo, scrive la pagina ed esce (CI/cron)")
    ap.add_argument("--mercato", default="IT", help="IT, DE, FR oppure TUTTI (default IT)")
    args = ap.parse_args()

    if args.mercato.upper() in ("TUTTI", "ALL", "*"):
        # tutti i mercati in sequenza: un giro per ciascuno, poi esce
        for cod in tu.elenco_mercati():
            print(f"\n===== {cod} · {tu.MERCATI[cod]['paese']} =====")
            esito = main_con_mercato(cod, args)
            if esito:
                print(f"[{cod}] qualcosa non ha funzionato (codice {esito})")
        return 0
    return main_con_mercato(args.mercato, args)


@tu.osserva
def _percorsi_segui_mercato(cod=None):
    """A ogni cambio di mercato, la dashboard punta a cache e file di quel mercato."""
    global CACHE_LIVE, CACHE_STORICO, STATO_FILE
    CACHE_LIVE = os.path.join(BASE_DIR, "cache", tu.percorso("scanner_live.pkl"))
    CACHE_STORICO = os.path.join(BASE_DIR, "cache", tu.percorso("momentum_raw.pkl"))
    STATO_FILE = os.path.join(BASE_DIR, "output", tu.percorso("stato_live.json"))

if __name__ == "__main__":
    sys.exit(main())
