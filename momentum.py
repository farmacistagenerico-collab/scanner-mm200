#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOMENTUM CROSS-SECTIONAL — ranking di forza relativa, ribilanciamento mensile
=============================================================================

Il filone precedente (rottura della MM200, filtri sul singolo titolo) è arrivato
a un risultato nullo. Qui cambio famiglia di segnale: non "quando rompe la media",
ma "quali titoli sono i più forti rispetto agli altri" (momentum cross-sectional),
che è la regolarità più documentata della letteratura finanziaria.

Regole (dichiarate prima di guardare i risultati):
  - universo: titoli di Piazza Affari (MIB / Mid / Star), con filtri di liquidità
  - segnale: rendimento a 12 mesi terminante un mese prima del ribilanciamento
    (mom = P[i-1]/P[i-13] - 1, il classico "12-1" che salta l'ultimo mese per
    evitare il rimbalzo di breve periodo)
  - portafoglio: i N titoli con momentum più alto, equipesati, ribilanciati
    ogni mese; costi 0,2% per lato applicati al turnover
  - varianti: N=10 e N=20, momentum 6 mesi, momentum corretto per volatilità,
    filtro di trend (prezzo sopra la MM200), lato corto (i peggiori N) come
    controllo inverso, portafoglio lungo-corto
  - controlli: universo equipesato (buy & hold), FTSE MIB, e PORTAFOGLI CASUALI
    (30 seed) per rispondere alla domanda "batte il caso?"
  - verifica: split in-sample (2010-2017) / out-of-sample (2018-2026) sui
    risultati, senza ri-ottimizzare nulla.

Uso:
    python3 momentum.py
    python3 momentum.py --dal 2010-01-01 --n 10 --liquidita 500000
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

import titoli_italiani as tu    # noqa: E402
import indicatori as ind       # noqa: E402

OUT_DIR = os.path.join(BASE_DIR, "output")


# ---------------------------------------------------------------------------
# costruzione del pannello mensile
# ---------------------------------------------------------------------------

def pannello_mensile(df: pd.DataFrame) -> pd.DataFrame:
    """Chiuse mensili, turnover mediano, flag MM200, volatilità 12 mesi."""
    d = df.dropna(subset=["Close"]).copy()
    m = pd.DataFrame({
        "close": d["Close"].resample("ME").last(),
        "turnover": (d["Close"] * d["Volume"]).resample("ME").median(),
    })
    mm200 = ind.sma(d["Close"], 200)
    sopra = (d["Close"] > mm200).resample("ME").last()
    m["sopra_mm200"] = sopra.reindex(m.index).fillna(False).astype(bool)
    rend_m = m["close"].pct_change()
    m["vol12"] = rend_m.rolling(12, min_periods=8).std()
    return m


def statistiche(eq: pd.Series, mesi: int, turnover_medio: float | None = None,
                n_medio: float | None = None) -> dict:
    """Statistiche annualizzate da una serie di equity mensile."""
    if eq is None or len(eq) < 12:
        return {}
    anni = mesi / 12
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / anni) - 1
    rm = eq.pct_change().dropna()
    vol = rm.std() * np.sqrt(12)
    sharpe = (rm.mean() * 12) / vol if vol > 0 else np.nan
    dd = float((eq / eq.cummax() - 1).min() * 100)
    out = {
        "CAGR_%": round(float(cagr * 100), 2),
        "volatilità_%": round(float(vol * 100), 2),
        "Sharpe": round(float(sharpe), 2) if np.isfinite(sharpe) else None,
        "max_drawdown_%": round(dd, 2),
        "mesi_positivi_%": round(float((rm > 0).mean() * 100), 1),
        "equity_finale": round(float(eq.iloc[-1]), 2),
    }
    if turnover_medio is not None:
        out["turnover_mensile_%"] = round(float(turnover_medio * 100), 1)
    if n_medio is not None:
        out["titoli_in_portafoglio"] = round(float(n_medio), 1)
    return out


# ---------------------------------------------------------------------------
# simulatore mensile
# ---------------------------------------------------------------------------

def simula(pannelli: dict[str, pd.DataFrame], mesi: list[pd.Timestamp], cfg,
           selettore, nome: str, seed: int | None = None,
           lungo_corto: bool = False) -> tuple[pd.Series, dict]:
    """
    Simulazione mensile.

    `selettore(righe_eleggibili, m_index, rng)` -> lista di ticker da tenere
    nel mese successivo. `righe_eleggibili` è un DataFrame indicizzato per
    ticker con le colonne del pannello mensile (mom, vol, sopra_mm200…).
    """
    rng = np.random.default_rng(seed) if seed is not None else None
    equity = cfg.capitale
    equity_serie, dettagli = [], []
    precedente: list[str] = []

    for i in range(13, len(mesi) - 1):
        data_rib = mesi[i]                 # fine mese i: decidiamo qui
        mese_rend = mesi[i + 1]            # rendimento realizzato nel mese i+1

        # -------- universo eleggibile a fine mese i --------
        righe = {}
        for t, p in pannelli.items():
            if mese_rend not in p.index or data_rib not in p.index:
                continue
            c = p["close"]
            i_rib = p.index.get_loc(data_rib)
            if i_rib < 13:
                continue
            mom = c.iloc[i_rib - 1] / c.iloc[i_rib - 13] - 1
            mom6 = c.iloc[i_rib - 1] / c.iloc[i_rib - 7] - 1
            turn = p["turnover"].iloc[max(0, i_rib - 3):i_rib].median()
            vol = p["vol12"].iloc[i_rib - 1]
            if not np.isfinite(mom) or not np.isfinite(mom6) or not np.isfinite(turn):
                continue
            if c.iloc[i_rib] <= 0:
                continue
            righe[t] = {"mom": mom, "mom6": mom6, "turnover": turn,
                        "vol": vol, "sopra_mm200": bool(p["sopra_mm200"].iloc[i_rib]),
                        "prezzo": float(c.iloc[i_rib])}
        elig = pd.DataFrame(righe).T
        if elig.empty:
            equity_serie.append((mese_rend, equity))
            continue
        elig["liquidita_ok"] = elig["turnover"] >= cfg.liquidita
        elig = elig[elig["liquidita_ok"]]

        if len(elig) < cfg.n_minimo:
            equity_serie.append((mese_rend, equity))
            continue

        scelti = selettore(elig, i, rng)[:cfg.n] if not lungo_corto else selettore(elig, i, rng)
        if not scelti:
            equity_serie.append((mese_rend, equity))
            continue

        # -------- rendimento del mese --------
        rend_azioni = []
        for t in scelti:
            p = pannelli[t]
            r = p["close"].loc[mese_rend] / p["close"].loc[data_rib] - 1
            if np.isfinite(r):
                rend_azioni.append(float(r))
        if not rend_azioni:
            equity_serie.append((mese_rend, equity))
            continue
        rend_portafoglio = float(np.mean(rend_azioni))

        # -------- turnover e costi --------
        if lungo_corto:
            num = len(set(scelti[: len(scelti) // 2]))
            den = max(len(scelti) // 2, 1)
            turnover = 1.0 if not precedente else 1 - len(set(scelti) & set(precedente)) / max(len(scelti), 1)
        else:
            den = max(len(scelti), 1)
            turnover = 1.0 if not precedente else 1 - len(set(scelti) & set(precedente)) / den
        costo = turnover * 2 * cfg.costo_lato          # vendita + acquisto della parte cambiata
        rend_netto = rend_portafoglio - costo

        equity *= (1 + rend_netto)
        equity_serie.append((mese_rend, equity))
        dettagli.append({"data": mese_rend.strftime("%Y-%m-%d"), "n": len(scelti),
                         "turnover": round(turnover * 100, 1), "rend": round(rend_netto * 100, 2),
                         "titoli": ", ".join(scelti[:cfg.n])})
        precedente = list(scelti)

    eq = pd.Series({d: v for d, v in equity_serie}).sort_index()
    turn_medio = np.mean([d["turnover"] for d in dettagli]) / 100 if dettagli else None
    n_medio = np.mean([d["n"] for d in dettagli]) if dettagli else None
    return eq, {"turnover": turn_medio, "n": n_medio, "dettagli": dettagli}


# ---------------------------------------------------------------------------
# selettori
# ---------------------------------------------------------------------------

def sel_top(nome_colonna="mom", filtro_trend=False, inverso=False):
    def f(elig, i, rng):
        e = elig
        if filtro_trend:
            e = e[e["sopra_mm200"]]
            if len(e) == 0:
                e = elig
        ordinato = e.sort_values(nome_colonna, ascending=inverso)
        return list(ordinato.index)
    return f


def sel_random(k):
    def f(elig, i, rng):
        idx = list(elig.index)
        rng.shuffle(idx)
        return idx[:k]
    return f


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Momentum cross-sectional su Piazza Affari")
    ap.add_argument("--dal", default="2010-01-01")
    ap.add_argument("--n", type=int, default=10, help="numero di titoli in portafoglio")
    ap.add_argument("--liquidita", type=float, default=500_000, help="turnover mediano minimo (€/giorno)")
    ap.add_argument("--capitale", type=float, default=100_000.0)
    ap.add_argument("--costo", type=float, default=0.002, help="costo per lato")
    args = ap.parse_args()

    import yfinance as yf

    class Cfg:
        pass

    cfg = Cfg()
    cfg.n = args.n
    cfg.n_minimo = max(args.n + 5, 15)
    cfg.liquidita = args.liquidita
    cfg.capitale = args.capitale
    cfg.costo_lato = args.costo
    cfg.dal = args.dal

    tickers = tu.solo_ticker()
    print(f"Scarico {len(tickers)} titoli di Piazza Affari + FTSE MIB...")
    raw = yf.download(tickers + ["FTSEMIB.MI"], period="max", interval="1d",
                      auto_adjust=True, group_by="ticker", threads=True, progress=False)

    pannelli = {}
    for t in tickers:
        try:
            df = raw[t].dropna(how="all").dropna(subset=["Close"])
        except Exception:
            continue
        if len(df) > 700:
            pannelli[t] = pannello_mensile(df)
    print(f"Titoli nel pannello: {len(pannelli)}")

    mesi = sorted(set().union(*[set(p.index) for p in pannelli.values()]))
    mesi = [d for d in mesi if d >= pd.Timestamp(cfg.dal)]
    print(f"Periodo: {mesi[0].date()} → {mesi[-1].date()} ({len(mesi)} mesi)")

    # universo equipesato (benchmark) e FTSE MIB
    comune = pd.DataFrame({t: p["close"] for t, p in pannelli.items()}).reindex(mesi)
    eq_universo = (comune.pct_change().mean(axis=1).fillna(0) + 1).cumprod() * cfg.capitale
    try:
        mib = raw["FTSEMIB.MI"].dropna(subset=["Close"])["Close"]
        mib_m = mib.resample("ME").last().reindex(mesi, method="ffill")
        mib_m = mib_m[mib_m.index >= pd.Timestamp(cfg.dal)]
        eq_mib = (mib_m / mib_m.iloc[0]) * cfg.capitale
    except Exception:
        eq_mib = None

    # ---------------- varianti ----------------
    varianti = {
        f"MOM 12-1, top {cfg.n}": (sel_top("mom", filtro_trend=False), False),
        f"MOM 12-1, top {cfg.n} + filtro MM200": (sel_top("mom", filtro_trend=True), False),
        f"MOM 12-1, top 20": (sel_top("mom", filtro_trend=False), False),
        f"MOM 6 mesi, top {cfg.n}": (sel_top("mom6", filtro_trend=False), False),
        f"MOM 12-1 corretto per volatilità, top {cfg.n}": (sel_top("mom_vol", filtro_trend=False), False),
        f"PEGGIORI {cfg.n} (controllo inverso)": (sel_top("mom", filtro_trend=False, inverso=True), False),
    }

    def ordina_con_mom_vol(elig, i, rng):
        return list(elig.assign(mom_vol=elig["mom"] / elig["vol"].replace(0, np.nan))
                    .sort_values("mom_vol", ascending=False).index)

    varianti[f"MOM 12-1 corretto per volatilità, top {cfg.n}"] = (ordina_con_mom_vol, False)

    risultati, curve, dettagli_per_variante = [], {}, {}
    for nome, (sel, lc) in varianti.items():
        if "top 20" in nome:
            salvato = cfg.n
            cfg.n = 20
            eq, info = simula(pannelli, mesi, cfg, sel, nome)
            cfg.n = salvato
        else:
            eq, info = simula(pannelli, mesi, cfg, sel, nome)
        if len(eq) < 12:
            print(f"  {nome}: dati insufficienti")
            continue
        st = statistiche(eq, len(eq), info["turnover"], info["n"])
        st["variante"] = nome
        risultati.append(st)
        curve[nome] = eq
        dettagli_per_variante[nome] = info["dettagli"]
        print(f"  {nome:<48} CAGR {st['CAGR_%']:+6.2f}%  Sharpe {st['Sharpe']:+5.2f}  "
              f"maxDD {st['max_drawdown_%']:6.1f}%  turnover {st.get('turnover_mensile_%', 0):5.1f}%/mese")

    # controllo: portafogli CASUALI (30 seed) — risponde a "batte il caso?"
    random_cagr, random_curve = [], []
    for s in range(30):
        eq_r, info_r = simula(pannelli, mesi, cfg, sel_random(cfg.n), f"random-{s}", seed=s)
        if len(eq_r) < 12:
            continue
        st_r = statistiche(eq_r, len(eq_r), info_r["turnover"], info_r["n"])
        random_cagr.append(st_r["CAGR_%"])
        random_curve.append(eq_r)
    if random_curve:
        eq_rand_media = pd.concat(random_curve, axis=1).mean(axis=1)
        st = statistiche(eq_rand_media, len(eq_rand_media))
        st["variante"] = f"Portafogli casuali (media di {len(random_cagr)} seed)"
        risultati.append(st)
        curve[st["variante"]] = eq_rand_media
        p05, p95 = np.percentile(random_cagr, [5, 95])
        print(f"  {'Portafogli CASUALI (' + str(len(random_cagr)) + ' seed)':<48} "
              f"CAGR medio {np.mean(random_cagr):+6.2f}%  (5°-95° percentile: {p05:+.2f}% … {p95:+.2f}%)")

    # benchmark
    st_u = statistiche(eq_universo, len(eq_universo))
    st_u["variante"] = "Universo equipesato (buy & hold)"
    risultati.append(st_u)
    curve[st_u["variante"]] = eq_universo
    if eq_mib is not None and len(eq_mib) > 12:
        st_m = statistiche(eq_mib, len(eq_mib))
        st_m["variante"] = "FTSE MIB (buy & hold)"
        risultati.append(st_m)
        curve[st_m["variante"]] = eq_mib

    tab = pd.DataFrame(risultati).sort_values("CAGR_%", ascending=False)
    colonne = ["variante", "CAGR_%", "volatilità_%", "Sharpe", "max_drawdown_%",
               "turnover_mensile_%", "titoli_in_portafoglio", "mesi_positivi_%", "equity_finale"]
    colonne = [c for c in colonne if c in tab.columns]
    print("\n" + "=" * 118)
    print("RISULTATI (mensile, costi 0,2% per lato sul turnover)")
    print("=" * 118)
    print(tab[colonne].to_string(index=False))

    # ---------------- in-sample / out-of-sample ----------------
    print("\n" + "=" * 118)
    print("IN-SAMPLE (2010-2017) vs OUT-OF-SAMPLE (2018-2026) — nessuna ri-ottimizzazione")
    print("=" * 118)
    righe_isoos = []
    for nome, eq in curve.items():
        for epoca, da, a in (("2010-2017", 2010, 2017), ("2018-2026", 2018, 2100)):
            sub = eq[(eq.index.year >= da) & (eq.index.year <= a)]
            if len(sub) < 24:
                continue
            st = statistiche(sub, len(sub))
            st["variante"] = nome
            st["periodo"] = epoca
            righe_isoos.append(st)
    iso = pd.DataFrame(righe_isoos)
    pivo = iso.pivot_table(index="variante", columns="periodo", values="CAGR_%").round(2)
    pivo_s = iso.pivot_table(index="variante", columns="periodo", values="Sharpe").round(2)
    print("\nCAGR % per periodo:")
    print(pivo.to_string())
    print("\nSharpe per periodo:")
    print(pivo_s.to_string())

    # ---------------- rendimenti per anno (varianti principali) ----------------
    chiavi = [f"MOM 12-1, top {cfg.n}", f"MOM 12-1, top {cfg.n} + filtro MM200",
              f"PEGGIORI {cfg.n} (controllo inverso)", st["variante"] if "casuali" in st["variante"] else None,
              "Universo equipesato (buy & hold)", "FTSE MIB (buy & hold)"]
    curve_anno = {k: curve[k] for k in chiavi if k and k in curve}
    per_anno = {}
    for nome, eq in curve_anno.items():
        annuale = eq.resample("YE").last()
        ann = annuale.pct_change() * 100
        if len(annuale):
            ann.iloc[0] = (annuale.iloc[0] / curve[nome].iloc[0] - 1) * 100
        per_anno[nome] = ann
    tab_anno = pd.DataFrame(per_anno)
    tab_anno.index = [d.year for d in tab_anno.index]
    print("\n" + "=" * 118)
    print("RENDIMENTO PER ANNO (%)")
    print("=" * 118)
    print(tab_anno.round(1).to_string())

    # ---------------- sensibilità alla soglia di liquidità ----------------
    print("\n" + "=" * 118)
    print("SENSIBILITÀ ALLA SOGLIA DI LIQUIDITÀ (MOM 12-1, top 10) — le micro-cap spiegano il risultato?")
    print("=" * 118)
    righe_liq = []
    liquidita_orig = cfg.liquidita
    for soglia in (0, 500_000, 2_000_000, 5_000_000):
        cfg.liquidita = soglia
        eq_l, info_l = simula(pannelli, mesi, cfg, sel_top("mom", filtro_trend=False), "liq")
        st_l = statistiche(eq_l, len(eq_l), info_l["turnover"], info_l["n"])
        s1 = eq_l[eq_l.index.year <= 2017]
        s2 = eq_l[eq_l.index.year >= 2018]
        c1 = statistiche(s1, len(s1)).get("CAGR_%", np.nan)
        c2 = statistiche(s2, len(s2)).get("CAGR_%", np.nan)
        righe_liq.append({"soglia_€/giorno": soglia, "CAGR_%": st_l["CAGR_%"],
                          "Sharpe": st_l["Sharpe"], "max_drawdown_%": st_l["max_drawdown_%"],
                          "CAGR_2010_2017_%": c1, "CAGR_2018_2026_%": c2})
        print(f"   soglia {soglia:>10,.0f} €/g   CAGR {st_l['CAGR_%']:+6.2f}%  Sharpe {st_l['Sharpe']:+5.2f}  "
              f"maxDD {st_l['max_drawdown_%']:6.1f}%   IS {c1:+6.2f}%   OOS {c2:+6.2f}%")
    cfg.liquidita = liquidita_orig
    tab_liq = pd.DataFrame(righe_liq)
    tab_liq.to_csv(os.path.join(OUT_DIR, "momentum_liquidita.csv"), sep=";", decimal=",",
                   encoding="utf-8-sig", index=False)

    # ---------------- salvataggi + report ----------------
    os.makedirs(OUT_DIR, exist_ok=True)
    tab.to_csv(os.path.join(OUT_DIR, "momentum_varianti.csv"), sep=";", decimal=",",
               encoding="utf-8-sig", index=False)
    tab_anno.round(2).to_csv(os.path.join(OUT_DIR, "momentum_per_anno.csv"), sep=";", decimal=",",
                             encoding="utf-8-sig")
    pivo.to_csv(os.path.join(OUT_DIR, "momentum_is_oos.csv"), sep=";", decimal=",",
                encoding="utf-8-sig")
    pd.DataFrame({k: v for k, v in curve.items()}).to_csv(
        os.path.join(OUT_DIR, "momentum_equity.csv"), sep=";", decimal=",",
        encoding="utf-8-sig")

    from momentum_report import scrivi_report_momentum
    path = scrivi_report_momentum(tab, colonne, tab_anno, pivo, pivo_s, curve, cfg,
                                  random_cagr, OUT_DIR, tab_liq)
    print(f"\nReport: {path}")
    with open(os.path.join(OUT_DIR, "momentum_riepilogo.json"), "w", encoding="utf-8") as f:
        json.dump({"varianti": risultati, "is_oos": righe_isoos,
                   "random_cagr": random_cagr}, f, ensure_ascii=False, indent=2, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
