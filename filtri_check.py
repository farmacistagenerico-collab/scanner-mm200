#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FILTRI CHECK — il filtro batte la baseline dello STESSO stato?
==============================================================

Problema: se in certi stati di mercato (es. MIB sotto la MM200) TUTTI i periodi
rendono di più, allora un "filtro" che seleziona quello stato non dice nulla
sulla qualità della rottura: sta solo facendo market timing.

Questo modulo confronta, per ogni stato:
    (a) il rendimento medio a 250 sedute di TUTTI i periodi in quello stato
        (baseline condizionata)
    (b) il rendimento medio delle ROTTURE in quello stesso stato
Se (b) - (a) ≈ 0, il filtro è solo market timing. Se (b) - (a) > 0 in modo
consistente, il filtro ha informazione specifica sulla rottura.

Uso:
    python3 filtri_check.py --dal 2005-01-01
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
import volume_lab as vl       # noqa: E402
import filtri_lab as fl       # noqa: E402

OUT_DIR = os.path.join(BASE_DIR, "output")
H = 250


def stato_riga(contesto, data):
    try:
        if data in contesto.index:
            return contesto.loc[data]
        i = contesto.index.searchsorted(data, side="right") - 1
        return contesto.iloc[i] if i >= 0 else None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dal", default="2005-01-01")
    args = ap.parse_args()

    import yfinance as yf

    tickers = tu.solo_ticker()
    print("Scarico la storia completa dei titoli + indice...")
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

    closes = pd.DataFrame({t: d["Close"] for t, d in dati.items()})
    mm_univ = closes.rolling(200, min_periods=150).mean()
    valid = closes.notna() & mm_univ.notna()
    breadth = ((closes > mm_univ) & valid).sum(axis=1) / valid.sum(axis=1).replace(0, np.nan)

    try:
        idx = yf.download("FTSEMIB.MI", period="max", interval="1d", auto_adjust=True, progress=False)
        if isinstance(idx.columns, pd.MultiIndex):
            idx.columns = idx.columns.get_level_values(0)
        ic = idx["Close"].dropna()
        i_mm = ind.sma(ic, 200)
        mib_above, mib_slope = (ic > i_mm), (i_mm / i_mm.shift(20) - 1) * 100
    except Exception:
        ew = closes.pct_change().mean(axis=1).fillna(0)
        ic = (1 + ew).cumprod()
        i_mm = ind.sma(ic, 200)
        mib_above, mib_slope = (ic > i_mm), (i_mm / i_mm.shift(20) - 1) * 100

    contesto = pd.DataFrame(index=closes.index)
    contesto["breadth"] = breadth
    contesto["mib_above"] = mib_above.reindex(closes.index, method="ffill")
    contesto["mib_slope"] = mib_slope.reindex(closes.index, method="ffill")
    ret12_all = closes / closes.shift(252) - 1
    rank_ret12 = ret12_all.rank(axis=1, pct=True)

    # ---------------- baseline condizionata: TUTTI i periodi ---------------- #
    base = {"mib_sopra": [], "mib_sotto": [],
            "recovery": [], "vicino_max": [], "rs_alto": [], "rs_basso": []}
    for t, df in dati.items():
        c = df["Close"]
        if args.dal:
            c = c[c.index >= pd.Timestamp(args.dal)]
        if len(c) < 300:
            continue
        fwd = (c.shift(-H) / c - 1) * 100
        hh = c.rolling(252, min_periods=150).max()
        dd = (c / hh - 1) * 100
        for i, (data, x) in enumerate(fwd.items()):
            if not np.isfinite(x):
                continue
            st = stato_riga(contesto, data)
            if st is None:
                continue
            if st["mib_above"] is True or st["mib_above"] == True:  # noqa: E712
                base["mib_sopra"].append(float(x))
            elif st["mib_above"] is False or st["mib_above"] == False:  # noqa: E712
                base["mib_sotto"].append(float(x))
            d = dd.loc[data] if data in dd.index else np.nan
            if np.isfinite(d):
                (base["recovery"] if d < -20 else base["vicino_max"]).append(float(x))
            rk = rank_ret12.at[data, t] if (data in rank_ret12.index and t in rank_ret12.columns) else np.nan
            if np.isfinite(rk):
                (base["rs_alto"] if rk >= 0.5 else base["rs_basso"]).append(float(x))

    # ---------------- rotture, per stato ------------------------------------ #
    eventi = []
    for t, df in dati.items():
        eventi += fl.eventi_titolo(df, contesto, rank_ret12, dal=args.dal, ticker=t)

    def bw(sel, chiave):
        if chiave == "rend":
            return vl._pulito([e["rend"].get(H, np.nan) for e in sel])
        return vl._pulito([e[chiave] for e in sel])

    print(f"\nPeriodi 'qualunque' analizzati: {sum(len(v) for v in base.values())//2:,} "
          f"(conteggi sovrapposti tra stati) | rotture: {len(eventi)}\n")
    print("=" * 118)
    print("ROTTURA vs BASELINE DELLO STESSO STATO (rendimento medio a 250 sedute)")
    print("=" * 118)
    print(f"{'stato':<44}{'baseline':>12}{'rotture':>12}{'excess':>10}{'n_base':>12}{'n_rott':>8}")

    def riga(nome, base_vals, chiave_evento, cond):
        sel = [e for e in eventi if cond(e)]
        r = bw(sel, chiave_evento)
        b = np.array(base_vals, dtype=float)
        if len(r) < 8 or len(b) < 8:
            print(f"{nome:<44}   (campione insufficiente)")
            return None
        excess = r.mean() - b.mean()
        print(f"{nome:<44}{b.mean():>12.2f}{r.mean():>12.2f}{excess:>10.2f}{len(b):>12,}{len(r):>8}")
        return {"stato": nome, "baseline": round(float(b.mean()), 2), "rotture": round(float(r.mean()), 2),
                "excess": round(float(excess), 2), "n_base": int(len(b)), "n_rotture": int(len(r))}

    out = []
    out.append(riga("MIB sopra la MM200", base["mib_sopra"], "rend",
                    lambda e: e["mib_above"] is True))
    out.append(riga("MIB sotto la MM200", base["mib_sotto"], "rend",
                    lambda e: e["mib_above"] is False))
    out.append(riga("azioni in deep recovery (dd < -20%)", base["recovery"], "rend",
                    lambda e: (e["dd"] or 0) < -20))
    out.append(riga("azioni vicine ai massimi (dd > -15%)", base["vicino_max"], "rend",
                    lambda e: (e["dd"] or -99) > -15))
    out.append(riga("forza relativa sopra la mediana", base["rs_alto"], "rend",
                    lambda e: (e["rs_rank"] or -1) >= 0.5))
    out.append(riga("forza relativa sotto la mediana", base["rs_basso"], "rend",
                    lambda e: (e["rs_rank"] or -1) < 0.5))

    print("\n  lettura: 'excess' = quanto la rottura rende IN PIÙ (o in meno) di un periodo")
    print("  qualunque trascorso nel medesimo stato. Excess ≈ 0 → il filtro è solo market timing.")

    # --- per la combinazione vincitrice, dettaglio per anno -------------------
    print("\n" + "=" * 118)
    print("DETTAGLIO: rotture in deep recovery, per anno (rendimento a 250 sedute)")
    print("=" * 118)
    rec = [e for e in eventi if (e["dd"] or 0) < -20]
    per_anno = {}
    for e in rec:
        r = e["rend"].get(H, np.nan)
        if np.isfinite(r):
            per_anno.setdefault(e["anno"], []).append(r)
    for a in sorted(per_anno):
        r = np.array(per_anno[a])
        print(f"   {a}: n={len(r):<3} medio={r.mean():+8.2f}%  win={(r>0).mean()*100:5.1f}%")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "filtri_check.json"), "w", encoding="utf-8") as fh:
        json.dump({"righe": out, "per_anno_recovery": {str(k): [len(v), round(float(np.mean(v)), 2)]
                                                       for k, v in sorted(per_anno.items())}},
                  fh, ensure_ascii=False, indent=2)
    print(f"\nSalvato: {os.path.join(OUT_DIR, 'filtri_check.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
