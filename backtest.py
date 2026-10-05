#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RICERCA: SIGNIFICATIVITÀ DELLA ROTTURA DELLA MM200 SU PIAZZA AFFARI
===================================================================

Questo modulo risponde a una domanda precisa e verificabile:

    "Una rottura della media a 200 periodi su un titolo italiano ha un
     rendimento atteso statisticamente diverso da un giorno/periodo a caso?
     E il timeframe (giornaliero vs settimanale) o i filtri (volumi,
     pendenza della media, conferma settimanale) cambiano le cose?"

Metodo:
  1. per ogni titolo dell'universo e per tutta la storia disponibile si
     individuano gli incroci al rialzo della MM200 (buffer ±1% anti-rumore);
  2. per ogni incrocio si misura il rendimento FORWARD a orizzonte fisso
     (21 / 63 / 126 / 250 sedute; in versione settimanale: 4 / 13 / 26 / 52);
  3. si costruisce la baseline con TUTTE le finestre della stessa lunghezza
     sullo stesso paniere (rendimento medio di un periodo qualunque);
  4. t-test sul campione delle rotture contro la media baseline;
  5. si ripete la statistica per i sottoinsiemi filtrati (volumi, pendenza
     della MM200, conferma settimanale, MM50 sopra MM200, RSI);
  6. si misura anche la versione "operativa" (ingresso all'apertura dopo la
     rottura, uscita al rientro sotto la media): win rate, profit factor,
     giorni di detenzione.

Uso:
    python3 backtest.py --dal 2005-01-01
    python3 backtest.py --dal 2010-01-01 --orizzonte 250

Limiti dichiarati (leggere prima di trarre conclusioni):
  - finestre sovrapposte: i campioni non sono indipendenti, i t-test sono
    quindi OTTIMISTICI (gonfiati); servono come indicazione, non come prova;
  - nessun costo di transazione, nessuno slippage, nessuna tassa;
  - survivorship bias parziale: l'universo è quello quotato oggi, i titoli
    delistati in passato non compaiono;
  - i rendimenti da breakout sono asimmetrici (molte piccole perdite, poche
    grandi vincite): la media è la statistica giusta, la mediana no.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import titoli_italiani as tu   # noqa: E402
import indicatori as ind      # noqa: E402

OUT_DIR = os.path.join(BASE_DIR, "output")
ORIZZONTI_GIORNO = [21, 63, 126, 250]
ORIZZONTI_SETT = [4, 13, 26, 52]      # in settimane (≈ 1 mese, 3 mesi, 6 mesi, 1 anno)


# ---------------------------------------------------------------------------
# statistica
# ---------------------------------------------------------------------------

def t_test(x, mu):
    """t di Student del campione x contro la media di riferimento mu."""
    x = np.asarray([v for v in x if np.isfinite(v)], dtype=float)
    n = len(x)
    if n < 5:
        return np.nan, np.nan
    sd = x.std(ddof=1)
    if sd == 0:
        return np.nan, np.nan
    t = (x.mean() - mu) / (sd / np.sqrt(n))
    try:
        from scipy import stats
        p = 2 * (1 - stats.t.cdf(abs(t), df=n - 1))
    except Exception:
        from math import erfc, sqrt
        p = erfc(abs(t) / sqrt(2))
    return float(t), float(p)


# ---------------------------------------------------------------------------
# estrazione dei segnali
# ---------------------------------------------------------------------------

def rendimenti_forward(serie_chiusure, pos, orizzonti, prezzi_alt=None):
    """Rendimenti % forward a orizzonte fisso a partire dalla posizione pos."""
    out = {}
    base = serie_chiusure.iloc[pos]
    for h in orizzonti:
        if pos + h < len(serie_chiusure):
            fine = serie_chiusure.iloc[pos + h]
            out[h] = float((fine / base - 1) * 100)
        else:
            out[h] = np.nan
    return out


def segnali_titolo(df, timeframe="giornaliero", buffer_pct=1.0, dal=None):
    """
    Individua gli incroci al rialzo della MM200 (giornaliero) o della MM40
    settimanale (equivalente: 200 sedute ≈ 40 settimane) e ne misura il
    rendimento forward con i relativi filtri di contesto.
    """
    if timeframe == "settimanale":
        df = ind.serie_settimanale(df)
        periodo_mm, vol_finestra, orizzonti = 40, 10, ORIZZONTI_SETT
        orizzonte_op = 52
    else:
        periodo_mm, vol_finestra, orizzonti = 200, 50, ORIZZONTI_GIORNO
        orizzonte_op = 250

    if dal is not None:
        # mantengo ~1 anno di storico prima del periodo di test per le medie
        df = df[df.index >= pd.Timestamp(dal) - pd.Timedelta(days=400)]
    if len(df) < periodo_mm + 30:
        return []

    c = df["Close"]
    mm = ind.sma(c, periodo_mm)
    mm_breve = ind.sma(c, max(5, periodo_mm // 4))
    vol_medio = df["Volume"].rolling(vol_finestra, min_periods=max(3, vol_finestra // 3)).mean()
    vol_ratio = (df["Volume"] / vol_medio).replace([np.inf, -np.inf], np.nan)
    r = ind.rsi(c, 14)
    stato = ind.stato_mm200(c, mm, buffer_pct)
    slope = ind.slope_pct(mm, max(5, periodo_mm // 10))

    # contesto: il timeframe "superiore" (per il settimanale usiamo il mensile)
    if timeframe == "settimanale":
        sup = c.resample("ME").last().dropna()
        sma_sup = ind.sma(sup, 10) if len(sup) >= 10 else pd.Series(np.nan, index=sup.index)
    else:
        sup = None
        sma_sup = None

    def contesto_superiore(data):
        if sup is None:
            return None
        s = sup[sup.index <= data]
        if not len(s):
            return None
        try:
            v = sma_sup.loc[s.index[-1]]
            return bool(not np.isnan(v) and s.iloc[-1] > v)
        except Exception:
            return None

    segnali = []
    for pos, data in ind.trova_incroci(stato, "SOPRA"):
        if pos + 2 >= len(df):
            continue
        fwd = rendimenti_forward(c, pos, orizzonti)

        # versione operativa: ingresso all'apertura successive, uscita al rientro
        prezzo_ing = float(df["Open"].iloc[pos + 1]) if "Open" in df else float(c.iloc[pos + 1])
        fine = min(pos + 1 + orizzonte_op, len(df) - 1)
        prezzo_usc, giorni = float(c.iloc[fine]), fine - pos - 1
        for j in range(pos + 2, fine + 1):
            m = mm.iloc[j]
            if np.isnan(m):
                continue
            if c.iloc[j] < m * (1 - buffer_pct / 100) and j >= pos + 4:
                prezzo_usc, giorni = float(c.iloc[j]), j - pos - 1
                break
        rend_op = (prezzo_usc / prezzo_ing - 1) * 100 if prezzo_ing > 0 else np.nan

        segnali.append({
            "data": data.strftime("%Y-%m-%d"),
            "fwd": fwd,
            "op_rend": rend_op,
            "op_giorni": giorni,
            "vol_ratio": float(vol_ratio.loc[data]) if data in vol_ratio.index and np.isfinite(vol_ratio.loc[data]) else np.nan,
            "rsi": float(r.loc[data]) if data in r.index and np.isfinite(r.loc[data]) else np.nan,
            "slope": float(slope.loc[data]) if data in slope.index and np.isfinite(slope.loc[data]) else np.nan,
            "mm_breve_sopra": bool(mm_breve.loc[data] > mm.loc[data]) if data in mm_breve.index and np.isfinite(mm_breve.loc[data]) else None,
            "weekly_ok": contesto_superiore(data),
        })
    return segnali


def baseline(df, orizzonti, timeframe="giornaliero", dal=None):
    """Rendimenti di TUTTE le finestre della stessa lunghezza (il 'periodo qualunque')."""
    if timeframe == "settimanale":
        df = ind.serie_settimanale(df)
    if dal is not None:
        df = df[df.index >= pd.Timestamp(dal)]
    c = df["Close"]
    out = {}
    for h in orizzonti:
        r = ((c.shift(-h) / c - 1) * 100).dropna()
        out[h] = r.tolist()
    return out


# ---------------------------------------------------------------------------
# analisi
# ---------------------------------------------------------------------------

def analizza_timeframe(dati, timeframe, dal):
    orizzonti = ORIZZONTI_SETT if timeframe == "settimanale" else ORIZZONTI_GIORNO
    tutti, base_tutte = [], {h: [] for h in orizzonti}
    for t, df in dati.items():
        s = segnali_titolo(df, timeframe=timeframe, dal=dal)
        for x in s:
            x["titolo"] = t
        tutti += s
        b = baseline(df, orizzonti, timeframe=timeframe, dal=dal)
        for h in orizzonti:
            base_tutte[h] += b[h]
    return tutti, base_tutte


def riga_tabella(nome, segnali, base, orizzonti, chiave_fwd="fwd"):
    """Statistiche di significatività per un gruppo di segnali."""
    righe = []
    for h in orizzonti:
        rend = [s[chiave_fwd][h] for s in segnali if s.get(chiave_fwd) and np.isfinite(s[chiave_fwd].get(h, np.nan))]
        if not rend:
            continue
        mu_base = float(np.mean(base[h])) if base[h] else 0.0
        t, p = t_test(rend, mu_base)
        rend = np.array(rend)
        righe.append({
            "gruppo": nome,
            "orizzonte": h,
            "n": len(rend),
            "rend_medio": round(float(rend.mean()), 2),
            "baseline": round(mu_base, 2),
            "delta": round(float(rend.mean()) - mu_base, 2),
            "win_rate": round(float((rend > 0).mean() * 100), 1),
            "t_stat": round(float(t), 2) if np.isfinite(t) else None,
            "p_value": round(float(p), 4) if np.isfinite(p) else None,
        })
    return righe


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Ricerca sulla significatività delle rotture MM200")
    ap.add_argument("--dal", default="2005-01-01", help="inizio del periodo di test")
    ap.add_argument("--indice", default="TUTTI", choices=["TUTTI", "MIB", "MID"])
    args = ap.parse_args()

    import yfinance as yf

    tickers = tu.solo_ticker(args.indice)
    print(f"Scarico la storia completa di {len(tickers)} titoli di Piazza Affari...")
    raw = yf.download(tickers, period="max", interval="1d", auto_adjust=True,
                      group_by="ticker", threads=True, progress=False)
    dati = {}
    for t in tickers:
        try:
            df = raw[t].dropna(how="all").dropna(subset=["Close"])
        except Exception:
            continue
        if len(df) > 500:
            dati[t] = df
    print(f"Titoli con storia sufficiente: {len(dati)}\n")

    report = {}

    for timeframe in ("giornaliero", "settimanale"):
        orizzonti = ORIZZONTI_SETT if timeframe == "settimanale" else ORIZZONTI_GIORNO
        segnali, base = analizza_timeframe(dati, timeframe, args.dal)
        etichetta_h = "settimane" if timeframe == "settimanale" else "sedute"
        print("=" * 100)
        print(f"TIMEFRAME {timeframe.upper()} — {len(segnali)} rotture rilevate dal {args.dal}")
        print(f"(orizzonti in {etichetta_h}: " + ", ".join(map(str, orizzonti)) + ")")
        print("=" * 100)

        # --- 1) tutte le rotture vs baseline ---
        tab = pd.DataFrame(riga_tabella("tutte", segnali, base, orizzonti))
        print("\n1) TUTTE LE ROTTURE vs BASELINE (periodo qualunque)\n")
        _stampa(tab)

        # --- 2) effetto dei filtri ---
        gruppi = {
            "vol ≥1,5x": lambda s: s["vol_ratio"] >= 1.5,
            "vol ≥2x": lambda s: s["vol_ratio"] >= 2.0,
            "vol <1,5x (debole)": lambda s: s["vol_ratio"] < 1.5,
            "MM non in discesa": lambda s: s["slope"] > -1,
            "MM in salita": lambda s: s["slope"] > 1,
            "media breve sopra la lunga": lambda s: s["mm_breve_sopra"] is True,
            "conferma TF superiore": lambda s: s["weekly_ok"] is True,
            "RSI 45-75": lambda s: 45 <= s["rsi"] <= 75,
        }
        print(f"\n2) EFFETTO DEI FILTRI (orizzonte lunghezza massima: {orizzonti[-1]} {etichetta_h})\n")
        righe = []
        for nome, cond in gruppi.items():
            sel = [s for s in segnali if _sicuro(cond, s)]
            righe += riga_tabella(nome, sel, base, orizzonti)
        tabf = pd.DataFrame(righe)
        _stampa(tabf)

        # --- 3) combinazione dei filtri migliori ---
        print("\n3) COMBINAZIONI DI FILTRI\n")
        combos = {
            "vol≥1,5x + MM non in discesa": lambda s: s["vol_ratio"] >= 1.5 and s["slope"] > -1,
            "vol≥1,5x + conferma TF sup.": lambda s: s["vol_ratio"] >= 1.5 and s["weekly_ok"] is True,
            "vol≥1,5x + MM in salita + media breve sopra": lambda s: s["vol_ratio"] >= 1.5 and s["slope"] > 0 and s["mm_breve_sopra"] is True,
            "tutti i filtri (vol+slope+breve+sup)": lambda s: s["vol_ratio"] >= 1.5 and s["slope"] > 0 and s["mm_breve_sopra"] is True and s["weekly_ok"] is True,
        }
        righe = []
        for nome, cond in combos.items():
            sel = [s for s in segnali if _sicuro(cond, s)]
            righe += riga_tabella(nome, sel, base, orizzonti)
        tabc = pd.DataFrame(righe)
        _stampa(tabc)

        # --- 4) versione operativa (con uscita) ---
        print("\n4) VERSIONE OPERATIVA (ingresso all'apertura, uscita al rientro sotto la media)\n")
        op = [s for s in segnali if np.isfinite(s["op_rend"])]
        rend = np.array([s["op_rend"] for s in op])
        vinc = (rend > 0).mean() * 100
        guad, perd = rend[rend > 0].sum(), -rend[rend < 0].sum()
        print(f"   Tutte le rotture: n={len(rend)}  win={vinc:.1f}%  rend.medio={rend.mean():+.2f}%  "
              f"mediana={np.median(rend):+.2f}%  PF={guad/perd:.2f}  giorni medi={np.mean([s['op_giorni'] for s in op]):.0f}")
        for nome, cond in combos.items():
            sel = [s for s in op if _sicuro(cond, s)]
            if len(sel) < 10:
                continue
            r2 = np.array([s["op_rend"] for s in sel])
            g2, p2 = r2[r2 > 0].sum(), -r2[r2 < 0].sum()
            print(f"   {nome:<46} n={len(r2):<5} win={(r2>0).mean()*100:>5.1f}%  "
                  f"rend.medio={r2.mean():+.2f}%  PF={g2/p2:.2f}  giorni={np.mean([s['op_giorni'] for s in sel]):.0f}")

        report[timeframe] = {
            "n_segnali": len(segnali),
            "tutte": tab.to_dict(orient="records"),
            "filtri": tabf.to_dict(orient="records"),
            "combinazioni": tabc.to_dict(orient="records"),
            "operativo": {
                "n": int(len(rend)),
                "win_rate": round(float(vinc), 1),
                "rend_medio": round(float(rend.mean()), 2),
                "mediana": round(float(np.median(rend)), 2),
                "profit_factor": round(float(guad / perd), 2),
                "giorni_medi": round(float(np.mean([s["op_giorni"] for s in op])), 0),
            },
        }
        print()

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "ricerca_significativita_mm200.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # CSV riassuntivo per anno (timeframe giornaliero, tutte le rotture)
    seg_g, base_g = analizza_timeframe(dati, "giornaliero", args.dal)
    df_y = pd.DataFrame([{"anno": r["data"][:4], "fwd_250": r["fwd"].get(250, np.nan),
                          "op_rend": r["op_rend"]} for r in seg_g])
    riep = df_y.groupby("anno").agg(n=("fwd_250", "count"), fwd_250_medio=("fwd_250", "mean"),
                                    win_rate=("fwd_250", lambda x: (x > 0).mean() * 100)).round(2)
    riep.to_csv(os.path.join(OUT_DIR, "ricerca_per_anno.csv"), sep=";", decimal=",", encoding="utf-8-sig")
    print("Stabilità nel tempo (timeframe giornaliero, rendimento forward a 250 sedute):")
    print(riep.to_string())
    print(f"\nSalvato: {os.path.join(OUT_DIR, 'ricerca_significativita_mm200.json')}")
    return 0


def _sicuro(cond, s):
    try:
        return bool(cond(s))
    except Exception:
        return False


def _stampa(tab):
    if tab.empty:
        print("   (nessun dato)")
        return
    print(f"{'gruppo':<44}{'oriz':>6}{'n':>7}{'rend%':>8}{'base%':>8}{'delta':>8}"
          f"{'win%':>7}{'t':>7}{'p':>8}")
    print("-" * 103)
    for _, r in tab.iterrows():
        t = f"{r['t_stat']:.2f}" if r["t_stat"] is not None else "—"
        p = f"{r['p_value']:.4f}" if r["p_value"] is not None else "—"
        print(f"{str(r['gruppo'])[:43]:<44}{r['orizzonte']:>6}{r['n']:>7}{r['rend_medio']:>8.2f}"
              f"{r['baseline']:>8.2f}{r['delta']:>8.2f}{r['win_rate']:>7.1f}{t:>7}{p:>8}")


if __name__ == "__main__":
    sys.exit(main())
