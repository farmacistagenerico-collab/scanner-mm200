#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CONTROLLO DI ROBUSTEZZA — finestre non sovrapposte
==================================================

PERCHÉ QUESTO MODULO
--------------------
Le finestre forward di 250 sedute (o 52 settimane) si sovrappongono tra eventi
ravvicinati dello stesso titolo: lo stesso rally viene contato molte volte.
I campioni quindi NON sono indipendenti, i t-test sono gonfiati e un p-value
può sembrare significativo anche quando l'effetto non esiste.

Questo modulo rifà i test principali tenendo UN SOLO evento per titolo per
anno (finestre di fatto non sovrapposte):

  1) GIORNALIERO — rotture MM200:
       struttura allineata (MM200 in salita e MM50>MM200) vs no
       volume alto (≥1,5x) vs basso, dentro e fuori la struttura buona
  2) SETTIMANALE — la combinazione "tutti i filtri" della ricerca precedente
     (vol ≥1,5x + MM in salita + media breve sopra + conferma mensile):
     versione sovrapposta (come nella ricerca precedente) e versione
     non sovrapposta (il test pulito).

Uso:
    python3 controllo_robustezza.py --dal 2005-01-01
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

import titoli_italiani as tu                        # noqa: E402
import volume_lab as vl                             # noqa: E402
from backtest import segnali_titolo, baseline as bt_baseline, ORIZZONTI_SETT  # noqa: E402

OUT_DIR = os.path.join(BASE_DIR, "output")


def non_sovrapposti(eventi, giorni=365, chiave_data="data"):
    """Tiene un solo evento per titolo ogni `giorni` (separa le finestre forward)."""
    per_titolo = {}
    for e in eventi:
        per_titolo.setdefault(e["titolo"], []).append(e)
    tenuti = []
    for t, gruppo in per_titolo.items():
        gruppo.sort(key=lambda x: x[chiave_data])
        ultimo = None
        for e in gruppo:
            d = pd.Timestamp(e[chiave_data])
            if ultimo is None or (d - ultimo).days >= giorni:
                tenuti.append(e)
                ultimo = d
    return tenuti


def stat(nome, sel, mu, h=250, chiave="rend"):
    r = vl._pulito([e[chiave].get(h, np.nan) if isinstance(e.get(chiave), dict) else np.nan
                    for e in sel]) if chiave == "rend" else \
        vl._pulito([e[chiave] for e in sel])
    if len(r) < 5:
        return {"gruppo": nome, "n": len(r)}
    t, p = vl.t_vs_base(r, mu)
    return {"gruppo": nome, "n": len(r), "win": round(float((r > 0).mean() * 100), 1),
            "medio": round(float(r.mean()), 2), "mediana": round(float(np.median(r)), 2),
            "t": round(t, 2) if np.isfinite(t) else None,
            "p": round(p, 4) if np.isfinite(p) else None}


def stampa(righe, titolo):
    print(f"\n{titolo}")
    print("-" * 96)
    print(f"{'gruppo':<44}{'n':>7}{'win%':>7}{'medio%':>9}{'mediana%':>10}{'t':>7}{'p':>9}")
    print("-" * 96)
    for r in righe:
        if r.get("n", 0) < 5:
            print(f"{r['gruppo']:<44}{r.get('n', 0):>7}   (campione insufficiente)")
            continue
        t = f"{r['t']:.2f}" if r["t"] is not None else "—"
        p = f"{r['p']:.4f}" if r["p"] is not None else "—"
        print(f"{r['gruppo']:<44}{r['n']:>7}{r['win']:>7.1f}{r['medio']:>9.2f}"
              f"{r['mediana']:>10.2f}{t:>7}{p:>9}")


def welch_riga(nome, a, b):
    t, p = vl.welch(a, b)
    if not np.isfinite(t):
        return f"   {nome:<52} campioni insufficienti"
    return (f"   {nome:<52} {np.nanmean(a):+7.2f}% (n={len(a)})  vs  "
            f"{np.nanmean(b):+7.2f}% (n={len(b)})   t={t:+.2f}  p={p:.4f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dal", default="2005-01-01")
    args = ap.parse_args()

    import yfinance as yf

    tickers = tu.solo_ticker()
    print(f"Scarico la storia completa di {len(tickers)} titoli...")
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

    risultato = {}

    # ==================================================================
    # PARTE 1 — GIORNALIERO
    # ==================================================================
    eventi = []
    for t, df in dati.items():
        for e in vl.eventi(df, dal=args.dal):
            e["titolo"] = t
            eventi.append(e)
    base = []
    for t, df in dati.items():
        base.extend(vl.baseline(df, dal=args.dal)[250].tolist())
    mu = float(np.mean(base))

    nov = non_sovrapposti(eventi, 365)
    print(f"\nEventi giornalieri: {len(eventi)} totali → {len(nov)} non sovrapposti "
          f"(max 1 per titolo/anno).  Baseline 250 sedute: {mu:+.2f}%")

    for etichetta, insieme in (("SOVRAPPOSTE (come nei test precedenti)", eventi),
                               ("NON SOVRAPPOSTE (test pulito)", nov)):
        righe = [
            stat("tutte le rotture", insieme, mu),
            stat("struttura OK", [e for e in insieme if e["struttura_ok"] == 1], mu),
            stat("struttura NO", [e for e in insieme if e["struttura_ok"] == 0], mu),
            stat("struttura OK + vol ≥1,5x", [e for e in insieme
                                              if e["struttura_ok"] == 1 and e["rv0"] >= 1.5], mu),
            stat("struttura OK + vol <1,5x", [e for e in insieme
                                              if e["struttura_ok"] == 1 and e["rv0"] < 1.5], mu),
        ]
        stampa(righe, f"GIORNALIERO — {etichetta}")
        a = [e["rend"][250] for e in insieme if e["struttura_ok"] == 1]
        b = [e["rend"][250] for e in insieme if e["struttura_ok"] == 0]
        c = [e["rend"][250] for e in insieme if e["struttura_ok"] == 1 and e["rv0"] >= 1.5]
        d = [e["rend"][250] for e in insieme if e["struttura_ok"] == 1 and e["rv0"] < 1.5]
        print(welch_riga("struttura OK vs NO:", a, b))
        print(welch_riga("entro struttura OK: volume alto vs basso:", c, d))
        risultato["giornaliero_" + ("sovrapposte" if insieme is eventi else "non_sovrapposte")] = {
            "n": len(insieme),
            "righe": righe,
            "welch_struttura": [round(v, 4) for v in vl.welch(a, b)],
            "welch_volume_in_struttura": [round(v, 4) for v in vl.welch(c, d)],
        }

    # ==================================================================
    # PARTE 2 — SETTIMANALE: la combinazione "tutti i filtri" di prima
    # ==================================================================
    sett = []
    for t, df in dati.items():
        for s in segnali_titolo(df, timeframe="settimanale", dal=args.dal):
            s["titolo"] = t
            sett.append(s)
    base_w = []
    for t, df in dati.items():
        base_w.extend(list(bt_baseline(df, ORIZZONTI_SETT, timeframe="settimanale", dal=args.dal)[52]))
    mu_w = float(np.mean(base_w))

    combo3 = [s for s in sett if (s["vol_ratio"] or 0) >= 1.5 and (s["slope"] or -99) > 0
              and s["mm_breve_sopra"] is True]
    combo4 = [s for s in combo3 if s["weekly_ok"] is True]
    nov3 = non_sovrapposti(combo3, 364)
    nov4 = non_sovrapposti(combo4, 364)

    print(f"\n\nEventi settimanali: {len(sett)} totali.  Baseline 52 settimane: {mu_w:+.2f}%")
    print(f"Combo 3 filtri: {len(combo3)} eventi → {len(nov3)} non sovrapposti")
    print(f"Combo 4 filtri (tutti): {len(combo4)} eventi → {len(nov4)} non sovrapposti")

    def s_stat(nome, sel):
        r = vl._pulito([s["fwd"].get(52, np.nan) for s in sel])
        if len(r) < 5:
            return {"gruppo": nome, "n": len(r)}
        t, p = vl.t_vs_base(r, mu_w)
        return {"gruppo": nome, "n": len(r), "win": round(float((r > 0).mean() * 100), 1),
                "medio": round(float(r.mean()), 2), "mediana": round(float(np.median(r)), 2),
                "t": round(t, 2) if np.isfinite(t) else None,
                "p": round(p, 4) if np.isfinite(p) else None}

    righe = [
        s_stat("tutte le rotture settimanali", sett),
        s_stat("combo 3 filtri — SOVRAPPOSTA (come prima)", combo3),
        s_stat("combo 3 filtri — NON sovrapposta", nov3),
        s_stat("combo 4 filtri — SOVRAPPOSTA (come prima)", combo4),
        s_stat("combo 4 filtri — NON sovrapposta", nov4),
    ]
    stampa(righe, "SETTIMANALE — effetto della sovrapposizione delle finestre")
    print("\n   (rendimenti a 52 settimane; stessa baseline per tutte le righe)")

    risultato["settimanale"] = {"n_eventi": len(sett), "baseline": round(mu_w, 2), "righe": righe}

    # ---- stabilità: due metà del campione + concentrazione per titolo ----
    from collections import Counter
    print("\n\nSTABILITÀ DELLA COMBO (rendimenti a 52 settimane)\n")
    righe_st = []
    for nome, sel in (("combo 3 filtri", combo3), ("combo 4 filtri (tutti)", combo4)):
        for epoca, sub in (("2005-2014", [x for x in sel if int(x["data"][:4]) <= 2014]),
                           ("2015-2026", [x for x in sel if int(x["data"][:4]) >= 2015])):
            r = vl._pulito([x["fwd"].get(52, np.nan) for x in sub])
            if len(r) >= 5:
                t, p = vl.t_vs_base(r, mu_w)
                righe_st.append({"gruppo": f"{nome} | {epoca}", "n": len(r),
                                 "win": round(float((r > 0).mean() * 100), 1),
                                 "medio": round(float(r.mean()), 2),
                                 "t": round(t, 2), "p": round(p, 4)})
                print(f"   {nome:<24} {epoca}   n={len(r):<3} win={(r>0).mean()*100:5.1f}%  "
                      f"medio={r.mean():+7.2f}%   t={t:+.2f}  p={p:.4f}")
    print("\n   Combo 4 filtri, per anno (n / medio% / win%):")
    per_anno = {}
    for x in combo4:
        r = x["fwd"].get(52, np.nan)
        if np.isfinite(r):
            per_anno.setdefault(x["data"][:4], []).append(r)
    for anno in sorted(per_anno):
        r = np.array(per_anno[anno])
        print(f"      {anno}: n={len(r):<3} medio={r.mean():+7.2f}%  win={(r>0).mean()*100:5.1f}%")
    conteggio = Counter(x["titolo"] for x in combo4)
    print(f"\n   Titoli più rappresentati nella combo 4 filtri: {conteggio.most_common(6)}")
    for escluso, _volte in conteggio.most_common(3):
        r = vl._pulito([x["fwd"].get(52, np.nan) for x in combo4 if x["titolo"] != escluso])
        t, p = vl.t_vs_base(r, mu_w)
        print(f"   escludendo {escluso:<10} n={len(r):<3} medio={r.mean():+7.2f}%  "
              f"win={(r>0).mean()*100:5.1f}%   t={t:+.2f}  p={p:.4f}")
    risultato["stabilita_combo"] = {"righe": righe_st, "top_titoli": conteggio.most_common(6)}

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "controllo_robustezza.json"), "w", encoding="utf-8") as f:
        json.dump(risultato, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nSalvato: {os.path.join(OUT_DIR, 'controllo_robustezza.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
