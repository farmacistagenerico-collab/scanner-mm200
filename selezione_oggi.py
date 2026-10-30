#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SELEZIONE DI OGGI — regola mensile condivisa con il backtest
======================================================================

Questo è lo strumento OPERATIVO del progetto: applica ai dati di mercato più
recenti la stessa regola del backtest, senza simulare nulla:

    segnale    momentum 12-1 (P(t-1)/P(t-13) su chiuse mensili concluse:
               salta il mese del segnale, come nel backtest)
    filtro     prezzo sopra la MM200 giornaliera
    liquidità  turnover mediano giornaliero >= soglia (default 2 M€/giorno)
    selezione  top N (default 10) equipesati, con BUFFER di rank (default 5):
               chi è già in portafoglio resta finché il suo rank non scende
               oltre N+buffer; solo allora viene sostituito
    frequenza  ribilanciamento mensile (o trimestrale, vedi --trimestrale)

Uso tipico (una volta al mese, dopo la chiusura dell'ultimo giorno del mese):

    python3 selezione_oggi.py                      # nuova selezione, dati freschi
    python3 selezione_oggi.py --attuale output/portafoglio_attuale.csv
    python3 selezione_oggi.py --capitale 25000 --n 10 --buffer 5
    python3 selezione_oggi.py --solo-lista         # solo i nomi, formato rapido
    python3 selezione_oggi.py --no-download        # usa la cache locale

Output:
    - tabella a video: portafoglio target (pesi, quote indicative, prezzo)
    - output/selezione_YYYY-MM-DD.csv        (portafoglio target completo)
    - output/portafoglio_attuale.csv         (da passare il mese prossimo con --attuale)
    - output/selezione_oggi.md               (scheda operativa compatta)

ATTENZIONE: strumento di analisi, non consulenza finanziaria. Applicare la
regola costa commissioni e, se il conto è in regime dichiarativo, imposte sul
capital gain: leggi la GUIDA.md prima di operare.
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import titoli_italiani as tu   # noqa: E402
import indicatori as ind       # noqa: E402
import momentum_core as mc     # noqa: E402

OUT_DIR = os.path.join(BASE_DIR, "output")
CACHE_DIR = os.path.join(BASE_DIR, "cache")
CACHE_LIVE = os.path.join(CACHE_DIR, "scanner_live.pkl")


@tu.osserva
def _percorsi_segui_mercato(cod=None):
    """Cache e file di lavoro distinti per mercato (IT mantiene i nomi storici)."""
    global CACHE_LIVE
    CACHE_LIVE = os.path.join(CACHE_DIR, tu.percorso("scanner_live.pkl"))


# ---------------------------------------------------------------------------
# dati
# ---------------------------------------------------------------------------

def scarica(periodo: str = "3y", usa_cache=False) -> dict:
    """Scarica (o riusa) i dati giornalieri dell'universo + benchmark."""
    import yfinance as yf

    os.makedirs(CACHE_DIR, exist_ok=True)
    if usa_cache and os.path.exists(CACHE_LIVE):
        try:
            return pd.read_pickle(CACHE_LIVE)
        except Exception:
            pass

    tickers = tu.solo_ticker()
    print(f"Scarico {len(tickers)} titoli + {tu.BENCHMARK_NOME} (dati giornalieri, {periodo})...")
    raw = yf.download(tickers + [tu.BENCHMARK], period=periodo, interval="1d",
                      auto_adjust=True, group_by="ticker", threads=True, progress=False)
    if raw is None or len(raw) == 0:
        if os.path.exists(CACHE_LIVE):
            print("Download non riuscito: uso la cache locale.")
            return pd.read_pickle(CACHE_LIVE)
        raise SystemExit("Download non riuscito e nessuna cache disponibile.")
    try:
        pd.to_pickle(raw, CACHE_LIVE)
    except Exception:
        pass
    return raw


# ---------------------------------------------------------------------------
# metriche punto-in-tempo
# ---------------------------------------------------------------------------

def metriche_titolo(df: pd.DataFrame, oggi: pd.Timestamp, mercato: str | None = None) -> dict | None:
    """Metriche del segnale mensile, allineate al backtest.

    `oggi` è la massima sessione utilizzabile (dopo la chiusura). Il mese in
    corso non entra nel segnale finché la sua ultima sessione di borsa non è
    conclusa. Prezzo live e prezzo del segnale sono tenuti distinti.
    """
    mercato = (mercato or tu.mercato).upper()
    d = df.dropna(subset=["Close"]).sort_index().copy()
    d = d[~d.index.duplicated(keep="last")]
    if d.index.tz is not None:
        d.index = d.index.tz_localize(None)
    limite = pd.Timestamp(oggi).normalize()
    d = d[d.index.normalize() <= limite]
    if len(d) < 300:
        return None
    close = d["Close"]
    m = mc.mesi_conclusi(close, limite, mercato)
    finestra = mc.finestra_momentum(m)
    if finestra is None:
        return None
    mom, rif0, rif = finestra
    data_segnale = close[close.index <= m.index[-1]].index[-1]
    d_seg = d[d.index <= data_segnale]
    mm200_seg = float(ind.sma(d_seg["Close"], 200).iloc[-1])
    prezzo_segnale = float(d_seg["Close"].iloc[-1])
    turni_m = (d["Close"] * d["Volume"]).resample("ME").median().reindex(m.index)
    turn = mc.liquidita_storica(turni_m, len(m) - 1)
    prezzo = float(close.iloc[-1])
    mm200_live = float(ind.sma(close, 200).iloc[-1])
    vol = close.pct_change().tail(126).std() * np.sqrt(252)
    return {
        "ticker": d.attrs.get("ticker", ""),
        "prezzo": prezzo,
        "prezzo_segnale": prezzo_segnale,
        "data_segnale": data_segnale.date(),
        "mom_%": mom * 100,
        "rif_mom": rif.date(),
        "rif_mom_inizio": rif0.date(),
        # Il filtro usa la chiusura del mese del segnale, non una barra intraday.
        "sopra_mm200": bool(prezzo_segnale > mm200_seg) if np.isfinite(mm200_seg) else False,
        "dist_mm200_%": (prezzo / mm200_live - 1) * 100 if np.isfinite(mm200_live) else np.nan,
        "turnover_mediano": float(turn) if np.isfinite(turn) else 0.0,
        "vol_annua_%": float(vol) * 100 if np.isfinite(vol) else np.nan,
        "ultima_rilevazione": close.index[-1].date(),
    }


def costruisci_tabella(raw: dict, oggi: pd.Timestamp, mercato: str | None = None) -> pd.DataFrame:
    righe = []
    for t in tu.solo_ticker():
        try:
            df = raw[t].dropna(how="all")
        except Exception:
            continue
        df = df.copy()
        df.attrs["ticker"] = t
        r = metriche_titolo(df, oggi, mercato)
        if r:
            righe.append(r)
    if not righe:
        return pd.DataFrame()
    tab = pd.DataFrame(righe).set_index("ticker")
    tab["nome"] = [tu.mappa_nomi().get(t, t) for t in tab.index]
    return tab


# ---------------------------------------------------------------------------
# selezione con buffer
# ---------------------------------------------------------------------------

def seleziona(tab: pd.DataFrame, precedente: list[str], n: int, buffer: int,
              liquidita: float) -> tuple[list[str], pd.DataFrame]:
    """Top N con buffer di rank, sopra MM200 e liquide, senza allentare i filtri.

    Se gli slot non sono riempibili, la parte mancante resta liquidità. Il
    backtest usa la stessa regola: niente acquisti sotto MM200 o illiquidi per
    raggiungere artificiosamente N titoli.
    """
    if tab.empty:
        return [], pd.DataFrame()
    elig = tab[tab["turnover_mediano"] >= liquidita]
    scelti = mc.seleziona_buffer(elig, precedente, n, buffer, filtro_mm200=True)
    nota = ""
    if len(scelti) < n:
        nota = (f"attenzione: solo {len(scelti)}/{n} titoli liquidi e sopra la MM200; "
                f"i {n - len(scelti)} slot mancanti restano liquidità. Filtri non allentati.")
    ranked = elig[elig["sopra_mm200"]].sort_values("mom_%", ascending=False).copy()
    ranked["rank"] = range(1, len(ranked) + 1)
    out = ranked.loc[scelti].copy() if scelti else ranked.iloc[0:0].copy()
    out["in_portafoglio_da_prima"] = [t in precedente for t in out.index]
    out.attrs["nota"] = nota
    return scelti, out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Selezione operativa momentum 12-1")
    ap.add_argument("--n", type=int, default=10, help="numero di titoli (default 10)")
    ap.add_argument("--buffer", type=int, default=5, help="buffer di rank (default 5)")
    ap.add_argument("--liquidita", type=float, default=2_000_000,
                    help="turnover mediano minimo in EUR/giorno (default 2.000.000)")
    ap.add_argument("--capitale", type=float, default=100_000.0,
                    help="capitale da investire in EUR (default 100.000)")
    ap.add_argument("--attuale", default="", help="CSV/lista del portafoglio attuale (output di una run precedente)")
    ap.add_argument("--trimestrale", action="store_true",
                    help="segnala che stai ricontrollando in modalità trimestrale (avviso nei file)")
    ap.add_argument("--periodo", default="3y", help="storico da scaricare (default 3y)")
    ap.add_argument("--no-download", action="store_true", help="usa solo la cache locale")
    ap.add_argument("--solo-lista", action="store_true", help="stampa solo i nomi selezionati")
    ap.add_argument("--mercato", default="IT", help="IT, DE, FR (default IT)")
    args = ap.parse_args()
    tu.imposta_mercato(args.mercato)

    oggi = mc.ultima_sessione_utile(pd.Timestamp.now(tz="Europe/Rome"), args.mercato)
    raw = scarica(args.periodo, usa_cache=args.no_download)
    tab = costruisci_tabella(raw, oggi, args.mercato)
    if tab.empty:
        raise SystemExit("Nessun titolo con dati sufficienti: controlla la connessione o la cache.")

    # portafoglio attuale
    precedente: list[str] = []
    if args.attuale and os.path.exists(args.attuale):
        try:
            p = pd.read_csv(args.attuale, sep=None, engine="python")
            col = next(c for c in p.columns if "ticker" in c.lower())
            precedente = [str(x).strip() for x in p[col].dropna().tolist()]
        except Exception as e:
            print(f"[avviso] non riesco a leggere {args.attuale}: {e}")
    elif args.attuale:
        print(f"[avviso] file {args.attuale} non trovato: parto senza portafoglio precedente.")

    scelti, sel = seleziona(tab, precedente, args.n, args.buffer, args.liquidita)
    nota_selezione = sel.attrs.get("nota", "")

    # Pesi per slot: se mancano candidati, il resto resta liquidità.
    # Le quote sono indicative sul prezzo live, non sul prezzo di esecuzione futuro.
    sel = sel.reset_index()
    peso_slot = 100.0 / args.n if args.n > 0 else 0.0
    eur_slot = args.capitale / args.n if args.n > 0 else 0.0
    sel["peso_%"] = peso_slot
    sel["eur"] = eur_slot
    sel["quote"] = np.floor(sel["eur"] / sel["prezzo"]).astype(int) if len(sel) else pd.Series(dtype=int)
    sel["eur_effettivi"] = (sel["quote"] * sel["prezzo"]).round(2) if len(sel) else pd.Series(dtype=float)
    eur_investiti = float(sel["eur_effettivi"].sum()) if len(sel) else 0.0
    liquidita_residua = max(args.capitale - eur_investiti, 0.0)

    data_rif = str(tab["rif_mom"].iloc[0])
    data_rif0 = str(tab["rif_mom_inizio"].iloc[0])
    ultima_rilevazione = str(tab["ultima_rilevazione"].max())

    if args.solo_lista:
        print(" ".join(scelti))
        return 0

    pd.set_option("display.width", 200)
    print("\n" + "=" * 108)
    print(f"SELEZIONE MOMENTUM 12-1 + MM200  —  ultima chiusura {ultima_rilevazione}")
    print(f"finestra di formazione del segnale: {data_rif0} → {data_rif}  "
          f"(12-1 su mesi conclusi; stessa regola del backtest)")
    print(f"regola: top {args.n}, buffer {args.buffer}, liquidità ≥ {args.liquidita:,.0f} €/giorno"
          + ("  [modalità trimestrale]" if args.trimestrale else "  [mensile]"))
    print("=" * 108)

    liq = tab[tab["turnover_mediano"] >= args.liquidita]
    num_sopra = int(liq["sopra_mm200"].sum())
    print(f"Universo: {len(tab)} titoli con dati | liquidi: {len(liq)} | "
          f"liquidi e sopra MM200: {num_sopra}")

    cols = ["rank", "nome", "prezzo", "mom_%", "dist_mm200_%", "vol_annua_%",
            "turnover_mediano", "peso_%", "quote", "eur_effettivi", "in_portafoglio_da_prima"]
    vis = sel[cols].copy()
    vis["turnover_mediano"] = (vis["turnover_mediano"] / 1e6).round(2)
    for c in ("prezzo", "mom_%", "dist_mm200_%", "vol_annua_%", "peso_%", "eur_effettivi"):
        vis[c] = vis[c].round(2)
    vis = vis.rename(columns={"nome": "titolo", "mom_%": "mom 12-1 %",
                              "dist_mm200_%": "dist MM200 %", "vol_annua_%": "vol annua %",
                              "turnover_mediano": "turnover M€", "peso_%": "peso %",
                              "in_portafoglio_da_prima": "già in ptf"})
    print("\nPORTAFOGLIO TARGET  (capitale %.0f €)" % args.capitale)
    print(vis.to_string(index=False))
    print(f"\nSlot riempiti: {len(sel)}/{args.n} · liquidità residua indicativa: {liquidita_residua:,.0f} €")

    # operazioni rispetto al portafoglio precedente
    if precedente:
        vendite = [t for t in precedente if t not in scelti]
        acquisti = [t for t in scelti if t not in precedente]
        print("\nOPERAZIONI RISPETTO AL PORTAFOGLIO ATTUALE")
        print(f"  mantieni ({len([t for t in scelti if t in precedente])}): "
              + ", ".join([t.replace('.MI', '') for t in scelti if t in precedente] or ["—"]))
        print(f"  vendi    ({len(vendite)}): " + ", ".join([t.replace('.MI', '') for t in vendite] or ["—"]))
        print(f"  compra   ({len(acquisti)}): " + ", ".join([t.replace('.MI', '') for t in acquisti] or ["—"]))
        # Stima prudente: si assume che il portafoglio precedente fosse a slot
        # uguali. Il costo reale dipende dai pesi effettivi al momento dell'ordine.
        prima = {t: 1.0 / args.n for t in precedente if t in tab.index}
        dopo = {t: 1.0 / args.n for t in scelti}
        turno = mc.turnover_operativo(prima, dopo)
        costo = mc.costo_transizione(prima, dopo, mc.COSTO_LATO) * args.capitale
        print(f"  turnover operativo stimato {turno*100:.0f}% · costo ≈ {costo:,.0f} € "
              f"(a {mc.COSTO_LATO*100:.1f}%/lato sul nozionale comprato/venduto)")

    # classifica estesa, per contesto
    top = tab.sort_values("mom_%", ascending=False).head(15)
    print("\nPRIMI 15 PER MOMENTUM 12-1 (indipendentemente dai filtri)")
    contesto = pd.DataFrame({
        "titolo": [tu.mappa_nomi().get(t, t) for t in top.index],
        "mom 12-1 %": top["mom_%"].round(1),
        "sopra MM200": np.where(top["sopra_mm200"], "sì", "no"),
        "turnover M€": (top["turnover_mediano"] / 1e6).round(1),
    })
    print(contesto.to_string(index=False))

    # ------------------- salvataggi -------------------
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = ultima_rilevazione
    path_sel = os.path.join(OUT_DIR, tu.percorso(f"selezione_{stamp}.csv"))
    out = sel[["rank", "ticker", "nome", "prezzo", "prezzo_segnale", "data_segnale", "mom_%",
               "rif_mom_inizio", "rif_mom", "sopra_mm200", "dist_mm200_%", "vol_annua_%",
               "turnover_mediano", "peso_%", "quote", "eur_effettivi",
               "in_portafoglio_da_prima"]].copy()
    out.to_csv(path_sel, sep=";", decimal=",", encoding="utf-8-sig", index=False)

    # file da ripassare il mese prossimo con --attuale
    att = out[["ticker", "nome", "rank", "peso_%", "quote", "prezzo"]].copy()
    att.insert(0, "data_selezione", stamp)
    att["prossima_verifica"] = "fine mese" if not args.trimestrale else "fine trimestre"
    path_att = os.path.join(OUT_DIR, tu.percorso("portafoglio_attuale.csv"))
    att.to_csv(path_att, sep=";", decimal=",", encoding="utf-8-sig", index=False)

    # scheda markdown
    md = [f"# Selezione momentum — dati al {stamp}", "",
          f"Finestra di formazione: {data_rif0} → {data_rif} · capitale {args.capitale:,.0f} € · "
          f"top {args.n} · buffer {args.buffer} · liquidità ≥ {args.liquidita:,.0f} €/giorno", "",
          "| # | Titolo | Prezzo € | Mom 12-1 | Dist. MM200 | Turnover M€ | Peso | Quote |",
          "|---|---|---|---|---|---|---|---|"]
    for _, r in sel.iterrows():
        md.append(f"| {int(r['rank'])} | {r['nome']} ({r['ticker'].replace('.MI','')}) | "
                  f"{r['prezzo']:.2f} | {r['mom_%']:.1f}% | {r['dist_mm200_%']:+.1f}% | "
                  f"{r['turnover_mediano']/1e6:.1f} | {r['peso_%']:.0f}% | {int(r['quote'])} |")
    md += ["", f"_Slot riempiti: {len(sel)}/{args.n}; liquidità residua indicativa {liquidita_residua:,.0f} €. "
           "Regola condivisa con il backtest: momentum 12-1 su mesi conclusi, prezzo del segnale > MM200, "
           "liquidità storica, buffer di rank. Nessun allentamento dei filtri per riempire gli slot. "
           "Il backtest è esplorativo: survivorship bias non rimosso, nessun holdout intatto._", ""]
    if precedente:
        md += ["## Operazioni", ""]
        md.append("- Mantieni: " + ", ".join([t.replace('.MI', '') for t in scelti if t in precedente]))
        md.append("- Vendi: " + ", ".join([t.replace('.MI', '') for t in precedente if t not in scelti] or ["—"]))
        md.append("- Compra: " + ", ".join([t.replace('.MI', '') for t in scelti if t not in precedente] or ["—"]))
    path_md = os.path.join(OUT_DIR, tu.percorso("selezione_oggi.md"))
    with open(path_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"\nSalvati: {path_sel}")
    print(f"         {path_att}  (ripassalo con --attuale il mese prossimo)")
    print(f"         {path_md}")
    if nota_selezione:
        print(f"\n[!] {nota_selezione}")
    print("\nPromemoria: la regola è mensile, si applica dopo la chiusura dell'ultimo giorno del mese.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
