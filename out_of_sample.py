#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OUT-OF-SAMPLE — il filtro deep recovery è una vera inefficienza o un artefatto?
===============================================================================

Protocollo (fissato PRIMA di guardare i risultati):

  IS  (in-sample)     : 2005-2015 — qui si calibra tutto
  OOS (out-of-sample) : 2016-2026 — qui si verifica, senza ri-ottimizzare nulla

  TEST A — Filtro deep recovery, calibrato e dichiarato sull'IS, verificato
           sull'OOS: rendimento, excess vs baseline condizionata allo stato,
           tasso di falso breakout, Welch deep vs altre rotture, versione non
           sovrapposta, dettaglio per anno.

  TEST B — Punteggio "calibrato onestamente": ogni componente riceve +1/-1
           punto SOLO se ha effetto significativo (p<0.10) nell'IS; il
           punteggio così costruito viene poi applicato all'OOS per vedere se
           ordina davvero i risultati (bucket e Welch alto vs basso).

  TEST C — VALIDAZIONE ESTERNA: gli stessi filtri (deep recovery) su ~40
           titoli di Germania, Francia, Spagna, Paesi Bassi, Belgio e Regno
           Unito, mercati su cui non è stata fatta NESSUNA calibrazione.
           Se l'effetto esiste solo in Italia, è sospetto; se appare anche
           altrove, è più plausibile che sia reale.

Uso:
    python3 out_of_sample.py
"""
from __future__ import annotations

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
DATA_IS_FINE = 2015          # IS = 2005..2015
DATA_OOS_INIZIO = 2016       # OOS = 2016..oggi

# ~40 large cap europee (DE, FR, ES, NL, BE, UK): validazione esterna
UNIVERSO_EU = [
    "SAP.DE", "SIE.DE", "ALV.DE", "BAYN.DE", "BMW.DE", "MBG.DE", "DTE.DE", "BAS.DE",
    "MUV2.DE", "RWE.DE", "HEN3.DE", "FRE.DE", "IFX.DE",
    "AIR.PA", "MC.PA", "OR.PA", "SAN.PA", "BNP.PA", "AI.PA", "SU.PA", "CS.PA",
    "DG.PA", "KER.PA", "RI.PA", "EL.PA", "VIE.PA",
    "ITX.MC", "SAN.MC", "BBVA.MC", "IBE.MC", "TEF.MC", "REP.MC", "FER.MC",
    "ASML.AS", "AD.AS", "INGA.AS", "PHIA.AS", "HEIA.AS", "ABN.AS",
    "ABI.BR", "UCB.BR", "KBC.BR", "SOLB.BR",
    "SHEL.L", "AZN.L", "HSBA.L", "ULVR.L", "BP.L", "GSK.L", "RIO.L", "BATS.L",
    "LLOY.L", "BARC.L", "DGE.L", "NG.L", "VOD.L",
]


# ---------------------------------------------------------------------------
# helper condivisi
# ---------------------------------------------------------------------------

def pulito(x):
    return vl._pulito(x)


def wilcoxon_t(x, y):
    return vl.welch(x, y)


def basi_condizionate(dati, dal, fino=None):
    """
    Baseline condizionata allo stato: per ogni titolo e ogni seduta raccoglie il
    rendimento forward a 250 sedute, etichettato per stato (deep recovery,
    vicino ai massimi, altro).
    """
    out = {"deep_recovery": [], "vicino_max": [], "altro": [], "tutte": []}
    for t, df in dati.items():
        c = df["Close"]
        if dal:
            c = c[c.index >= pd.Timestamp(dal)]
        if fino:
            c = c[c.index <= pd.Timestamp(f"{fino}-12-31")]
        if len(c) < 300:
            continue
        fwd = (c.shift(-H) / c - 1) * 100
        hh = c.rolling(252, min_periods=150).max()
        dd = (c / hh - 1) * 100
        frame = pd.DataFrame({"fwd": fwd, "dd": dd}).dropna()
        if frame.empty:
            continue
        out["tutte"] += frame["fwd"].tolist()
        out["deep_recovery"] += frame.loc[frame["dd"] < -20, "fwd"].tolist()
        out["vicino_max"] += frame.loc[frame["dd"] > -15, "fwd"].tolist()
        out["altro"] += frame.loc[(frame["dd"] >= -20) & (frame["dd"] <= -15), "fwd"].tolist()
    return out


def blocco(nome, sel, base, chiave_rend="rend"):
    """Statistiche di un gruppo di eventi confrontate con la baseline di stato."""
    r = pulito([e[chiave_rend].get(H, np.nan) for e in sel])
    if len(r) < 8:
        return None
    b = np.array(base, dtype=float)
    t_tot, p_tot = vl.t_vs_base(r, b.mean()) if len(b) >= 8 else (np.nan, np.nan)
    falso = np.mean([1 if e["fallito21"] else 0 for e in sel]) * 100
    return {
        "gruppo": nome, "n": len(r), "win": round(float((r > 0).mean() * 100), 1),
        "medio": round(float(r.mean()), 2), "mediana": round(float(np.median(r)), 2),
        "mae": round(float(np.nanmean([e["mae63"] for e in sel])), 2),
        "baseline": round(float(b.mean()), 2),
        "excess": round(float(r.mean() - b.mean()), 2),
        "falso21": round(float(falso), 1),
        "t_vs_base": round(t_tot, 2) if np.isfinite(t_tot) else None,
        "p_vs_base": round(p_tot, 4) if np.isfinite(p_tot) else None,
    }


def stampa_tabella(righe, titolo):
    print(f"\n{titolo}")
    print("-" * 118)
    print(f"{'gruppo':<34}{'n':>6}{'win%':>7}{'medio%':>9}{'mediana%':>9}{'MAE63':>8}"
          f"{'base%':>8}{'excess':>8}{'falso21%':>10}{'t':>7}{'p':>9}")
    print("-" * 118)
    for r in righe:
        if not r:
            continue
        t = f"{r['t_vs_base']:.2f}" if r["t_vs_base"] is not None else "—"
        p = f"{r['p_vs_base']:.4f}" if r["p_vs_base"] is not None else "—"
        print(f"{r['gruppo'][:33]:<34}{r['n']:>6}{r['win']:>7.1f}{r['medio']:>9.2f}"
              f"{r['mediana']:>9.2f}{r['mae']:>8.2f}{r['baseline']:>8.2f}{r['excess']:>8.2f}"
              f"{r['falso21']:>10.1f}{t:>7}{p:>9}")


def non_sovrapposti(eventi, giorni=365):
    per_titolo = {}
    for e in eventi:
        per_titolo.setdefault(e["titolo"], []).append(e)
    tenuti = []
    for t, g in per_titolo.items():
        g.sort(key=lambda x: x["data"])
        ultimo = None
        for e in g:
            d = pd.Timestamp(e["data"])
            if ultimo is None or (d - ultimo).days >= giorni:
                tenuti.append(e)
                ultimo = d
    return tenuti


def _ok(cond, e):
    try:
        return bool(cond(e))
    except Exception:
        return False


def eventi_universo(dati, contesto, rank_ret12):
    ev = []
    for t, df in dati.items():
        ev += fl.eventi_titolo(df, contesto, rank_ret12, ticker=t)
    return ev


# ---------------------------------------------------------------------------
# TEST B — punteggio calibrato su IS
# ---------------------------------------------------------------------------

COMPONENTI = {
    "deep recovery (dd<-20%)": lambda e: (e["dd"] or 0) < -20,
    "vicino ai massimi (dd>-15%)": lambda e: (e["dd"] or -99) > -15,
    "MM200 in salita (20g>0)": lambda e: (e["slope20"] or -99) > 0,
    "MM50 sopra MM200": lambda e: e["mm50_sopra"] is True,
    "rendimento 12m > 0": lambda e: (e["ret12"] or -99) > 0,
    "forza relativa ≥50° pct": lambda e: (e["rs_rank"] or -1) >= 0.5,
    "RSI 45-75": lambda e: 45 <= (e["rsi"] or 0) <= 75,
    "volume ≥1,5x": lambda e: (e.get("rv0") or 0) >= 1.5,
    "struttura settimanale OK": lambda e: e.get("weekly_ok") == 1.0,
    "bassa volatilità (ATR <50° pct)": lambda e: (e["atr_pctile"] or 999) < 50,
    "nessun incrocio da 6+ mesi": lambda e: (e.get("giorni_da_incrocio") or 0) >= 126,
}


def calibra(componenti, eventi_is):
    """Assegna +1/-1 punto per componente significativa (p<0.10) nell'IS."""
    pesi = {}
    dettaglio = []
    for nome, f in componenti.items():
        si = [e for e in eventi_is if _ok(f, e)]
        no = [e for e in eventi_is if not _ok(f, e)]
        r_si = pulito([e["rend"].get(H, np.nan) for e in si])
        r_no = pulito([e["rend"].get(H, np.nan) for e in no])
        if len(r_si) < 10 or len(r_no) < 10:
            pesi[nome] = 0
            continue
        t, p = vl.welch(r_si, r_no)
        delta = float(r_si.mean() - r_no.mean())
        punto = 0
        if np.isfinite(p) and p < 0.10:
            punto = 1 if delta > 0 else -1
        pesi[nome] = punto
        dettaglio.append({"componente": nome, "n_si": len(r_si), "delta_is": round(delta, 2),
                          "p_is": round(float(p), 4) if np.isfinite(p) else None, "punti": punto})
    return pesi, dettaglio


# ---------------------------------------------------------------------------

def main():
    import yfinance as yf

    tickers = tu.solo_ticker()
    print(f"Scarico {len(tickers)} titoli italiani + {len(UNIVERSO_EU)} titoli europei...")
    raw = yf.download(tickers + UNIVERSO_EU, period="max", interval="1d", auto_adjust=True,
                      group_by="ticker", threads=True, progress=False)

    def carica(lista):
        d = {}
        for t in lista:
            try:
                df = raw[t].dropna(how="all").dropna(subset=["Close"])
            except Exception:
                continue
            if len(df) > 500:
                d[t] = df
        return d

    dati_it = carica(tickers)
    dati_eu = carica(UNIVERSO_EU)
    print(f"  Italia: {len(dati_it)} titoli | Europa: {len(dati_eu)} titoli")

    def contesto_di(dati):
        closes = pd.DataFrame({t: d["Close"] for t, d in dati.items()})
        mm = closes.rolling(200, min_periods=150).mean()
        valid = closes.notna() & mm.notna()
        breadth = ((closes > mm) & valid).sum(axis=1) / valid.sum(axis=1).replace(0, np.nan)
        ew = closes.pct_change().mean(axis=1).fillna(0)
        ic = (1 + ew).cumprod()
        i_mm = ind.sma(ic, 200)
        contesto = pd.DataFrame(index=closes.index)
        contesto["breadth"] = breadth
        contesto["mib_above"] = (ic > i_mm)
        contesto["mib_slope"] = (i_mm / i_mm.shift(20) - 1) * 100
        rank = (closes / closes.shift(252) - 1).rank(axis=1, pct=True)
        return contesto, rank

    contesto_it, rank_it = contesto_di(dati_it)
    contesto_eu, rank_eu = contesto_di(dati_eu)

    eventi = [e for e in eventi_universo(dati_it, contesto_it, rank_it) if e["anno"] >= 2005]
    print(f"\nRotture MM200 (Italia, dal 2005): {len(eventi)}")
    risultato = {"n_eventi_italia": len(eventi)}

    # ======================================================================
    # TEST A — deep recovery IS vs OOS
    # ======================================================================
    print("\n" + "=" * 118)
    print("TEST A — FILTRO DEEP RECOVERY: 2005-2015 (in-sample) vs 2016-2026 (out-of-sample)")
    print("=" * 118)

    base_is = basi_condizionate(dati_it, "2005-01-01", DATA_IS_FINE)
    base_oos = basi_condizionate(dati_it, f"{DATA_OOS_INIZIO}-01-01", None)
    print(f"  baseline IS  — tutte: {np.mean(base_is['tutte']):+.2f}% | "
          f"deep recovery: {np.mean(base_is['deep_recovery']):+.2f}% | "
          f"vicino max: {np.mean(base_is['vicino_max']):+.2f}%")
    print(f"  baseline OOS — tutte: {np.mean(base_oos['tutte']):+.2f}% | "
          f"deep recovery: {np.mean(base_oos['deep_recovery']):+.2f}% | "
          f"vicino max: {np.mean(base_oos['vicino_max']):+.2f}%")

    for etichetta, da, a, base in (("IN-SAMPLE 2005-2015", 2005, DATA_IS_FINE, base_is),
                                   ("OUT-OF-SAMPLE 2016-2026", DATA_OOS_INIZIO, 2100, base_oos)):
        sub = [e for e in eventi if da <= e["anno"] <= a]
        righe = [
            blocco("rotture in DEEP RECOVERY (dd<-20%)",
                   [e for e in sub if (e["dd"] or 0) < -20], base["deep_recovery"]),
            blocco("rotture VICINO AI MASSIMI (dd>-15%)",
                   [e for e in sub if (e["dd"] or -99) > -15], base["vicino_max"]),
            blocco("tutte le rotture (controllo)",
                   sub, base["tutte"]),
        ]
        stampa_tabella(righe, f"{etichetta} — rendimento a 250 sedute")
        r_dr = [e["rend"].get(H, np.nan) for e in sub if (e["dd"] or 0) < -20]
        r_no = [e["rend"].get(H, np.nan) for e in sub if (e["dd"] or 0) >= -20]
        tW, pW = vl.welch(r_dr, r_no)
        print(f"   Welch deep recovery vs altre rotture: t={tW:+.2f}  p={pW:.4f}")
        dr_nov = non_sovrapposti([e for e in sub if (e["dd"] or 0) < -20])
        no_nov = non_sovrapposti([e for e in sub if (e["dd"] or 0) >= -20])
        a1 = pulito([e["rend"].get(H, np.nan) for e in dr_nov])
        b1 = pulito([e["rend"].get(H, np.nan) for e in no_nov])
        t2, p2 = vl.welch(a1, b1)
        print(f"   Non sovrapposte: deep {a1.mean():+.2f}% (n={len(a1)}) vs altre {b1.mean():+.2f}% "
              f"(n={len(b1)})  t={t2:+.2f}  p={p2:.4f}")
        risultato[f"A_{'is' if da == 2005 else 'oos'}"] = {
            "righe": [r for r in righe if r],
            "welch_deep_vs_altre": [round(tW, 2), round(pW, 4)],
            "welch_non_sovrapposte": [round(t2, 2), round(p2, 4), len(a1), len(b1)],
        }

    # dettaglio per anno OOS
    print("\nDettaglio deep recovery, per anno (OOS):")
    oos_dr = [e for e in eventi if e["anno"] >= DATA_OOS_INIZIO and (e["dd"] or 0) < -20]
    per_anno = {}
    for e in oos_dr:
        r = e["rend"].get(H, np.nan)
        if np.isfinite(r):
            per_anno.setdefault(e["anno"], []).append(r)
    for a in sorted(per_anno):
        r = np.array(per_anno[a])
        print(f"   {a}: n={len(r):<3} medio={r.mean():+8.2f}%  win={(r>0).mean()*100:5.1f}%")

    # ======================================================================
    # TEST B — punteggio calibrato su IS, applicato su OOS
    # ======================================================================
    print("\n\n" + "=" * 118)
    print("TEST B — PUNTEGGIO: componenti selezionate e pesate SOLO sul 2005-2015, poi applicate al 2016-2026")
    print("=" * 118)

    def stato_evento(e):
        dd = e["dd"]
        if dd is None or not np.isfinite(dd if dd is not None else np.nan):
            return "altro"
        if dd < -20:
            return "deep_recovery"
        if dd > -15:
            return "vicino_max"
        return "altro"

    def base_di(stato, base):
        return float(np.mean(base.get(stato, base["tutte"])))

    for e in eventi:
        e["stato_evento"] = stato_evento(e)
        base = base_is if e["anno"] <= DATA_IS_FINE else base_oos
        r = e["rend"].get(H, np.nan)
        e["excess_periodo"] = (float(r) - base_di(e["stato_evento"], base)) if np.isfinite(r) else np.nan

    ev_is = [e for e in eventi if e["anno"] <= DATA_IS_FINE]
    ev_oos = [e for e in eventi if e["anno"] >= DATA_OOS_INIZIO]

    # --- B1: calibrazione INGENUA (rendimenti grezzi) — lezione metodologica ---
    pesi_grezzi, det_grezzi = calibra(COMPONENTI, ev_is)
    print("\nB1) Calibrazione INGENUA (confronto dei rendimenti grezzi) — per mostrare il tranello:")
    print(f"   {'componente':<34}{'delta IS':>10}{'p IS':>9}{'punti':>7}")
    for d in det_grezzi:
        print(f"   {d['componente'][:33]:<34}{d['delta_is']:>10.2f}"
              f"{(d['p_is'] if d['p_is'] is not None else float('nan')):>9.4f}{d['punti']:>7}")
    for e in eventi:
        e["score_grezzo"] = sum(p for nome, p in pesi_grezzi.items() if _ok(COMPONENTI[nome], e))
    a1g = pulito([e["rend"].get(H, np.nan) for e in ev_oos if e["score_grezzo"] > 0])
    b1g = pulito([e["rend"].get(H, np.nan) for e in ev_oos if e["score_grezzo"] <= 0])
    tG, pG = vl.welch(a1g, b1g)
    print(f"   → OOS: punteggio(grezzo) >0 vs ≤0: {a1g.mean():+.2f}% (n={len(a1g)}) vs "
          f"{b1g.mean():+.2f}% (n={len(b1g)})  t={tG:+.2f}  p={pG:.4f}")
    if pG < 0.10 and a1g.mean() < b1g.mean():
        giudizio = "ANTI-predittivo"
    elif pG < 0.10:
        giudizio = "positivo e significativo"
    else:
        giudizio = "positivo ma NON significativo (e sensibile al campione)"
    print(f"   → Esito B1: {giudizio}. Calibrare sui rendimenti grezzi mescola la composizione")
    print("     degli stati (recovery, massimi, trend) con la qualità della rottura: i punti finiscono")
    print("     nel posto sbagliato (nel primo run, con eventi pre-2005 inclusi, il punteggio si è")
    print("     invertito). Da qui la calibrazione B2 sull'excess condizionato.")

    # --- B2: calibrazione CORRETTA sull'excess condizionato ---
    def calibra_excess(componenti, eventi_is):
        pesi, dettaglio = {}, []
        for nome, f in componenti.items():
            si = [e for e in eventi_is if _ok(f, e)]
            no = [e for e in eventi_is if not _ok(f, e)]
            r_si = pulito([e["excess_periodo"] for e in si])
            r_no = pulito([e["excess_periodo"] for e in no])
            if len(r_si) < 10 or len(r_no) < 10:
                pesi[nome] = 0
                continue
            t, p = vl.welch(r_si, r_no)
            delta = float(r_si.mean() - r_no.mean())
            punto = 0
            if np.isfinite(p) and p < 0.10:
                punto = 1 if delta > 0 else -1
            pesi[nome] = punto
            dettaglio.append({"componente": nome, "n_si": len(r_si), "delta_excess_is": round(delta, 2),
                              "p_is": round(float(p), 4) if np.isfinite(p) else None, "punti": punto})
        return pesi, dettaglio

    pesi, dettaglio = calibra_excess(COMPONENTI, ev_is)
    print("\nB2) Calibrazione CORRETTA (confronto dell'EXCESS rispetto alla baseline di stato):")
    print(f"   {'componente':<34}{'delta excess IS':>16}{'p IS':>9}{'punti':>7}")
    for d in dettaglio:
        print(f"   {d['componente'][:33]:<34}{d['delta_excess_is']:>16.2f}"
              f"{(d['p_is'] if d['p_is'] is not None else float('nan')):>9.4f}{d['punti']:>7}")

    for e in eventi:
        e["score"] = sum(p for nome, p in pesi.items() if _ok(COMPONENTI[nome], e))

    def tab_excess(sel, etichetta):
        print(f"\n   {etichetta}")
        print(f"   {'gruppo':<34}{'n':>6}{'excess medio %':>16}{'rend. grezzo %':>16}{'win%':>7}{'falso21%':>10}")
        righe = []
        for nome, cond in (("score = +4", lambda e: e["score"] == 4),
                           ("score = +3", lambda e: e["score"] == 3),
                           ("score = +2", lambda e: e["score"] == 2),
                           ("score = +1", lambda e: e["score"] == 1),
                           ("score ≤ 0", lambda e: e["score"] <= 0),
                           ("score ≥ +2 (aggregato)", lambda e: e["score"] >= 2),
                           ("score ≥ +3", lambda e: e["score"] >= 3)):
            gruppo = [e for e in sel if cond(e)]
            ex = pulito([e["excess_periodo"] for e in gruppo])
            gr = pulito([e["rend"].get(H, np.nan) for e in gruppo])
            if len(ex) < 8:
                continue
            falso = np.mean([1 if e["fallito21"] else 0 for e in gruppo]) * 100
            print(f"   {nome:<34}{len(ex):>6}{ex.mean():>16.2f}{gr.mean():>16.2f}"
                  f"{(gr>0).mean()*100:>7.1f}{falso:>10.1f}")
            righe.append({"gruppo": nome, "n": len(ex), "excess": round(float(ex.mean()), 2),
                          "grezzo": round(float(gr.mean()), 2),
                          "win": round(float((gr > 0).mean() * 100), 1),
                          "falso21": round(float(falso), 1)})
        return righe

    rig_is = tab_excess(ev_is, "IN-SAMPLE 2005-2015 (dove è calibrato)")
    rig_oos = tab_excess(ev_oos, "OUT-OF-SAMPLE 2016-2026 (mai visto nella calibrazione)")
    a2 = pulito([e["excess_periodo"] for e in ev_oos if e["score"] >= 2])
    b2 = pulito([e["excess_periodo"] for e in ev_oos if e["score"] < 2])
    tB, pB = vl.welch(a2, b2)
    print(f"\n   OOS: excess medio con score ≥+2 vs <+2 → {a2.mean():+.2f}% (n={len(a2)}) vs "
          f"{b2.mean():+.2f}% (n={len(b2)})  t={tB:+.2f}  p={pB:.4f}")
    c2 = pulito([e["excess_periodo"] for e in ev_oos if e["score"] >= 1])
    d2 = pulito([e["excess_periodo"] for e in ev_oos if e["score"] < 1])
    tB3, pB3 = vl.welch(c2, d2)
    print(f"   OOS: excess medio con score ≥+1 vs <+1 → {c2.mean():+.2f}% (n={len(c2)}) vs "
          f"{d2.mean():+.2f}% (n={len(d2)})  t={tB3:+.2f}  p={pB3:.4f}")

    risultato["B_punteggio"] = {
        "B1_grezzo": {"pesi": pesi_grezzi, "dettaglio": det_grezzi,
                      "oos_pos_vs_neg": [round(tG, 2), round(pG, 4), len(a1g), len(b1g)]},
        "B2_excess": {"pesi": pesi, "dettaglio": dettaglio, "is": rig_is, "oos": rig_oos,
                      "oos_score2": [round(tB, 2), round(pB, 4), len(a2), len(b2)],
                      "oos_score1": [round(tB3, 2), round(pB3, 4), len(c2), len(d2)]},
    }

    # ======================================================================
    # TEST C — validazione esterna su altri mercati europei
    # ======================================================================
    print("\n\n" + "=" * 118)
    print("TEST C — VALIDAZIONE ESTERNA: stessi filtri su ~50 large cap europee (nessuna calibrazione)")
    print("=" * 118)
    ev_eu = [e for e in eventi_universo(dati_eu, contesto_eu, rank_eu) if e["anno"] >= 2005]
    print(f"Rotture MM200 (Europa, dal 2005): {len(ev_eu)} su {len(dati_eu)} titoli")
    base_eu_tutte = basi_condizionate(dati_eu, "2005-01-01", None)

    # excess periodo-consistente anche per l'Europa (baseline IS per gli eventi IS,
    # baseline OOS per gli eventi OOS): evita di mescolare epoche diverse
    base_eu_is0 = basi_condizionate(dati_eu, "2005-01-01", DATA_IS_FINE)
    base_eu_oos0 = basi_condizionate(dati_eu, f"{DATA_OOS_INIZIO}-01-01", None)
    for e in ev_eu:
        dd = e["dd"]
        st = "altro" if (dd is None or not np.isfinite(dd)) else ("deep_recovery" if dd < -20
                                                                else "vicino_max" if dd > -15 else "altro")
        b = base_eu_is0 if e["anno"] <= DATA_IS_FINE else base_eu_oos0
        e["base_stato"] = float(np.mean(b.get(st, b["tutte"])))
        r = e["rend"].get(H, np.nan)
        e["excess_periodo"] = (float(r) - e["base_stato"]) if np.isfinite(r) else np.nan
    print(f"  baseline Europa — tutte: {np.mean(base_eu_tutte['tutte']):+.2f}% | "
          f"deep recovery: {np.mean(base_eu_tutte['deep_recovery']):+.2f}% | "
          f"vicino max: {np.mean(base_eu_tutte['vicino_max']):+.2f}%")
    # tabella con baseline di stato PERIODO-CONSISTENTE (metodo corretto)
    print(f"\n   {'gruppo':<34}{'n':>6}{'win%':>7}{'medio%':>9}{'base stato%':>13}"
          f"{'excess':>9}{'falso21%':>10}")
    print("   " + "-" * 90)
    righe_eu = []
    for nome, cond in (("rotture in DEEP RECOVERY (dd<-20%)", lambda e: (e["dd"] or 0) < -20),
                       ("rotture VICINO AI MASSIMI (dd>-15%)", lambda e: (e["dd"] or -99) > -15),
                       ("tutte le rotture (controllo)", lambda e: True)):
        sel = [e for e in ev_eu if cond(e)]
        r = pulito([e["rend"].get(H, np.nan) for e in sel])
        ex = pulito([e["excess_periodo"] for e in sel])
        if len(r) < 8:
            continue
        bm = float(np.mean([e["base_stato"] for e in sel]))
        falso = np.mean([1 if e["fallito21"] else 0 for e in sel]) * 100
        t_tot, p_tot = vl.t_vs_base(r, bm)
        print(f"   {nome[:33]:<34}{len(r):>6}{(r>0).mean()*100:>7.1f}{r.mean():>9.2f}{bm:>13.2f}"
              f"{ex.mean():>9.2f}{falso:>10.1f}")
        righe_eu.append({"gruppo": nome, "n": len(r), "win": round(float((r > 0).mean() * 100), 1),
                         "medio": round(float(r.mean()), 2), "baseline": round(bm, 2),
                         "excess": round(float(ex.mean()), 2), "falso21": round(float(falso), 1),
                         "t_vs_base": round(t_tot, 2) if np.isfinite(t_tot) else None,
                         "p_vs_base": round(p_tot, 4) if np.isfinite(p_tot) else None})
    print("   (excess calcolato con la baseline dello stato PERIODO-CONSISTENTE, come nei test italiani)")
    r_dr = [e["rend"].get(H, np.nan) for e in ev_eu if (e["dd"] or 0) < -20]
    r_no = [e["rend"].get(H, np.nan) for e in ev_eu if (e["dd"] or 0) >= -20]
    tC, pC = vl.welch(r_dr, r_no)
    print(f"   Welch deep recovery vs altre rotture (Europa): t={tC:+.2f}  p={pC:.4f}")
    dr_nov = non_sovrapposti([e for e in ev_eu if (e["dd"] or 0) < -20])
    no_nov = non_sovrapposti([e for e in ev_eu if (e["dd"] or 0) >= -20])
    a3 = pulito([e["rend"].get(H, np.nan) for e in dr_nov])
    b3 = pulito([e["rend"].get(H, np.nan) for e in no_nov])
    tC2, pC2 = vl.welch(a3, b3)
    print(f"   Non sovrapposte: deep {a3.mean():+.2f}% (n={len(a3)}) vs altre {b3.mean():+.2f}% "
          f"(n={len(b3)})  t={tC2:+.2f}  p={pC2:.4f}")
    # stabilità tra le due metà (in Europa non c'è calibrazione: è la prova esterna pulita)
    print("\n   Stabilità Europa tra le due metà del campione (excess vs baseline di stato):")
    base_eu_is, base_eu_oos = base_eu_is0, base_eu_oos0
    for etichetta, da, a_, base_ep in (("2005-2015", 2005, DATA_IS_FINE, base_eu_is),
                                       ("2016-2026", DATA_OOS_INIZIO, 2100, base_eu_oos)):
        sub = [e for e in ev_eu if da <= e["anno"] <= a_]
        for nome, cond, chiave in (("deep recovery", lambda e: (e["dd"] or 0) < -20, "deep_recovery"),
                                   ("vicino ai massimi", lambda e: (e["dd"] or -99) > -15, "vicino_max")):
            sel = [e for e in sub if cond(e)]
            r = pulito([e["rend"].get(H, np.nan) for e in sel])
            if len(r) < 8:
                continue
            b = float(np.mean(base_ep[chiave]))
            print(f"      {etichetta} | {nome:<18} n={len(r):<4} rotte={r.mean():+7.2f}%  "
                  f"baseline={b:+7.2f}%  excess={r.mean()-b:+6.2f}  win={(r>0).mean()*100:5.1f}%")

    risultato["C_europa"] = {"n_eventi": len(ev_eu), "righe": [r for r in righe_eu if r],
                             "welch": [round(tC, 2), round(pC, 4)],
                             "non_sovrapposte": [round(tC2, 2), round(pC2, 4), len(a3), len(b3)]}

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "out_of_sample.json"), "w", encoding="utf-8") as fh:
        json.dump(risultato, fh, ensure_ascii=False, indent=2, default=str)
    print(f"\nSalvato: {os.path.join(OUT_DIR, 'out_of_sample.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
