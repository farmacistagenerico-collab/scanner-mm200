#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOMENTUM + RISK MANAGEMENT — attenuare i crash senza uccidere il segnale
=========================================================================

Il momentum cross-sectional funziona (momentum.py), ma ha due difetti noti:
  - crash improvvisi (2018 −22%, 2022 −24% sul portafoglio)
  - turnover alto (25-35%/mese) → costi e, nella realtà, tasse

Questo modulo aggiunge tre strumenti di controllo e ne misura l'effetto,
uno alla volta e in combinazione:

  1. VOLATILITY TARGETING — l'esposizione del mese successivo è
     target_vol / volatilità realizzata dei mesi precedenti, limitata fra
     30% e 100% (niente leva, per restare realistici).
  2. OVERLAY DI DRAWDOWN — se l'equity della strategia scende sotto la sua
     media a 10 mesi si va in cash (trend overlay classico); in alternativa
     riduzione progressiva dell'esposizione al crescere del drawdown.
  3. BUFFER E FREQUENZA DI RIBILANCIAMENTO — un titolo già in portafoglio
     viene sostituito solo se il candidato lo supera oltre una fascia di
     tolleranza (buffer di rank); ribilanciamento mensile o trimestrale.

Tutto è misurato con gli stessi controlli degli altri moduli: costi 0,2% per
lato sul turnover effettivo, portafogli casuali come controllo, benchmark
universo equipesato e FTSE MIB, split in-sample 2010-2017 / out-of-sample
2018-2026, e analisi dei crash (peggiori mesi, durata del drawdown, tempo di
recupero).

Uso:
    python3 momentum_risk.py --dal 2010-01-01
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import titoli_italiani as tu        # noqa: E402
import momentum as mm              # noqa: E402

OUT_DIR = os.path.join(BASE_DIR, "output")
CACHE = os.path.join(BASE_DIR, "cache", "momentum_raw.pkl")


@tu.osserva
def _cache_segui_mercato(cod=None):
    global CACHE
    CACHE = os.path.join(BASE_DIR, "cache", tu.percorso("momentum_raw.pkl"))


# ---------------------------------------------------------------------------
# dati (con cache per non riscaricare a ogni prova)
# ---------------------------------------------------------------------------

def carica_pannelli(dal: str, aggiorna=False) -> tuple[dict, pd.DataFrame, pd.Series | None]:
    """Ritorna (pannelli mensili, chiusure mensili comuni, FTSE MIB mensile)."""
    import yfinance as yf

    raw = None
    if os.path.exists(CACHE) and not aggiorna:
        try:
            with open(CACHE, "rb") as f:
                raw = pickle.load(f)
        except Exception:
            raw = None
    if raw is None:
        tickers = tu.solo_ticker()
        print(f"Scarico {len(tickers)} titoli + FTSE MIB (poi uso la cache)...")
        raw = yf.download(tickers + ["FTSEMIB.MI"], period="max", interval="1d",
                          auto_adjust=True, group_by="ticker", threads=True, progress=False)
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        try:
            with open(CACHE, "wb") as f:
                pickle.dump(raw, f)
        except Exception:
            pass

    pannelli = {}
    for t in tu.solo_ticker():
        try:
            df = raw[t].dropna(how="all").dropna(subset=["Close"])
        except Exception:
            continue
        if len(df) > 700:
            pannelli[t] = mm.pannello_mensile(df)

    closes = pd.DataFrame({t: p["close"] for t, p in pannelli.items()})
    closes = closes[closes.index >= pd.Timestamp(dal)]

    mib = None
    try:
        s = raw["FTSEMIB.MI"].dropna(subset=["Close"])["Close"]
        mib = s.resample("ME").last()
        mib = mib[mib.index >= pd.Timestamp(dal)]
    except Exception:
        pass
    return pannelli, closes, mib


# ---------------------------------------------------------------------------
# selettore con buffer
# ---------------------------------------------------------------------------

def seleziona(elig: pd.DataFrame, precedente: list[str], n: int, buffer: int,
              filtro_mm200: bool) -> list[str]:
    """
    Ranking di momentum con buffer: i titoli già in portafoglio restano finché
    il loro rank non scivola oltre n+buffer; solo allora vengono sostituiti.
    """
    e = elig[elig["sopra_mm200"]] if filtro_mm200 else elig
    if len(e) < n:
        e = elig
    ranked = list(e.sort_values("mom", ascending=False).index)
    tetto = ranked[: n + buffer]
    tenuti = [t for t in precedente if t in tetto]
    nuovi = [t for t in ranked if t not in tenuti]
    return (tenuti + nuovi)[:n]


# ---------------------------------------------------------------------------
# simulatore con volatilità target, overlay e buffer
# ---------------------------------------------------------------------------

def simula_risk(pannelli: dict, mesi: list[pd.Timestamp], cfg, nome: str,
                seed: int | None = None) -> tuple[pd.Series, dict]:
    """
    cfg richiede: n, n_minimo, liquidita, capitale, costo_lato, freq (1=mensile,
    3=trimestrale), buffer, vol_target (None o es. 0.15), overlay ("none"|"ma"|"dd"),
    filtro_mm200 (bool), casuale (bool)
    """
    rng = np.random.default_rng(seed) if seed is not None else None
    equity = cfg.capitale
    serie, dettagli = [], []
    corrente: list[str] = []
    rend_storico: list[float] = []
    picco = equity
    esposizione = 1.0

    for i in range(13, len(mesi) - 1):
        data_rib, mese_next = mesi[i], mesi[i + 1]

        # ------- universo eleggibile (come momentum.py) -------
        righe = {}
        for t, p in pannelli.items():
            if data_rib not in p.index or mese_next not in p.index:
                continue
            pos = p.index.get_loc(data_rib)
            if pos < 13:
                continue
            c = p["close"]
            mom = c.iloc[pos - 1] / c.iloc[pos - 13] - 1
            turn = p["turnover"].iloc[max(0, pos - 3):pos].median()
            if not np.isfinite(mom) or not np.isfinite(turn) or turn < cfg.liquidita:
                continue
            righe[t] = {"mom": mom, "sopra_mm200": bool(p["sopra_mm200"].iloc[pos])}
        elig = pd.DataFrame(righe).T

        # ------- selezione (solo ai ribilanciamenti) -------
        ribilanciare = (len(dettagli) == 0) or (i % cfg.freq == 0)
        if ribilanciare and len(elig) >= cfg.n_minimo:
            if cfg.casuale:
                idx = list(elig.index)
                rng.shuffle(idx)
                nuovo = idx[:cfg.n]
            else:
                nuovo = seleziona(elig, corrente, cfg.n, cfg.buffer, cfg.filtro_mm200)
        else:
            nuovo = [t for t in corrente if t in elig.index] or corrente

        if not nuovo:
            serie.append((mese_next, equity))
            continue

        # ------- rendimento lordo del mese -------
        rend_azioni = [float(pannelli[t]["close"].loc[mese_next] /
                             pannelli[t]["close"].loc[data_rib] - 1)
                       for t in nuovo
                       if data_rib in pannelli[t].index and mese_next in pannelli[t].index]
        rend_azioni = [r for r in rend_azioni if np.isfinite(r)]
        if not rend_azioni:
            serie.append((mese_next, equity))
            continue
        rend_loro = float(np.mean(rend_azioni))

        # ------- esposizione: volatilità target + overlay -------
        esp = 1.0
        if cfg.vol_target and len(rend_storico) >= 6:
            vol_real = float(np.std(rend_storico[-12:], ddof=1) * np.sqrt(12))
            if vol_real > 0:
                esp = float(np.clip(cfg.vol_target / vol_real, 0.3, 1.0))
        if cfg.overlay == "ma" and len(serie) >= 10:
            eq_serie = pd.Series({d: v for d, v in serie})
            ma10 = eq_serie.rolling(10, min_periods=6).mean().iloc[-1]
            if np.isfinite(ma10) and equity < ma10:
                esp *= 0.0                     # risk-off: in cash
        elif cfg.overlay == "dd":
            dd = (equity / picco - 1) * 100
            if dd < -25:
                esp *= 0.0
            elif dd < -15:
                esp *= 0.5

        # ------- turnover e costi (solo sulla parte investita) -------
        if ribilanciare:
            if not corrente:
                turnover = 1.0
            else:
                turnover = 1 - len(set(nuovo) & set(corrente)) / max(len(nuovo), 1)
            costo = turnover * 2 * cfg.costo_lato * esp
        else:
            turnover, costo = 0.0, 0.0

        rend_netto = esp * rend_loro - costo
        equity *= (1 + rend_netto)
        picco = max(picco, equity)
        rend_storico.append(rend_netto)
        serie.append((mese_next, equity))
        dettagli.append({"data": mese_next.strftime("%Y-%m-%d"), "n": len(nuovo),
                         "turnover": round(turnover * 100, 1), "esposizione": round(esp * 100, 1),
                         "rend": round(rend_netto * 100, 2)})
        corrente = list(nuovo)

    eq = pd.Series({d: v for d, v in serie}).sort_index()
    if len(eq) == 0:
        return eq, {}
    rom = eq.pct_change().dropna()
    info = {
        "turnover": float(np.mean([d["turnover"] for d in dettagli])) / 100 if dettagli else None,
        "esposizione_media": float(np.mean([d["esposizione"] for d in dettagli])) if dettagli else None,
        "mesi_in_cash": float(np.mean([1 if d["esposizione"] < 1 else 0 for d in dettagli]) * 100)
                         if dettagli else None,
        "dettagli": dettagli,
        "mesi": len(rom),
    }
    return eq, info


# ---------------------------------------------------------------------------
# diagnostica dei crash
# ---------------------------------------------------------------------------

def analisi_crash(eq: pd.Series) -> dict:
    """Peggiori mesi, drawdown massimo con durata e tempo di recupero."""
    if eq is None or len(eq) < 12:
        return {}
    rm = eq.pct_change().dropna()
    peggiori = rm.nsmallest(3)
    cummax = eq.cummax()
    dd = eq / cummax - 1
    fondo = dd.idxmin()
    dd_min = float(dd.min() * 100)
    # inizio del drawdown e recupero
    prima = eq.loc[:fondo]
    inizio = prima[prima >= cummax.loc[fondo]].index.min() if len(prima) else None
    dopo = eq.loc[fondo:]
    rec = dopo[dopo >= cummax.loc[fondo]]
    recupero = rec.index.min() if len(rec) else None
    durata = ((fondo - inizio).days / 30.44) if inizio is not None else None
    recupero_mesi = ((recupero - fondo).days / 30.44) if recupero is not None else None
    return {
        "peggior_mese_1": f"{peggiori.index[0]:%Y-%m} ({peggiori.iloc[0]*100:+.1f}%)",
        "peggior_mese_2": f"{peggiori.index[1]:%Y-%m} ({peggiori.iloc[1]*100:+.1f}%)",
        "peggior_mese_3": f"{peggiori.index[2]:%Y-%m} ({peggiori.iloc[2]*100:+.1f}%)",
        "max_dd_%": round(dd_min, 1),
        "dd_inizio": f"{inizio:%Y-%m}" if inizio is not None else None,
        "dd_fondo": f"{fondo:%Y-%m}",
        "dd_durata_mesi": round(durata, 1) if durata is not None else None,
        "recupero_mesi": round(recupero_mesi, 1) if recupero_mesi is not None else None,
        "Calmar": round(float((eq.iloc[-1] / eq.iloc[0]) ** (12 / len(rm)) - 1) * 100 / abs(dd_min), 2)
                   if dd_min < 0 else None,
    }


def per_anno(eq: pd.Series, capitale: float) -> pd.Series:
    annuale = eq.resample("YE").last()
    ann = annuale.pct_change() * 100
    if len(annuale):
        ann.iloc[0] = (annuale.iloc[0] / eq.iloc[0] - 1) * 100
    ann.index = [d.year for d in ann.index]
    return ann


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Momentum + risk management")
    ap.add_argument("--dal", default="2010-01-01")
    ap.add_argument("--capitale", type=float, default=100_000.0)
    ap.add_argument("--liquidita", type=float, default=2_000_000,
                    help="turnover mediano minimo €/giorno (default più severo del modulo base)")
    ap.add_argument("--costo", type=float, default=0.002)
    ap.add_argument("--aggiorna-dati", action="store_true")
    ap.add_argument("--mercato", default="IT", help="IT, DE, FR (default IT)")
    args = ap.parse_args()
    tu.imposta_mercato(args.mercato)

    class Cfg:
        pass

    def nuova_cfg(**kw):
        c = Cfg()
        c.n = 10
        c.n_minimo = 15
        c.liquidita = args.liquidita
        c.capitale = args.capitale
        c.costo_lato = args.costo
        c.freq = 1
        c.buffer = 0
        c.vol_target = None
        c.overlay = "none"
        c.filtro_mm200 = True
        c.casuale = False
        for k, v in kw.items():
            setattr(c, k, v)
        return c

    pannelli, closes, mib = carica_pannelli(args.dal, args.aggiorna_dati)
    mesi = sorted(closes.index)
    print(f"Titoli: {len(pannelli)} | Periodo: {mesi[0].date()} → {mesi[-1].date()} "
          f"({len(mesi)} mesi) | soglia liquidità: {args.liquidita:,.0f} €/giorno")

    # ---------------- varianti ----------------
    varianti = {
        "① Base MOM 12-1 top10 + MM200 (mensile)": nuova_cfg(),
        "② + buffer di rank 5": nuova_cfg(buffer=5),
        "③ + ribilanciamento trimestrale (buffer 5)": nuova_cfg(buffer=5, freq=3),
        "④ + volatility targeting 15%": nuova_cfg(vol_target=0.15),
        "⑤ + overlay trend su equity (MA10)": nuova_cfg(overlay="ma"),
        "⑥ + overlay drawdown (15%/25%)": nuova_cfg(overlay="dd"),
        "⑦ Combinato: trimestrale + VT + MA10": nuova_cfg(buffer=5, freq=3,
                                                       vol_target=0.15, overlay="ma"),
        "⑧ Combinato: mensile + buffer + VT + DD": nuova_cfg(buffer=5, vol_target=0.15,
                                                             overlay="dd"),
        "①-bis Base senza filtro MM200": nuova_cfg(filtro_mm200=False),
    }

    risultati, curve, crash = [], {}, {}
    print("\n" + "=" * 132)
    print("VARIANTI")
    print("=" * 132)
    dettagli_var = {}
    for nome, cfg in varianti.items():
        eq, info = simula_risk(pannelli, mesi, cfg, nome)
        if len(eq) < 24:
            print(f"  {nome}: dati insufficienti")
            continue
        st = mm.statistiche(eq, len(eq), info["turnover"], None)
        st["variante"] = nome
        st["esposizione_media_%"] = round(info["esposizione_media"], 1) if info["esposizione_media"] else None
        st["mesi_risk_off_%"] = round(info["mesi_in_cash"], 1) if info["mesi_in_cash"] else None
        cr = analisi_crash(eq)
        st["max_dd_%"] = cr.get("max_dd_%")
        st["recupero_mesi"] = cr.get("recupero_mesi")
        st["Calmar"] = cr.get("Calmar")
        risultati.append(st)
        curve[nome] = eq
        crash[nome] = cr
        dettagli_var[nome] = info.get("dettagli", [])
        print(f"  {nome:<44} CAGR {st['CAGR_%']:+6.2f}%  vol {st['volatilità_%']:5.1f}%  "
              f"Sharpe {st['Sharpe']:+5.2f}  maxDD {st['max_dd_%']:6.1f}%  "
              f"turnover {st.get('turnover_mensile_%', 0):5.1f}%  espos. {st['esposizione_media_%'] or 0:5.1f}%")

    # ---------------- controllo: portafogli casuali ---------------- #
    cfg_rand = nuova_cfg(casuale=True)
    rand_cagr, rand_curve = [], []
    for s in range(20):
        eq_r, info_r = simula_risk(pannelli, mesi, cfg_rand, f"random-{s}", seed=s)
        if len(eq_r) < 24:
            continue
        st_r = mm.statistiche(eq_r, len(eq_r), info_r["turnover"], None)
        rand_cagr.append(st_r["CAGR_%"])
        rand_curve.append(eq_r)
    if rand_curve:
        eq_rm = pd.concat(rand_curve, axis=1).mean(axis=1)
        st = mm.statistiche(eq_rm, len(eq_rm))
        st["variante"] = f"⓪ Controllo: casuali equip. (media {len(rand_cagr)} seed)"
        risultati.append(st)
        curve[st["variante"]] = eq_rm
        crash[st["variante"]] = analisi_crash(eq_rm)
        print(f"  {st['variante']:<44} CAGR {st['CAGR_%']:+6.2f}%  "
              f"(5°-95° dei seed: {np.percentile(rand_cagr,5):+.2f}% … {np.percentile(rand_cagr,95):+.2f}%)")

    # benchmark
    eq_univ = (closes.pct_change().mean(axis=1).fillna(0) + 1).cumprod() * args.capitale
    st = mm.statistiche(eq_univ, len(eq_univ))
    st["variante"] = "◇ Universo equipesato (buy & hold)"
    risultati.append(st)
    curve[st["variante"]] = eq_univ
    crash[st["variante"]] = analisi_crash(eq_univ)
    if mib is not None and len(mib) > 12:
        eq_mib = mib / mib.iloc[0] * args.capitale
        st = mm.statistiche(eq_mib, len(eq_mib))
        st["variante"] = "◇ FTSE MIB (buy & hold)"
        risultati.append(st)
        curve[st["variante"]] = eq_mib
        crash[st["variante"]] = analisi_crash(eq_mib)

    tab = pd.DataFrame(risultati)
    if "max_drawdown_%" in tab.columns:          # i benchmark hanno solo questa colonna
        tab["max_dd_%"] = tab["max_dd_%"].fillna(tab["max_drawdown_%"])
    colonne = ["variante", "CAGR_%", "volatilità_%", "Sharpe", "max_dd_%", "Calmar",
               "turnover_mensile_%", "esposizione_media_%", "mesi_risk_off_%", "recupero_mesi",
               "mesi_positivi_%"]
    colonne = [c for c in colonne if c in tab.columns]
    print("\n" + "=" * 132)
    print("TABELLA FINALE (ordinate per Sharpe)")
    print("=" * 132)
    print(tab.sort_values("Sharpe", ascending=False)[colonne].to_string(index=False))

    # ---------------- in-sample / out-of-sample ----------------
    print("\n" + "=" * 132)
    print("IN-SAMPLE (2010-2017) vs OUT-OF-SAMPLE (2018-2026)")
    print("=" * 132)
    righe = []
    for nome, eq in curve.items():
        for epoca, da, a in (("2010-2017", 2010, 2017), ("2018-2026", 2018, 2100)):
            sub = eq[(eq.index.year >= da) & (eq.index.year <= a)]
            if len(sub) < 24:
                continue
            s = mm.statistiche(sub, len(sub))
            s["variante"] = nome
            s["periodo"] = epoca
            righe.append(s)
    iso = pd.DataFrame(righe)
    pivo_c = iso.pivot_table(index="variante", columns="periodo", values="CAGR_%").round(2)
    pivo_s = iso.pivot_table(index="variante", columns="periodo", values="Sharpe").round(2)
    pivo_d = iso.pivot_table(index="variante", columns="periodo", values="max_drawdown_%").round(1)
    print("\nCAGR % per periodo:")
    print(pivo_c.to_string())
    print("\nSharpe per periodo:")
    print(pivo_s.to_string())
    print("\nMax drawdown % per periodo:")
    print(pivo_d.to_string())

    # ---------------- crash ----------------
    print("\n" + "=" * 132)
    print("DIAGNOSTICA DEI CRASH")
    print("=" * 132)
    righe_cr = []
    for nome, cr in crash.items():
        if not cr:
            continue
        righe_cr.append({"variante": nome, **cr})
    tab_cr = pd.DataFrame(righe_cr)
    print(tab_cr[["variante", "peggior_mese_1", "peggior_mese_2", "max_dd_%", "dd_durata_mesi",
                  "recupero_mesi", "Calmar"]].to_string(index=False))

    # ---------------- per anno ----------------
    chiavi = [k for k in curve if k.startswith(("①", "③", "⑤", "⑦", "◇"))]
    tab_anno = pd.DataFrame({k: per_anno(curve[k], args.capitale) for k in chiavi})
    print("\n" + "=" * 132)
    print("RENDIMENTO PER ANNO (%)")
    print("=" * 132)
    print(tab_anno.round(1).to_string())

    # ---------------- salvataggi + report ----------------
    os.makedirs(OUT_DIR, exist_ok=True)
    tab.sort_values("Sharpe", ascending=False).to_csv(
        os.path.join(OUT_DIR, tu.percorso("momentum_risk_varianti.csv")), sep=";", decimal=",",
        encoding="utf-8-sig", index=False)
    tab_cr.to_csv(os.path.join(OUT_DIR, tu.percorso("momentum_risk_crash.csv")), sep=";", decimal=",",
                  encoding="utf-8-sig", index=False)
    tab_anno.round(2).to_csv(os.path.join(OUT_DIR, tu.percorso("momentum_risk_per_anno.csv")), sep=";",
                             decimal=",", encoding="utf-8-sig")
    pivo_c.to_csv(os.path.join(OUT_DIR, tu.percorso("momentum_risk_is_oos.csv")), sep=";", decimal=",",
                  encoding="utf-8-sig")
    pd.DataFrame(curve).to_csv(os.path.join(OUT_DIR, tu.percorso("momentum_risk_equity.csv")), sep=";",
                               decimal=",", encoding="utf-8-sig")

    from momentum_risk_report import scrivi_report_risk
    path = scrivi_report_risk(tab, colonne, tab_anno, tab_cr, pivo_c, pivo_s, pivo_d,
                             curve, args, rand_cagr, OUT_DIR)
    print(f"\nReport: {path}")
    with open(os.path.join(OUT_DIR, tu.percorso("momentum_risk_riepilogo.json")), "w", encoding="utf-8") as f:
        json.dump({"varianti": risultati, "crash": {k: v for k, v in crash.items()},
                   "random_cagr": rand_cagr}, f, ensure_ascii=False, indent=2, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
