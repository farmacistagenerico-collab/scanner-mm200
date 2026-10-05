#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOLUME LAB — il volume come filtro / validatore della rottura della MM200
=========================================================================

Domanda: abbinare il volume alla rottura della MM200 aumenta davvero la
probabilità che il movimento sia significativo? E se sì, QUALE misura di
volume funziona — e funziona *in aggiunta* alla struttura di trend, o è la
struttura a fare tutto il lavoro?

Questo modulo è costruito per rispondere a quella seconda domanda, che il
backtest precedente non isolava: lì volume e struttura erano testati
insieme, quindi non si sapeva chi dei due portasse il vantaggio.

Metodo
------
1. Eventi: tutte le rotture al rialzo della MM200 (buffer ±1%) dei titoli di
   Piazza Affari, dal 2005 a oggi (~4.000 eventi).
2. Per ogni evento si calcolano 13 misure di volume/qualità della barra
   NOTE AL MOMENTO DELLA ROTTURA (nessun look-ahead) + 1 validatore noto
   solo 3 giorni dopo.
3. Test:
   A) dose-risposta: il rendimento forward cresce col volume? (bucket + Spearman)
   B) 2x2 STRUTTURA x VOLUME: il volume aggiunge qualcosa *a parità di struttura*?
   C) singole metriche: ciascuna confrontata con le rotture che NON la rispettano
   D) punteggio composito di volume (0-5): monotonia e soglia utile
   E) validatore a 3 giorni: aspettare la conferma dei volumi migliora l'esito?
   F) robustezza 2005-2014 vs 2015-oggi
   G) effetto della liquidità (il volume conta di più sui titoli liquidi?)

Statistica: test t di Welch (campioni indipendenti) fra sottoinsiemi, e
t-test contro baseline per contesto. ATTENZIONE: le finestre forward si
sovrappongono → i p-value sono OTTIMISTICI. Vanno letti come indicazione.

Uso:
    python3 volume_lab.py
    python3 volume_lab.py --dal 2005-01-01
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
ORIZZONTI = [21, 63, 126, 250]        # sedute


# ---------------------------------------------------------------------------
# statistica
# ---------------------------------------------------------------------------

def _pulito(x):
    return np.asarray([v for v in np.asarray(x, dtype=float) if np.isfinite(v)], dtype=float)


def t_vs_base(x, mu):
    """t-test del campione x contro la media di riferimento mu."""
    x = _pulito(x)
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


def welch(x, y):
    """Test t di Welch fra due campioni indipendenti (alta vs bassa metrica)."""
    x, y = _pulito(x), _pulito(y)
    if len(x) < 5 or len(y) < 5:
        return np.nan, np.nan
    try:
        from scipy import stats
        t, p = stats.ttest_ind(x, y, equal_var=False)
        return float(t), float(p)
    except Exception:
        se = np.sqrt(x.var(ddof=1) / len(x) + y.var(ddof=1) / len(y))
        if se == 0:
            return np.nan, np.nan
        t = (x.mean() - y.mean()) / se
        from math import erfc, sqrt
        return float(t), float(erfc(abs(t) / sqrt(2)))


def spearman(x, y):
    # tengo le COPPIE (x_i, y_i) entrambe finite: filtrare le due serie
    # separatamente disallineerebbe i valori
    coppie = [(a, b) for a, b in zip(x, y)
              if np.isfinite(a) and np.isfinite(b)]
    if len(coppie) < 10:
        return np.nan, np.nan
    x, y = map(np.asarray, zip(*coppie))
    rx = pd.Series(x).rank().values
    ry = pd.Series(y).rank().values
    r = np.corrcoef(rx, ry)[0, 1]
    n = len(x)
    if abs(r) >= 1:
        return float(r), 0.0
    t = r * np.sqrt((n - 2) / (1 - r * r))
    try:
        from scipy import stats
        p = 2 * (1 - stats.t.cdf(abs(t), df=n - 2))
    except Exception:
        from math import erfc, sqrt
        p = erfc(abs(t) / sqrt(2))
    return float(r), float(p)


# ---------------------------------------------------------------------------
# metriche di volume
# ---------------------------------------------------------------------------

def mfi(df: pd.DataFrame, periodo: int = 14) -> pd.Series:
    """Money Flow Index: volume pesato dalla direzione del prezzo tipico."""
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    mf = tp * df["Volume"]
    pos = mf.where(tp.diff() > 0, 0.0)
    neg = mf.where(tp.diff() < 0, 0.0)
    rap = pos.rolling(periodo).sum() / neg.rolling(periodo).sum().replace(0, np.nan)
    return 100 - 100 / (1 + rap)


def obv(df: pd.DataFrame) -> pd.Series:
    """On-Balance Volume."""
    direzione = np.sign(df["Close"].diff()).fillna(0)
    return (direzione * df["Volume"]).cumsum()


def prepara(df: pd.DataFrame) -> dict:
    """Precalcola le serie necessarie alle metriche di evento."""
    c, v = df["Close"], df["Volume"].astype(float)
    rng = (df["High"] - df["Low"]).replace(0, np.nan)

    vol_prev = v.rolling(50, min_periods=20).mean().shift(1)     # media 50 sedute PRECEDENTI
    rv = v / vol_prev

    o = obv(df)
    o_ma = ind.sma(o, 50)

    segno = np.sign(c.diff()).fillna(0)
    vol_su = v.where(segno > 0, 0.0).rolling(20).sum()
    vol_giu = v.where(segno < 0, 0.0).rolling(20).sum()

    return {
        "close": c, "volume": v, "rng": rng,
        "mm200": ind.sma(c, 200), "mm50": ind.sma(c, 50),
        "slope20": ind.slope_pct(ind.sma(c, 200), 20),
        "rv": rv,
        "rv_pre5": rv.rolling(5).median().shift(1),              # compressione prima della rottura
        "rv_5g": rv.rolling(5).mean(),                            # volume sostenuto (5 gg, rottura inclusa)
        "vol20_50": v.rolling(20).mean() / v.rolling(50).mean(),  # volume in accumulo
        "close_pos": (c - df["Low"]) / rng,                       # chiusura nella parte alta della barra
        "body": (c - df["Open"]).abs() / rng,
        "atr_rel": rng / ind.atr(df, 14),                         # espansione di volatilità
        "updown20": vol_su / vol_giu.replace(0, np.nan),
        "obv": o, "obv_ma": o_ma,
        "obv_slope20": (o - o.shift(20)) / (vol_prev * 20),       # pendenza OBV normalizzata
        "mfi14": mfi(df, 14),
        "dollar": (c * v).rolling(250, min_periods=100).median(), # liquidità (€/seduta)
    }


def evento(s: dict, pos: int, df: pd.DataFrame) -> dict | None:
    """Estrae le metriche di volume di un singolo evento di rottura."""
    def val(nome, i=pos):
        try:
            x = s[nome].iloc[i]
            return float(x) if np.isfinite(x) else np.nan
        except Exception:
            return np.nan

    rv0 = val("rv")
    if not np.isfinite(rv0):
        return None

    # validatore: volume medio dei 3 giorni SUCCESSIVI alla rottura (noto solo dopo)
    rv3 = np.nan
    if pos + 2 < len(df):
        r = s["rv"].iloc[pos:pos + 3]
        if r.notna().sum() >= 2:
            rv3 = float(r.mean())

    # percentile del volume odierno negli ultimi 252 giorni (esclusa oggi)
    vp = np.nan
    if pos >= 60:
        finestra = s["volume"].iloc[max(0, pos - 252):pos]
        finestra = _pulito(finestra)
        if len(finestra) >= 50:
            vp = float((finestra <= s["volume"].iloc[pos]).mean() * 100)

    ev = {
        "rv0": rv0,
        "rv_pre5": val("rv_pre5"),
        "rv_5g": val("rv_5g"),
        "vol20_50": val("vol20_50"),
        "vol_pctile": vp,
        "close_pos": val("close_pos"),
        "body": val("body"),
        "atr_rel": val("atr_rel"),
        "updown20": val("updown20"),
        "obv_above": float(s["obv"].iloc[pos] > s["obv_ma"].iloc[pos])
                     if np.isfinite(val("obv_ma")) else np.nan,
        "obv_slope20": val("obv_slope20"),
        "mfi14": val("mfi14"),
        "dollar": val("dollar"),
        "rv3": rv3,
        "struttura_ok": float(val("slope20") > 0 and val("mm50") > val("mm200"))
                        if np.isfinite(val("slope20")) and np.isfinite(val("mm50")) else np.nan,
    }
    return ev


def eventi(df: pd.DataFrame, dal=None) -> list[dict]:
    """Tutti gli eventi di rottura al rialzo della MM200 con metriche e rendimenti forward."""
    df = df.dropna(subset=["Close"]).copy()
    if len(df) < 320:
        return []
    if dal is not None:
        df = df[df.index >= pd.Timestamp(dal) - pd.Timedelta(days=420)]
    if len(df) < 320:
        return []

    s = prepara(df)
    stato = ind.stato_mm200(s["close"], s["mm200"], 1.0)
    incroci = ind.trova_incroci(stato, "SOPRA")

    out = []
    for pos, data in incroci:
        if pos + 4 >= len(df):
            continue
        ev = evento(s, pos, df)
        if ev is None:
            continue
        base = s["close"].iloc[pos]
        rend = {}
        for h in ORIZZONTI:
            rend[h] = float((s["close"].iloc[pos + h] / base - 1) * 100) if pos + h < len(df) else np.nan
        # rendimenti misurati DOPO l'eventuale validazione a 3 giorni
        rend3 = {}
        j = pos + 3
        if j + 21 < len(df):
            b3 = s["close"].iloc[j]
            for h in (21, 63, 126, 250):
                rend3[h] = float((s["close"].iloc[j + h] / b3 - 1) * 100) if j + h < len(df) else np.nan
        ev.update({
            "data": data.strftime("%Y-%m-%d"),
            "anno": int(data.year),
            "rend": rend,
            "rend3": rend3,
        })
        out.append(ev)
    return out


def baseline(df: pd.DataFrame, dal=None) -> dict:
    """Rendimenti di tutte le finestre della stessa lunghezza (periodo qualunque)."""
    df = df.dropna(subset=["Close"])
    if dal is not None:
        df = df[df.index >= pd.Timestamp(dal)]
    c = df["Close"]
    return {h: _pulito(((c.shift(-h) / c - 1) * 100).dropna()) for h in ORIZZONTI}


# ---------------------------------------------------------------------------
# tabelle
# ---------------------------------------------------------------------------

def riga_tab(nome, sel, base, orizzonte=250, chiave="rend"):
    rend = np.array([e[chiave].get(orizzonte, np.nan) for e in sel], dtype=float)
    rend = _pulito(rend)
    if len(rend) < 5:
        return None
    mu = float(np.mean(base[orizzonte])) if base.get(orizzonte) is not None else np.nan
    t, p = t_vs_base(rend, mu)
    return {
        "gruppo": nome, "n": len(rend), "win_rate": round(float((rend > 0).mean() * 100), 1),
        "rend_medio": round(float(rend.mean()), 2), "mediana": round(float(np.median(rend)), 2),
        "baseline": round(mu, 2) if np.isfinite(mu) else None,
        "delta": round(float(rend.mean()) - mu, 2) if np.isfinite(mu) else None,
        "t_vs_base": round(t, 2) if np.isfinite(t) else None,
        "p_vs_base": round(p, 4) if np.isfinite(p) else None,
    }


def tab(welf=100):
    return f"{'gruppo':<{welf}}"


def _stampa(df, titolo, welf=52):
    print(f"\n{titolo}")
    print("-" * 118)
    print(f"{'gruppo':<{welf}}{'n':>7}{'win%':>7}{'rend%':>9}{'mediana':>9}{'base%':>8}"
          f"{'delta':>8}{'t':>7}{'p':>9}")
    print("-" * 118)
    for _, r in df.iterrows():
        if r["n"] is None or (isinstance(r["n"], float) and np.isnan(r["n"])):
            continue
        print(f"{str(r['gruppo'])[:welf-1]:<{welf}}{int(r['n']):>7}{r['win_rate']:>7.1f}"
              f"{r['rend_medio']:>9.2f}{r['mediana']:>9.2f}"
              f"{(r['baseline'] if r['baseline'] is not None else float('nan')):>8.2f}"
              f"{(r['delta'] if r['delta'] is not None else float('nan')):>8.2f}"
              f"{(r['t_vs_base'] if r['t_vs_base'] is not None else float('nan')):>7.2f}"
              f"{(r['p_vs_base'] if r['p_vs_base'] is not None else float('nan')):>9.4f}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Il volume come filtro della rottura della MM200")
    ap.add_argument("--dal", default="2005-01-01")
    ap.add_argument("--indice", default="TUTTI", choices=["TUTTI", "MIB", "MID"])
    args = ap.parse_args()

    import yfinance as yf

    tickers = tu.solo_ticker(args.indice)
    print(f"Scarico la storia completa di {len(tickers)} titoli di Piazza Affari...")
    raw = yf.download(tickers, period="max", interval="1d", auto_adjust=True,
                      group_by="ticker", threads=True, progress=False)

    tutti, base = [], {h: [] for h in ORIZZONTI}
    for t in tickers:
        try:
            df = raw[t].dropna(how="all").dropna(subset=["Close"])
        except Exception:
            continue
        if len(df) < 500:
            continue
        ev = eventi(df, dal=args.dal)
        for e in ev:
            e["titolo"] = t
        tutti += ev
        b = baseline(df, dal=args.dal)
        for h in ORIZZONTI:
            base[h] += list(b[h])

    print(f"\n{len(tutti)} rotture al rialzo della MM200 con dati di volume, "
          f"{len({e['titolo'] for e in tutti})} titoli, dal {args.dal}.")
    print(f"Baseline (tutte le finestre): 250 sedute = {np.mean(base[250]):+.2f}%  |  "
          f"63 sedute = {np.mean(base[63]):+.2f}%")

    risultato = {}

    # ---------------------------------------------------------------- A) dose-risposta
    bucket = [(0, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, 99)]
    righe = []
    for lo, hi in bucket:
        sel = [e for e in tutti if lo <= e["rv0"] < hi]
        r = riga_tab(f"volume {lo:g}-{hi:g}x" if hi < 99 else f"volume ≥{lo:g}x", sel, base, 250)
        if r:
            righe.append(r)
    tabA = pd.DataFrame(righe)
    _stampa(tabA, "A) DOSE-RISPOSTA: rendimento a 250 sedute per livello di volume sulla rottura")
    # confronto diretto alto vs basso
    alto = [e["rend"][250] for e in tutti if e["rv0"] >= 1.5]
    basso = [e["rend"][250] for e in tutti if e["rv0"] < 1.5]
    tW, pW = welch(alto, basso)
    rho, p_rho = spearman([e["rv0"] for e in tutti], [e["rend"][250] for e in tutti])
    print(f"\n   Volume ≥1,5x vs <1,5x (Welch):  media {np.nanmean(alto):+.2f}% vs {np.nanmean(basso):+.2f}%"
          f"   t={tW:.2f}  p={pW:.4f}")
    print(f"   Correlazione (Spearman) volume↔rendimento 250 sedute: rho={rho:+.3f}  p={p_rho:.4f}")
    risultato["A_dose_risposta"] = {"buckets": righe, "welch_t": round(tW, 2), "welch_p": round(pW, 4),
                                    "spearman_rho": round(rho, 3), "spearman_p": round(p_rho, 4)}

    # ---------------------------------------------------------------- B) 2x2 struttura x volume
    righe = []
    for nome_s, f_s in (("struttura OK", lambda e: e["struttura_ok"] == 1),
                        ("struttura NO", lambda e: e["struttura_ok"] == 0)):
        for nome_v, f_v in (("vol ≥1,5x", lambda e: e["rv0"] >= 1.5),
                            ("vol <1,5x", lambda e: e["rv0"] < 1.5)):
            sel = [e for e in tutti if f_s(e) and f_v(e)]
            r = riga_tab(f"{nome_s} + {nome_v}", sel, base, 250)
            if r:
                righe.append(r)
    tabB = pd.DataFrame(righe)
    _stampa(tabB, "B) 2x2 — STRUTTURA (MM200 in salita e MM50>MM200) x VOLUME: chi porta il vantaggio?")
    svp = [e["rend"][250] for e in tutti if e["struttura_ok"] == 1 and e["rv0"] >= 1.5]
    svm = [e["rend"][250] for e in tutti if e["struttura_ok"] == 1 and e["rv0"] < 1.5]
    nvp = [e["rend"][250] for e in tutti if e["struttura_ok"] == 0 and e["rv0"] >= 1.5]
    nvm = [e["rend"][250] for e in tutti if e["struttura_ok"] == 0 and e["rv0"] < 1.5]
    t1, p1 = welch(svp, svm)
    t2, p2 = welch(nvp, nvm)
    print(f"\n   A parità di STRUTTURA BUONA, il volume aggiunge?  {np.nanmean(svp):+.2f}% vs {np.nanmean(svm):+.2f}%"
          f"   t={t1:.2f}  p={p1:.4f}")
    print(f"   A parità di STRUTTURA DEBOLE, il volume aiuta?    {np.nanmean(nvp):+.2f}% vs {np.nanmean(nvm):+.2f}%"
          f"   t={t2:.2f}  p={p2:.4f}")
    risultato["B_2x2"] = {"celle": righe, "struct_buona_vol_alto_vs_basso": [round(t1, 2), round(p1, 4)],
                          "struct_debole_vol_alto_vs_basso": [round(t2, 2), round(p2, 4)]}

    # ---------------------------------------------------------------- C) singole metriche
    metriche = {
        "chiusura nella parte alta della barra (close_pos ≥0,7)": lambda e: e["close_pos"] >= 0.7,
        "volume ≥1,5x la media 50": lambda e: e["rv0"] >= 1.5,
        "volume ≥2x la media 50": lambda e: e["rv0"] >= 2.0,
        "volume sostenuto (media 5 gg ≥1,5x)": lambda e: e["rv_5g"] >= 1.5,
        "percentile volume ≥90": lambda e: e["vol_pctile"] >= 90,
        "compressione: vol pre-rottura sotto la media (rv_pre5 <1)": lambda e: e["rv_pre5"] < 1.0,
        "volume in accumulo (vol20_50 ≥1,2)": lambda e: e["vol20_50"] >= 1.2,
        "OBV sopra la sua media 50": lambda e: e["obv_above"] == 1,
        "pendenza OBV 20g positiva": lambda e: e["obv_slope20"] > 0,
        "MFI 50-85 (afflussi senza ipercomprato)": lambda e: 50 <= e["mfi14"] <= 85,
        "rapporto volumi su/giù 20g ≥1,2": lambda e: e["updown20"] >= 1.2,
        "espansione range (range ≥1,3x ATR)": lambda e: e["atr_rel"] >= 1.3,
        "corpo ampio (≥50% del range)": lambda e: e["body"] >= 0.5,
    }
    righe = []
    for nome, cond in metriche.items():
        sel = [e for e in tutti if _ok(cond, e)]
        r = riga_tab(nome, sel, base, 250)
        if r:
            opp = [e["rend"][250] for e in tutti if not _ok(cond, e)]
            tW, pW = welch([e["rend"][250] for e in sel], opp)
            r["t_vs_resto"], r["p_vs_resto"] = round(tW, 2), round(pW, 4)
            righe.append(r)
    tabC = pd.DataFrame(righe)
    _stampa(tabC, "C) SINGOLE MISURE DI VOLUME/QUALITÀ (rendimento a 250 sedute)")
    if not tabC.empty:
        print("\n   (confronto col resto delle rotture: t e p Welch)")
        for _, r in tabC.iterrows():
            print(f"   {str(r['gruppo'])[:52]:<53} vs resto: t={r['t_vs_resto']:+.2f}  p={r['p_vs_resto']:.4f}")
    risultato["C_metriche"] = tabC.to_dict(orient="records") if not tabC.empty else []

    # ---------------------------------------------------------------- D) punteggio composito
    def score_volume(e):
        s = 0
        if e["rv0"] >= 1.5: s += 2
        if e["close_pos"] >= 0.7: s += 1
        if e["obv_above"] == 1: s += 1
        if e["updown20"] >= 1.2: s += 1
        if 50 <= e["mfi14"] <= 85: s += 1
        return s

    for e in tutti:
        e["score_vol"] = score_volume(e)
    righe = []
    for k in range(0, 7):
        sel = [e for e in tutti if e["score_vol"] == k]
        r = riga_tab(f"punteggio volume = {k}", sel, base, 250)
        if r:
            righe.append(r)
    righe.append(riga_tab("punteggio volume ≥4", [e for e in tutti if e["score_vol"] >= 4], base, 250))
    tabD = pd.DataFrame([r for r in righe if r])
    _stampa(tabD, "D) PUNTEGGIO COMPOSITO DI VOLUME (0-6): monotonia e soglia")

    # il test che conta: a parità di struttura, il punteggio di volume aggiunge?
    buona = [e for e in tutti if e["struttura_ok"] == 1]
    t4, p4 = welch([e["rend"][250] for e in buona if e["score_vol"] >= 4],
                   [e["rend"][250] for e in buona if e["score_vol"] < 4])
    _a = _pulito([e["rend"][250] for e in buona if e["score_vol"] >= 4])
    _b = _pulito([e["rend"][250] for e in buona if e["score_vol"] < 4])
    print(f"\n   Entro le rotture con STRUTTURA BUONA: punteggio volume ≥4 vs <4  →  "
          f"{_a.mean():+.2f}% (n={len(_a)}) vs {_b.mean():+.2f}% (n={len(_b)})   t={t4:.2f}  p={p4:.4f}")
    risultato["D_score"] = {"tabella": tabD.to_dict(orient="records"),
                            "struct_buona_score_alto_vs_basso": [round(t4, 2), round(p4, 4)]}

    # ---------------------------------------------------------------- E) validatore a 3 giorni
    con3 = [e for e in tutti if np.isfinite(e.get("rv3", np.nan))]
    conf = [e for e in con3 if e["rv3"] >= 1.2]
    nonc = [e for e in con3 if e["rv3"] < 1.2]
    def rend3(sel, h):
        return _pulito([e["rend3"].get(h, np.nan) for e in sel])
    righe = []
    for h in (21, 63, 126, 250):
        a, b = rend3(conf, h), rend3(nonc, h)
        tW, pW = welch(a, b)
        righe.append({"orizzonte": h, "n_conferma": len(a), "rend_conferma": round(float(a.mean()), 2),
                      "n_no": len(b), "rend_no": round(float(b.mean()), 2),
                      "t": round(tW, 2) if np.isfinite(tW) else None,
                      "p": round(pW, 4) if np.isfinite(pW) else None})
    tabE = pd.DataFrame(righe)
    print("\n\nE) VALIDATORE: aspettare 3 giorni e verificare i volumi (rendimenti misurati DOPO il giorno 3)\n")
    print(f"{'orizzonte':>10}{'n conf':>8}{'rend conf%':>12}{'n no':>7}{'rend no%':>10}{'t':>7}{'p':>9}")
    print("-" * 66)
    for _, r in tabE.iterrows():
        print(f"{r['orizzonte']:>10}{r['n_conferma']:>8}{r['rend_conferma']:>12.2f}"
              f"{r['n_no']:>7}{r['rend_no']:>10.2f}{(r['t'] if r['t'] is not None else float('nan')):>7.2f}"
              f"{(r['p'] if r['p'] is not None else float('nan')):>9.4f}")
    risultato["E_validatore"] = tabE.to_dict(orient="records")

    # ---------------------------------------------------------------- F) robustezza
    print("\n\nF) ROBUSTEZZA nel tempo — celle chiave su due metà del campione\n")
    meta1 = [e for e in tutti if e["anno"] <= 2014]
    meta2 = [e for e in tutti if e["anno"] >= 2015]
    righe = []
    for nome, sel in (
        ("tutte le rotture", lambda x: x),
        ("struttura OK", lambda x: [e for e in x if e["struttura_ok"] == 1]),
        ("struttura OK + vol ≥1,5x", lambda x: [e for e in x if e["struttura_ok"] == 1 and e["rv0"] >= 1.5]),
        ("struttura OK + vol <1,5x", lambda x: [e for e in x if e["struttura_ok"] == 1 and e["rv0"] < 1.5]),
        ("score volume ≥4", lambda x: [e for e in x if e["score_vol"] >= 4]),
    ):
        for epoca, dati_ep in (("2005-2014", meta1), ("2015-2026", meta2)):
            sel_ep = sel(dati_ep) if callable(sel) else sel
            r = riga_tab(f"{nome} | {epoca}", sel_ep, base, 250)
            if r:
                righe.append(r)
    tabF = pd.DataFrame(righe)
    _stampa(tabF, "F) Split-campione (nota: la baseline è unica per tutto il periodo)")

    # ---------------------------------------------------------------- G) liquidità
    print("\n\nG) LIQUIDITÀ: il volume conta di più sui titoli liquidi?\n")
    righe = []
    fasce = [("illiquidi (<1 M€/d)", 0, 1e6), ("medi (1-10 M€/d)", 1e6, 1e7), ("liquidi (>10 M€/d)", 1e7, 1e15)]
    for nome, lo, hi in fasce:
        sel = [e for e in tutti if np.isfinite(e["dollar"]) and lo <= e["dollar"] < hi]
        r = riga_tab(nome, sel, base, 250)
        if r:
            righe.append(r)
        rv_alto = [e["rend"][250] for e in sel if e["rv0"] >= 1.5]
        rv_basso = [e["rend"][250] for e in sel if e["rv0"] < 1.5]
        if len(rv_alto) >= 10 and len(rv_basso) >= 10:
            tW, pW = welch(rv_alto, rv_basso)
            print(f"   {nome:<22} n={len(sel):<5}  vol≥1,5x: {np.nanmean(rv_alto):+7.2f}% (n={len(rv_alto)})   "
                  f"vol<1,5x: {np.nanmean(rv_basso):+7.2f}% (n={len(rv_basso)})   t={tW:+.2f}  p={pW:.4f}")
    tabG = pd.DataFrame(righe)
    _stampa(tabG, "G) Rendimento a 250 sedute per fascia di liquidità")
    risultato["F_robustezza"] = tabF.to_dict(orient="records")
    risultato["G_liquidita"] = tabG.to_dict(orient="records")

    # ---------------------------------------------------------------- H) replica settimanale
    print("\n\nH) REPLICA SUL TIMEFRAME SETTIMANALE (controllo del risultato precedente)\n")
    sett_eventi = []
    for t in tickers:
        try:
            df = raw[t].dropna(how="all").dropna(subset=["Close"])
        except Exception:
            continue
        if len(df) < 500:
            continue
        w = ind.serie_settimanale(df)
        if args.dal is not None:
            w = w[w.index >= pd.Timestamp(args.dal) - pd.Timedelta(days=750)]
        if len(w) < 70:
            continue
        c, v = w["Close"], w["Volume"]
        mm40, mm10 = ind.sma(c, 40), ind.sma(c, 10)
        if mm40.notna().sum() < 40:
            continue
        sl = ind.slope_pct(mm40, 4)
        rv_w = v / v.rolling(10, min_periods=5).mean().shift(1)
        stato = ind.stato_mm200(c, mm40, 1.0)
        for pos, data in ind.trova_incroci(stato, "SOPRA"):
            if pos + 52 >= len(w):
                continue
            if not (np.isfinite(sl.iloc[pos]) and np.isfinite(mm10.iloc[pos])
                    and np.isfinite(rv_w.iloc[pos])):
                continue
            sett_eventi.append({
                "titolo": t, "data": data.strftime("%Y-%m-%d"),
                "rend52": float((c.iloc[pos + 52] / c.iloc[pos] - 1) * 100),
                "struttura_ok": float(sl.iloc[pos] > 0 and mm10.iloc[pos] > mm40.iloc[pos]),
                "rv_w": float(rv_w.iloc[pos]),
            })
    if sett_eventi:
        print(f"   Eventi settimanali: {len(sett_eventi)}\n")
        for nome_s, f_s in (("struttura OK", lambda e: e["struttura_ok"] == 1),
                            ("struttura NO", lambda e: e["struttura_ok"] == 0)):
            for nome_v, f_v in (("vol ≥1,5x", lambda e: e["rv_w"] >= 1.5),
                                ("vol <1,5x", lambda e: e["rv_w"] < 1.5)):
                rend = _pulito([e["rend52"] for e in sett_eventi if f_s(e) and f_v(e)])
                if len(rend) >= 5:
                    print(f"   {nome_s} + {nome_v:<10} n={len(rend):<4} win={(rend>0).mean()*100:5.1f}%   "
                          f"medio={rend.mean():+7.2f}%   mediana={np.median(rend):+7.2f}%")
        a = [e["rend52"] for e in sett_eventi if e["struttura_ok"] == 1 and e["rv_w"] >= 1.5]
        b = [e["rend52"] for e in sett_eventi if e["struttura_ok"] == 1 and e["rv_w"] < 1.5]
        tW, pW = welch(a, b)
        print(f"\n   A parità di struttura (settimanale), vol alto vs basso → "
              f"{np.nanmean(a):+.2f}% (n={len(a)}) vs {np.nanmean(b):+.2f}% (n={len(b)})  t={tW:.2f}  p={pW:.4f}")

        # controllo con finestre NON sovrapposte: la regola va applicata DENTRO
        # ogni gruppo confrontato (max 1 evento per titolo ogni ~52 settimane),
        # altrimenti si scartano eventi a caso e si confrontano campioni sbilanciati
        def _nonov(evs, giorni=364):
            per_titolo = {}
            for e in evs:
                per_titolo.setdefault(e["titolo"], []).append(e)
            tenuti = []
            for t, gruppo in per_titolo.items():
                gruppo.sort(key=lambda x: x["data"])
                ultimo = None
                for e in gruppo:
                    d = pd.Timestamp(e["data"])
                    if ultimo is None or (d - ultimo).days >= giorni:
                        tenuti.append(e)
                        ultimo = d
            return tenuti
        a2 = [e["rend52"] for e in _nonov([e for e in sett_eventi
                                           if e["struttura_ok"] == 1 and e["rv_w"] >= 1.5])]
        b2 = [e["rend52"] for e in _nonov([e for e in sett_eventi
                                           if e["struttura_ok"] == 1 and e["rv_w"] < 1.5])]
        t2, p2 = welch(a2, b2)
        print(f"   NON sovrapposte  (max 1 evento/anno/titolo): vol alto vs basso → "
              f"{np.nanmean(a2):+.2f}% (n={len(a2)}) vs {np.nanmean(b2):+.2f}% (n={len(b2)})  t={t2:.2f}  p={p2:.4f}")
        # e la struttura da sola, non sovrapposta?
        s1 = [e["rend52"] for e in _nonov([e for e in sett_eventi if e["struttura_ok"] == 1])]
        s0 = [e["rend52"] for e in _nonov([e for e in sett_eventi if e["struttura_ok"] == 0])]
        t3, p3 = welch(s1, s0)
        print(f"   NON sovrapposte: struttura OK vs NO → {np.nanmean(s1):+.2f}% (n={len(s1)}) vs "
              f"{np.nanmean(s0):+.2f}% (n={len(s0)})  t={t3:.2f}  p={p3:.4f}")
        risultato["H_settimanale"] = {
            "n": len(sett_eventi),
            "vol_alto_vs_basso_in_struttura": [round(tW, 2), round(pW, 4)],
            "non_sovrapposto_vol": [round(t2, 2), round(p2, 4)],
            "non_sovrapposto_struttura": [round(t3, 2), round(p3, 4)],
        }

    # ---------------------------------------------------------------- salvataggi
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "volume_lab.json"), "w", encoding="utf-8") as f:
        json.dump(risultato, f, ensure_ascii=False, indent=2, default=str)
    righe_csv = []
    for chiave, titolo in (("A_dose_risposta", "A) buckets"), ):
        pass
    pd.concat([tabA.assign(sezione="A"), tabB.assign(sezione="B"),
               (tabC.assign(sezione="C") if not tabC.empty else pd.DataFrame()),
               tabD.assign(sezione="D"), tabE.assign(sezione="E"),
               tabF.assign(sezione="F"), tabG.assign(sezione="G")], ignore_index=True) \
        .to_csv(os.path.join(OUT_DIR, "volume_lab_riepilogo.csv"), sep=";", decimal=",",
                encoding="utf-8-sig", index=False)
    print(f"\nSalvati: {os.path.join(OUT_DIR, 'volume_lab.json')} e volume_lab_riepilogo.csv")
    return 0


def _ok(cond, e):
    try:
        v = cond(e)
        return bool(v) if not isinstance(v, float) else bool(np.isfinite(v) and v)
    except Exception:
        return False


if __name__ == "__main__":
    sys.exit(main())
