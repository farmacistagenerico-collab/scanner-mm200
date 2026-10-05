#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCANNER MM200 — Borsa Italiana (Piazza Affari)
==============================================

Scova i titoli italiani "pronti" a rompere (o appena rotti rispetto a) la
media mobile a 200 periodi, con filtri pensati per aumentare la probabilità
che il movimento sia statisticamente significativo e non un falso segnale.

Cosa fa, in sintesi:
  1. scarica in blocco i dati giornalieri di ~130 titoli di Piazza Affari
     (FTSE MIB, Mid Cap, STAR) via Yahoo Finance;
  2. calcola MM20/MM50/MM200, distanza % dalla MM200, distanza in ATR,
     volume relativo, RSI, volatilità, pendenza della MM200, n. di incroci
     storici e contesto settimanale (MM40 settimanale ≈ MM200 giornaliera);
  3. etichetta ogni titolo (rottura confermata, rottura da confermare, falso
     breakout, in prossimità, trend già in corso...) e assegna un punteggio
     0-100 di "prontezza alla rottura";
  4. esporta CSV + report HTML/Markdown.

Uso:
    python3 scanner.py                        # tutti gli indici, 3 anni di storia
    python3 scanner.py --indice MIB
    python3 scanner.py --soglia 60 --distanza 6 --volume 1.8
    python3 scanner.py --periodo-anni 5 --top 25
    python3 scanner.py --no-download          # riusa l'ultima cache in cache/

ATTENZIONE: strumento di analisi, non è consulenza finanziaria né un
consiglio di investimento. Vedi le note in fondo al README.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import titoli_italiani as tu          # noqa: E402
import indicatori as ind             # noqa: E402
from report_html import scrivi_report  # noqa: E402

CACHE_DIR = os.path.join(BASE_DIR, "cache")
OUT_DIR = os.path.join(BASE_DIR, "output")

# ----------------------------------------------------------------------------
# Configurazione dei filtri (tutti sovrascrivibili da riga di comando)
# ----------------------------------------------------------------------------
CFG_DEFAULT = {
    # --- medie ---
    "periodo_mm": 200,
    "periodo_mm_breve": 50,
    "min_barre": 260,                 # ~1 anno di borsa: minimo per una MM200 sensata

    # --- definizione di "rottura" e di "zona di indecisione" ---
    "buffer_stato_pct": 1.0,          # ±1% attorno alla MM200 = transizione (filtro anti-rumore)
    "distanza_prontezza_pct": 8.0,    # titolo "a ridosso" se entro -8%..+1% dalla MM200

    # --- filtri di significatività (dalle evidenze empiriche) ---
    "volume_conferma": 1.5,           # volume >= 1,5x media 50 sedute sulla barra di rottura
    "soglia_punteggio": 55,           # punteggio minimo per entrare in lista candidati
}


# ----------------------------------------------------------------------------
# Download dati
# ----------------------------------------------------------------------------

def scarica_dati(ticker_list, anni=3, usa_cache=False):
    """Scarica i dati giornalieri in blocco. Ritorna (dict di DataFrame, lista mancanti)."""
    import yfinance as yf

    os.makedirs(CACHE_DIR, exist_ok=True)
    tutte = ticker_list + [tu.BENCHMARK]
    df = yf.download(
        tutte,
        period=f"{anni}y",
        interval="1d",
        auto_adjust=True,
        group_by="ticker",
        threads=True,
        progress=False,
    )

    dati, mancanti = {}, []
    for t in ticker_list:
        try:
            sub = df[t].dropna(how="all").copy()
        except Exception:
            mancanti.append(t)
            continue
        sub = sub.dropna(subset=["Close"])
        if len(sub) < 260:
            mancanti.append(t)
            continue
        dati[t] = sub

    # cache locale (parquet se disponibile, altrimenti pickle)
    if dati:
        try:
            for t, d in dati.items():
                d.to_pickle(os.path.join(CACHE_DIR, t.replace(".", "_") + ".pkl"))
        except Exception:
            pass

    return dati, mancanti


def carica_da_cache():
    """Rilegge i dati salvati in cache/ (utile offline o per test ripetuti)."""
    dati = {}
    if not os.path.isdir(CACHE_DIR):
        return dati
    for f in sorted(os.listdir(CACHE_DIR)):
        if f.endswith(".pkl"):
            t = f[:-4].replace("_MI", ".MI").replace("_", ".")
            try:
                dati[t] = pd.read_pickle(os.path.join(CACHE_DIR, f))
            except Exception:
                pass
    return dati


# ----------------------------------------------------------------------------
# Analisi
# ----------------------------------------------------------------------------

def analizza(dati, cfg):
    """Applica il pacchetto di metriche a ogni titolo. Ritorna un DataFrame."""
    nomi = tu.mappa_nomi()
    righe = []
    for t, df in dati.items():
        m = ind.calcola_metriche(df, cfg)
        if m is None:
            continue
        m["ticker"] = t
        m["nome"] = nomi.get(t, t)
        righe.append(m)
    if not righe:
        return pd.DataFrame()
    out = pd.DataFrame(righe).set_index("ticker")
    ordine = ["nome", "data", "close", "mm200", "mm50", "stato", "etichetta",
              "distanza_pct", "distanza_atr", "dd_252", "rs_rank_12m",
              "punteggio", "vol_ratio",
              "vol_ratio_5g", "rsi14", "atr_pct", "slope_mm200_20g",
              "ret_3m", "ret_6m", "ret_12m", "mm50_sopra_mm200",
              "sopra_weekly_mm40", "giorni_da_incrocio_su", "giorni_da_incrocio_giu",
              "n_incroci_3a", "candidato", "flag_significativita", "dettagli_punteggio"]
    ordine = [c for c in ordine if c in out.columns]
    return out[ordine + [c for c in out.columns if c not in ordine]]


def aggiungi_punteggio_validato(df):
    """
    Punteggio "validato OOS" (out-of-sample): usa SOLO le componenti risultate
    significative nella calibrazione 2005-2015 e confermate sul 2016-2026
    (out_of_sample.py, TEST B2). NON è il punteggio di attenzione: è la parte
    che ha superato la verifica fuori campione, con pesi fissi.

    Componenti (dal TEST B2, calibrazione sull'excess condizionato):
      +1  deep recovery (drawdown dal massimo a 12 mesi < -20%)
      +1  MM200 in salita (pendenza 20 sedute > 0)
      +1  MM50 sopra MM200
      +1  forza relativa ≥ 50° percentile dell'universo (rendimento 12 mesi)
      -1  rottura vicino ai massimi (drawdown > -15%)
      Componenti a peso zero (non significative): volume, RSI, struttura
      settimanale, volatilità, rendimento 12 mesi, assenza di incroci recenti.
    """
    if df is None or df.empty:
        return df

    def punti(r):
        p, comp = 0, []
        dd = r.get("dd_252", float("nan"))
        if pd.notna(dd):
            if dd < -20:
                p += 1; comp.append("recovery")
            elif dd > -15:
                p -= 1; comp.append("vicino ai max")
        sl = r.get("slope_mm200_20g", float("nan"))
        if pd.notna(sl) and sl > 0:
            p += 1; comp.append("MM200 su")
        if bool(r.get("mm50_sopra_mm200", False)):
            p += 1; comp.append("MM50>200")
        rs = r.get("rs_rank_12m", float("nan"))
        if pd.notna(rs) and rs >= 50:
            p += 1; comp.append("forza rel.")
        return p, " · ".join(comp)

    risultati = [punti(r) for _, r in df.iterrows()]
    df["score_validato"] = [x[0] for x in risultati]
    df["componenti_validati"] = [x[1] for x in risultati]
    return df


def contesto_mercato(dati, cfg):
    """Metriche di regime sull'indice FTSE MIB: sopra/sotto la sua MM200."""
    try:
        import yfinance as yf
        idx = yf.download(tu.BENCHMARK, period=f"{cfg.get('anni', 3)}y", interval="1d",
                          auto_adjust=True, progress=False)
        if isinstance(idx.columns, pd.MultiIndex):
            idx.columns = idx.columns.get_level_values(0)
        c = idx["Close"].dropna()
        m = ind.sma(c, 200)
        dist = float((c.iloc[-1] / m.iloc[-1] - 1) * 100)
        return {
            "indice": tu.BENCHMARK_NOME,
            "data": c.index[-1].strftime("%Y-%m-%d"),
            "close": float(c.iloc[-1]),
            "mm200": float(m.iloc[-1]) if not np.isnan(m.iloc[-1]) else None,
            "distanza_pct": dist,
            "regime": "rialzista (indice sopra MM200)" if dist > 0 else "ribassista (indice sotto MM200)",
            "slope_20g": float(ind.slope_pct(m, 20).iloc[-1]) if len(c) > 220 else None,
        }
    except Exception as e:
        return {"errore": str(e)}


# ----------------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------------

def esporta_csv(df, path):
    out = df.copy()
    for c in ("dettagli_punteggio", "flag_significativita"):
        if c in out.columns:
            out[c] = out[c].astype(str).str.replace(";", "|", regex=False)
    out.to_csv(path, sep=";", decimal=",", encoding="utf-8-sig")
    return path


def stampa_console(df, cfg, mancanti, mercato):
    sep = "=" * 108
    print(sep)
    print(f"  SCANNER MM200 — BORSA ITALIANA (Piazza Affari)   |   {datetime.now():%d/%m/%Y %H:%M}")
    print(sep)
    if mercato and "regime" in mercato:
        print(f"  Contesto: {mercato['indice']} {mercato['close']:.2f} — {mercato['regime']}"
              f" (distanza dalla MM200: {mercato['distanza_pct']:+.2f}%)")
    print(f"  Titoli analizzati: {len(df)}   |   dati non disponibili: {len(mancanti)}")
    print(sep)

    def blocco(titolo, sotto_df, max_righe=None):
        if sotto_df.empty:
            print(f"\n{titolo}: nessun titolo")
            return
        print(f"\n{titolo}  ({len(sotto_df)})")
        if max_righe:
            sotto_df = sotto_df.head(max_righe)
        print("-" * 108)
        print(f"{'Ticker':<10}{'Nome':<28}{'Stato':<15}{'Etichetta':<28}"
              f"{'Dist%':>7}{'Vol':>6}{'RSI':>6}{'Pt':>5}")
        print("-" * 108)
        for t, r in sotto_df.iterrows():
            print(f"{t:<10}{str(r['nome'])[:27]:<28}{r['stato']:<15}{str(r['etichetta'])[:27]:<28}"
                  f"{r['distanza_pct']:>7.2f}{r['vol_ratio']:>6.2f}{r['rsi14']:>6.1f}{r['punteggio']:>5.0f}")

    rotture = df[(df["etichetta"] == "ROTTURA CONFERMATA") |
                 (df["etichetta"] == "ROTTURA DA CONFERMARE")].sort_values("punteggio", ascending=False)
    pronte = df[df["etichetta"].isin(["IN PROSSIMITÀ (sotto)", "IN PROSSIMITÀ (sopra)",
                                      "IN AVVICINAMENTO (sotto)"])].sort_values(
        "distanza_pct", ascending=True)
    trend = df[df["etichetta"] == "TREND RIALZISTA (già sopra)"].sort_values("distanza_pct")
    ribassi = df[df["etichetta"].isin(["ROTTURA RIBASSISTA", "TREND RIBASSISTA (sotto)"])].sort_values(
        "distanza_pct")
    falsi = df[df["etichetta"] == "FALSO BREAKOUT / RIENTRO"].sort_values("punteggio", ascending=False)

    blocco("A) ROTTURE APPENA AVVENUTE (ultimi 5 giorni)", rotture)
    blocco("B) CANDIDATI PRONTI A ROMPERE AL RIALZO (prezzo a ridosso della MM200)", pronte)
    blocco("C) GIÀ IN TREND SOPRA LA MM200 (per confronto)", trend.head(12))
    blocco("D) FALSI BREAKOUT / RIENTRI SOTTO LA MEDIA (da evitare)", falsi)
    blocco("E) SOTTO LA MM200 (ribassiste, escluse dalla selezione long)", ribassi, max_righe=20)

    if "score_validato" in df.columns:
        val = df[df["score_validato"] >= 3].sort_values(["score_validato", "punteggio"], ascending=False)
        ampia = df[df["score_validato"] >= 2]
        print(f"\n{sep}")
        print(f"  SELEZIONE VALIDATA OUT-OF-SAMPLE (score_validato >= 3): {len(val)} titoli")
        print(f"  (con soglia >= 2 sarebbero {len(ampia)}: statisticamente valida ma poco selettiva)")
        print("  Componenti: score calibrato 2005-2015 e confermato 2016-2026 — recovery, MM200 in")
        print("  salita, MM50>MM200, forza relativa; penalità vicino ai massimi. Excess OOS misurato:")
        print("  +4 -> +18,4% | +3 -> +8,5% | +2 -> +1,7% | +1 -> -1,7% | <=0 -> -4,2% (baseline di stato)")
        print("  ATTENZIONE (esito del test di portafoglio, portafoglio.py): come strategia operativa")
        print("  questa selezione NON batte il buy&hold equal-weight dell'universo; gli ingressi casuali")
        print("  rendono come le rotture. Usa lo score come graduatoria di attenzione, non come sistema.")
        print(sep)
        for t, r in val.iterrows():
            print(f"  {t:<10} {str(r['nome'])[:26]:<27} score {r['score_validato']:+d} | "
                  f"dist {r['distanza_pct']:+.2f}% | dd {r['dd_252']:+.1f}% | {r['componenti_validati']}")
        print()

    crit = df[df["candidato"]].sort_values("punteggio", ascending=False)
    print(f"\n{sep}")
    print(f"  SELEZIONE FINALE (punteggio >= {cfg['soglia_punteggio']}): {len(crit)} titoli")
    print(sep)
    for t, r in crit.iterrows():
        print(f"  {t:<10} {str(r['nome'])[:26]:<27} {r['etichetta']:<28} "
              f"pt {r['punteggio']:.0f} | dist {r['distanza_pct']:+.2f}% | vol {r['vol_ratio']:.2f}x")
        if r.get("flag_significativita"):
            print(f"             note: {r['flag_significativita']}")
    print()
    return crit


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Scanner MM200 su Borsa Italiana")
    ap.add_argument("--indice", default="TUTTI", choices=["TUTTI", "MIB", "MID"],
                    help="universo da scansionare (default: TUTTI)")
    ap.add_argument("--periodo-anni", type=int, default=3, help="anni di storia da scaricare (default 3)")
    ap.add_argument("--soglia", type=float, default=CFG_DEFAULT["soglia_punteggio"],
                    help="punteggio minimo per la selezione finale")
    ap.add_argument("--distanza", type=float, default=CFG_DEFAULT["distanza_prontezza_pct"],
                    help="distanza massima (%% sotto la MM200) per essere 'a ridosso'")
    ap.add_argument("--volume", type=float, default=CFG_DEFAULT["volume_conferma"],
                    help="moltiplicatore volume per la conferma della rottura")
    ap.add_argument("--buffer", type=float, default=CFG_DEFAULT["buffer_stato_pct"],
                    help="buffer %% attorno alla MM200 (zona di transizione)")
    ap.add_argument("--no-download", action="store_true", help="usa solo la cache locale")
    ap.add_argument("--json", action="store_true", help="stampa anche il JSON dei risultati")
    args = ap.parse_args()

    cfg = dict(CFG_DEFAULT)
    cfg.update({
        "soglia_punteggio": args.soglia,
        "distanza_prontezza_pct": args.distanza,
        "volume_conferma": args.volume,
        "buffer_stato_pct": args.buffer,
        "anni": args.periodo_anni,
    })

    tickers = tu.solo_ticker(args.indice)
    print(f"Universo {args.indice}: {len(tickers)} titoli. Download in corso...")

    if args.no_download:
        dati = carica_da_cache()
        mancanti = [t for t in tickers if t not in dati]
        dati = {t: dati[t] for t in tickers if t in dati}
    else:
        dati, mancanti = scarica_dati(tickers, anni=args.periodo_anni)

    if not dati:
        print("Nessun dato disponibile. Controlla la connessione o la cache.")
        return 1

    df = analizza(dati, cfg)
    # forza relativa: percentile del rendimento a 12 mesi DENTRO l'universo
    # scansionato (informativa: da sola non è un filtro, vedi filtri_check.py)
    if len(df) and "ret_12m" in df.columns:
        df["rs_rank_12m"] = (df["ret_12m"].rank(pct=True) * 100).round(1)
    df = aggiungi_punteggio_validato(df)
    mercato = contesto_mercato(dati, cfg)
    stampa_console(df, cfg, mancanti, mercato)

    os.makedirs(OUT_DIR, exist_ok=True)
    data_rif = df["data"].iloc[0].replace("-", "") if len(df) else datetime.now().strftime("%Y%m%d")
    csv_path = esporta_csv(df, os.path.join(OUT_DIR, f"segnali_mm200_{data_rif}.csv"))
    html_path = scrivi_report(df, mercato, cfg, mancanti, OUT_DIR, data_rif)

    riepilogo = {
        "data_analisi": data_rif,
        "universo": args.indice,
        "titoli_analizzati": int(len(df)),
        "titoli_senza_dati": mancanti,
        "contesto_mercato": mercato,
        "candidati": df[df["candidato"]].sort_values("punteggio", ascending=False)
                       .reset_index().to_dict(orient="records") if len(df) else [],
    }
    json_path = os.path.join(OUT_DIR, f"segnali_mm200_{data_rif}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(riepilogo, f, ensure_ascii=False, indent=2, default=str)

    print(f"  CSV  -> {csv_path}")
    print(f"  HTML -> {html_path}")
    print(f"  JSON -> {json_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
