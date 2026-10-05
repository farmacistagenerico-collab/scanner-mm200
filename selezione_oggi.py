#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SELEZIONE DI OGGI — la regola finale validata, applicata ai dati reali
======================================================================

Questo è lo strumento OPERATIVO del progetto: applica ai dati di mercato più
recenti la configurazione uscita dalla ricerca (README §7.5), senza simulare
nulla:

    segnale    momentum 12-1 (P(t-1)/P(t-13) su chiuse mensili: salta l'ultimo
               mese, come nel backtest)
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

OUT_DIR = os.path.join(BASE_DIR, "output")
CACHE_DIR = os.path.join(BASE_DIR, "cache")
CACHE_LIVE = os.path.join(CACHE_DIR, "scanner_live.pkl")


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
    print(f"Scarico {len(tickers)} titoli + FTSE MIB (dati giornalieri, {periodo})...")
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

def metriche_titolo(df: pd.DataFrame, oggi: pd.Timestamp) -> dict | None:
    """Metriche live di un titolo: momentum 12-1, stato MM200, liquidità."""
    d = df.dropna(subset=["Close"]).copy()
    if len(d) < 300:
        return None
    d = d[d.index <= oggi]
    close = d["Close"]
    mm200 = ind.sma(close, 200)
    prezzo = float(close.iloc[-1])
    ultima = close.index[-1]
    m = close.resample("ME").last()
    # scarta il mese in corso (incompleto): la decisione usa mesi conclusi
    if len(m) and (m.index[-1].year, m.index[-1].month) == (ultima.year, ultima.month) \
            and ultima < m.index[-1]:
        m = m.iloc[:-1]
    if len(m) < 14:
        return None
    mom = float(m.iloc[-2] / m.iloc[-13] - 1)          # 12-1, come nel backtest
    rif = m.index[-2].date()                            # fine finestra di formazione
    rif0 = m.index[-13].date()                          # inizio finestra di formazione
    vol = close.pct_change().tail(126).std() * np.sqrt(252)
    turn = (d["Close"] * d["Volume"]).tail(63).median()
    return {
        "ticker": d.attrs.get("ticker", ""),
        "prezzo": prezzo,
        "mom_%": mom * 100,
        "rif_mom": rif,
        "rif_mom_inizio": rif0,
        "sopra_mm200": bool(prezzo > float(mm200.iloc[-1])),
        "dist_mm200_%": (prezzo / float(mm200.iloc[-1]) - 1) * 100 if np.isfinite(mm200.iloc[-1]) else np.nan,
        "turnover_mediano": float(turn) if np.isfinite(turn) else 0.0,
        "vol_annua_%": float(vol) * 100 if np.isfinite(vol) else np.nan,
        "ultima_rilevazione": ultima.date(),
    }


def costruisci_tabella(raw: dict, oggi: pd.Timestamp) -> pd.DataFrame:
    righe = []
    for t in tu.solo_ticker():
        try:
            df = raw[t].dropna(how="all")
        except Exception:
            continue
        df = df.copy()
        df.attrs["ticker"] = t
        r = metriche_titolo(df, oggi)
        if r:
            righe.append(r)
    tab = pd.DataFrame(righe).set_index("ticker")
    tab["nome"] = [tu.mappa_nomi().get(t, t) for t in tab.index]
    return tab


# ---------------------------------------------------------------------------
# selezione con buffer
# ---------------------------------------------------------------------------

def seleziona(tab: pd.DataFrame, precedente: list[str], n: int, buffer: int,
              liquidita: float) -> tuple[list[str], pd.DataFrame]:
    """Top N con buffer di rank, sopra MM200 e liquide; fallback sull'universo intero."""
    elig = tab[(tab["turnover_mediano"] >= liquidita) & tab["sopra_mm200"]]
    note_fallback = ""
    if len(elig) < n:
        elig = tab[tab["turnover_mediano"] >= liquidita]
        note_fallback = ("attenzione: meno di N titoli sopra la MM200 fra i liquidi → "
                         "filtro MM200 allentato")
    if len(elig) < n:
        elig = tab
        note_fallback = ("attenzione: meno di N titoli liquidi → filtri allentati")
    ranked = elig.sort_values("mom_%", ascending=False)
    ranked["rank"] = range(1, len(ranked) + 1)
    tetto = list(ranked.index[: n + buffer])
    tenuti = [t for t in precedente if t in tetto]
    nuovi = [t for t in ranked.index if t not in tenuti]
    scelti = (tenuti + nuovi)[:n]
    out = ranked.loc[scelti].copy()
    out["in_portafoglio_da_prima"] = [t in precedente for t in out.index]
    out.attrs["nota"] = note_fallback
    return scelti, out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Selezione operativa momentum 12-1 (Piazza Affari)")
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
    args = ap.parse_args()

    oggi = pd.Timestamp(datetime.now().date())
    raw = scarica(args.periodo, usa_cache=args.no_download)
    tab = costruisci_tabella(raw, oggi)
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

    # pesi e quote
    sel = sel.reset_index()
    sel["peso_%"] = 100 / len(sel)
    sel["eur"] = args.capitale / len(sel)
    sel["quote"] = np.floor(sel["eur"] / sel["prezzo"]).astype(int)
    sel["eur_effettivi"] = (sel["quote"] * sel["prezzo"]).round(2)

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
          f"(la formula 12-1 salta l'ultimo mese: più conservativo del backtest, zero look-ahead)")
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

    # operazioni rispetto al portafoglio precedente
    if precedente:
        vendite = [t for t in precedente if t not in scelti]
        acquisti = [t for t in scelti if t not in precedente]
        print("\nOPERAZIONI RISPETTO AL PORTAFOGLIO ATTUALE")
        print(f"  mantieni ({len([t for t in scelti if t in precedente])}): "
              + ", ".join([t.replace('.MI', '') for t in scelti if t in precedente] or ["—"]))
        print(f"  vendi    ({len(vendite)}): " + ", ".join([t.replace('.MI', '') for t in vendite] or ["—"]))
        print(f"  compra   ({len(acquisti)}): " + ", ".join([t.replace('.MI', '') for t in acquisti] or ["—"]))
        turnover = (len(acquisti) / len(scelti)) if scelti else 0.0
        costo = turnover * args.capitale * 0.002
        print(f"  turnover stimato {turnover*100:.0f}% · costo commissioni ≈ {costo:,.0f} € "
              f"(a 0,2%/lato; il backtest include già questi costi)")

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
    path_sel = os.path.join(OUT_DIR, f"selezione_{stamp}.csv")
    out = sel[["rank", "ticker", "nome", "prezzo", "mom_%", "rif_mom_inizio", "rif_mom", "sopra_mm200",
               "dist_mm200_%", "vol_annua_%", "turnover_mediano", "peso_%", "quote",
               "eur_effettivi", "in_portafoglio_da_prima"]].copy()
    out.to_csv(path_sel, sep=";", decimal=",", encoding="utf-8-sig", index=False)

    # file da ripassare il mese prossimo con --attuale
    att = out[["ticker", "nome", "rank", "peso_%", "quote", "prezzo"]].copy()
    att.insert(0, "data_selezione", stamp)
    att["prossima_verifica"] = "fine mese" if not args.trimestrale else "fine trimestre"
    path_att = os.path.join(OUT_DIR, "portafoglio_attuale.csv")
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
    md += ["", "_Regola validata: momentum 12-1, top 10, prezzo > MM200, buffer di rank 5, "
           "ribilanciamento mensile. Nessun overlay sull'equity (peggiora i risultati, "
           "vedi README §7.5)._", ""]
    if precedente:
        md += ["## Operazioni", ""]
        md.append("- Mantieni: " + ", ".join([t.replace('.MI', '') for t in scelti if t in precedente]))
        md.append("- Vendi: " + ", ".join([t.replace('.MI', '') for t in precedente if t not in scelti] or ["—"]))
        md.append("- Compra: " + ", ".join([t.replace('.MI', '') for t in scelti if t not in precedente] or ["—"]))
    path_md = os.path.join(OUT_DIR, "selezione_oggi.md")
    with open(path_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"\nSalvati: {path_sel}")
    print(f"         {path_att}  (ripassalo con --attuale il mese prossimo)")
    print(f"         {path_md}")
    if sel.attrs.get("nota"):
        print(f"\n[!] {sel.attrs['nota']}")
    print("\nPromemoria: la regola è mensile, si applica dopo la chiusura dell'ultimo giorno del mese.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
