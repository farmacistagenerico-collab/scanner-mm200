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
lato sul nozionale scambiato, portafogli casuali come controllo, paniere
liquido equipesato con stesse date/costi, indice come diagnostica non
comparabile, split storico 2010-2017 / 2018-2026 (esplorativo, non un vero
out-of-sample intatto) e analisi dei crash.

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
import momentum_core as mc         # noqa: E402

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
    """Ritorna (pannelli mensili, chiusure mensili, indice di riferimento mensile).

    L'indice è quello configurato per il mercato attivo, non sempre il FTSE MIB.
    Le barre dell'ultima sessione non sono usate finché la chiusura non è
    confermata; il mese in corso resta escluso dai segnali.
    """
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
        print(f"Scarico {len(tickers)} titoli + {tu.BENCHMARK_NOME} (poi uso la cache)...")
        raw = yf.download(tickers + [tu.BENCHMARK], period="max", interval="1d",
                          auto_adjust=True, group_by="ticker", threads=True, progress=False)
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        try:
            with open(CACHE, "wb") as f:
                pickle.dump(raw, f)
        except Exception:
            pass

    cutoff = mc.ultima_sessione_utile(pd.Timestamp.now(tz="Europe/Rome"), tu.mercato)
    pannelli = {}
    for t in tu.solo_ticker():
        try:
            df = raw[t].dropna(how="all").dropna(subset=["Close"])
            df = df[df.index.normalize() <= cutoff]
        except Exception:
            continue
        if len(df) > 700:
            pannelli[t] = mm.pannello_mensile(df, tu.mercato)

    closes = pd.DataFrame({t: p["close"] for t, p in pannelli.items()})
    closes = closes[closes.index >= pd.Timestamp(dal)]

    indice = None
    try:
        s = raw[tu.BENCHMARK].dropna(subset=["Close"])["Close"]
        s = s[s.index.normalize() <= cutoff]
        indice = mc.mesi_conclusi(s, cutoff, tu.mercato)
        indice = indice[indice.index >= pd.Timestamp(dal)]
    except Exception as e:
        print(f"[avviso] indice {tu.BENCHMARK_NOME} non disponibile: {e}")
    return pannelli, closes, indice


# ---------------------------------------------------------------------------
# selettore con buffer
# ---------------------------------------------------------------------------

def seleziona(elig: pd.DataFrame, precedente: list[str], n: int, buffer: int,
              filtro_mm200: bool, casuale: bool = False, rng=None) -> list[str]:
    """Wrapper storico: la regola unica vive in momentum_core."""
    return mc.seleziona_buffer(elig, precedente, n, buffer, filtro_mm200, casuale, rng)


# ---------------------------------------------------------------------------
# simulatore con volatilità target, overlay e buffer
# ---------------------------------------------------------------------------

def _elegibili(pannelli: dict, data_rib: pd.Timestamp, liquidita: float) -> pd.DataFrame:
    """Universo eleggibile usando SOLO informazioni disponibili a data_rib."""
    righe = {}
    for t, p in pannelli.items():
        if data_rib not in p.index:
            continue
        pos = p.index.get_loc(data_rib)
        if pos < 13:
            continue
        finestra = mc.finestra_momentum(p["close"].iloc[:pos + 1])
        turn = mc.liquidita_storica(p["turnover"], pos)
        if finestra is None or not np.isfinite(turn) or turn < liquidita:
            continue
        righe[t] = {"mom": finestra[0], "sopra_mm200": bool(p["sopra_mm200"].iloc[pos])}
    return pd.DataFrame(righe).T


def _prezzi_esecuzione(pannelli: dict, data_rib: pd.Timestamp, mese_next: pd.Timestamp):
    """Prezzi di ingresso/uscita: prima chiusura dopo la fine del mese segnale.

    Restituisce (entry, exit, gaps). Un titolo senza prezzo di ingresso non viene
    comprato; un titolo senza prezzo di uscita viene marcato come dato mancante.
    Il risultato non è considerato validabile se ci sono gap sui titoli detenuti.
    """
    entry, exit_, gaps = {}, {}, []
    for t, p in pannelli.items():
        if "exec_close" not in p.columns:
            continue
        e = p["exec_close"].get(data_rib, np.nan)
        u = p["exec_close"].get(mese_next, np.nan)
        if np.isfinite(e) and e > 0:
            entry[t] = float(e)
        if np.isfinite(u) and u > 0:
            exit_[t] = float(u)
    return entry, exit_, gaps


def _applica_periodo(equity, pesi_prima, target, entry, exit_, costo_lato):
    """Applica costi sul nozionale scambiato e poi il rendimento del periodo."""
    comprabili = {t: w for t, w in target.items() if t in entry}
    gaps = [t for t in target if t not in entry or t not in exit_]
    costo = mc.costo_transizione(pesi_prima, comprabili, costo_lato)
    rend = {t: (exit_[t] / entry[t] - 1) for t in comprabili if t in exit_}
    lordo = sum(w * rend.get(t, 0.0) for t, w in comprabili.items())
    netto = (1 - costo) * (1 + lordo) - 1
    equity *= (1 + netto)
    pesi_dopo = mc.pesi_dopo_rendimenti(comprabili, {t: rend.get(t, 0.0) for t in comprabili})
    return equity, pesi_dopo, costo, lordo, netto, gaps


def simula_risk(pannelli: dict, mesi: list[pd.Timestamp], cfg, nome: str,
                seed: int | None = None) -> tuple[pd.Series, dict]:
    """Simulazione con pesi reali, costi su ogni transizione e ingresso ritardato.

    Il segnale matura alla chiusura del mese t; l'ingresso è alla prima chiusura
    successiva. I filtri non vengono mai allentati per riempire gli slot: la
    parte non investibile resta liquidità. L'eleggibilità non dipende dal fatto
    che il titolo abbia dati nel mese successivo.
    """
    rng = np.random.default_rng(seed) if seed is not None else None
    equity = cfg.capitale
    start = 13
    serie = [(mesi[start], equity)] if len(mesi) > start else []
    dettagli, gaps_tot = [], []
    corrente: list[str] = []
    pesi: dict[str, float] = {}
    rend_storico: list[float] = []
    picco = equity

    for i in range(start, len(mesi) - 1):
        data_rib, mese_next = mesi[i], mesi[i + 1]
        elig = _elegibili(pannelli, data_rib, cfg.liquidita)
        entry, exit_, _ = _prezzi_esecuzione(pannelli, data_rib, mese_next)

        ribilanciare = (i == start) or ((i - start) % cfg.freq == 0)
        if ribilanciare:
            nuovo = seleziona(elig, corrente, cfg.n, cfg.buffer, cfg.filtro_mm200,
                              cfg.casuale, rng)
        else:
            # Fra i ribilanciamenti si esce comunque da titoli non più liquidi o
            # sotto MM200 (se il filtro è attivo), ma non si riequilibra il ranking.
            tenuti = [t for t in corrente if t in elig.index]
            if cfg.filtro_mm200:
                tenuti = [t for t in tenuti if bool(elig.loc[t, "sopra_mm200"])]
            nuovo = tenuti

        # Esposizione decisa con solo storico disponibile a data_rib.
        esp = 1.0
        if cfg.vol_target and len(rend_storico) >= 6:
            vol_real = float(np.std(rend_storico[-12:], ddof=1) * np.sqrt(12))
            if vol_real > 0:
                esp = float(np.clip(cfg.vol_target / vol_real, 0.3, 1.0))
        if cfg.overlay == "ma" and len(serie) >= 10:
            eq_serie = pd.Series({d: v for d, v in serie})
            ma10 = eq_serie.rolling(10, min_periods=6).mean().iloc[-1]
            if np.isfinite(ma10) and equity < ma10:
                esp = 0.0
        elif cfg.overlay == "dd":
            dd = (equity / picco - 1) * 100
            if dd < -25:
                esp = 0.0
            elif dd < -15:
                esp = 0.5

        if ribilanciare:
            target = mc.pesi_target(nuovo, cfg.n, esp)
        else:
            base = {t: pesi[t] for t in nuovo if t in pesi}
            slot = esp * len(nuovo) / cfg.n
            somma = sum(base.values())
            if somma > 0 and slot > 0:
                target = {t: w * slot / somma for t, w in base.items()}
            elif slot > 0:
                target = mc.pesi_target(nuovo, cfg.n, esp)
            else:
                target = {}

        pesi_prima = pesi
        equity, pesi, costo, lordo, netto, gaps = _applica_periodo(
            equity, pesi_prima, target, entry, exit_, cfg.costo_lato)
        gaps_tot += [{"data": data_rib.strftime("%Y-%m-%d"), "titoli": gaps}] if gaps else []
        picco = max(picco, equity)
        rend_storico.append(netto)
        serie.append((mese_next, equity))
        dettagli.append({"data": mese_next.strftime("%Y-%m-%d"), "n": len(nuovo),
                         "turnover": round(mc.turnover_operativo(pesi_prima, target) * 100, 1),
                         "costo": round(costo * 100, 4),
                         "esposizione": round(sum(target.values()) * 100, 1),
                         "rend": round(netto * 100, 2)})
        corrente = list(nuovo)

    eq = pd.Series({d: v for d, v in serie}).sort_index()
    if len(eq) == 0:
        return eq, {}
    rom = eq.pct_change().dropna()
    info = {
        "turnover": float(np.mean([d["turnover"] for d in dettagli])) / 100 if dettagli else None,
        "esposizione_media": float(np.mean([d["esposizione"] for d in dettagli])) if dettagli else None,
        "mesi_in_cash": float(np.mean([1 if d["esposizione"] < 100 else 0 for d in dettagli]) * 100)
                         if dettagli else None,
        "dettagli": dettagli,
        "mesi": len(rom),
        "gaps_dati": gaps_tot,
        "validabile": not gaps_tot,
    }
    return eq, info


def simula_paniere(pannelli: dict, mesi: list[pd.Timestamp], cfg,
                   filtro_mm200: bool = False) -> tuple[pd.Series, dict]:
    """Paniere equipesato comparabile: stessa liquidità, date, ingressi e costi.

    Non è il buy & hold dell'intero universo storico: ribilancia ogni mese sui
    soli titoli liquidi disponibili in quella data, pagando le transizioni.
    """
    equity = cfg.capitale
    start = 13
    serie = [(mesi[start], equity)] if len(mesi) > start else []
    dettagli, gaps_tot = [], []
    pesi: dict[str, float] = {}
    for i in range(start, len(mesi) - 1):
        data_rib, mese_next = mesi[i], mesi[i + 1]
        elig = _elegibili(pannelli, data_rib, cfg.liquidita)
        if filtro_mm200 and not elig.empty:
            elig = elig[elig["sopra_mm200"].astype(bool)]
        entry, exit_, _ = _prezzi_esecuzione(pannelli, data_rib, mese_next)
        target = {t: 1.0 / len(elig) for t in elig.index} if len(elig) else {}
        pesi_prima = pesi
        equity, pesi, costo, lordo, netto, gaps = _applica_periodo(
            equity, pesi_prima, target, entry, exit_, cfg.costo_lato)
        gaps_tot += [{"data": data_rib.strftime("%Y-%m-%d"), "titoli": gaps}] if gaps else []
        serie.append((mese_next, equity))
        dettagli.append({"data": mese_next.strftime("%Y-%m-%d"), "n": len(elig),
                         "turnover": round(mc.turnover_operativo(pesi_prima, target) * 100, 1),
                         "costo": round(costo * 100, 4),
                         "esposizione": round(sum(target.values()) * 100, 1),
                         "rend": round(netto * 100, 2)})
    eq = pd.Series({d: v for d, v in serie}).sort_index()
    info = {"dettagli": dettagli, "gaps_dati": gaps_tot, "validabile": not gaps_tot,
            "turnover": float(np.mean([d["turnover"] for d in dettagli])) / 100 if dettagli else None,
            "esposizione_media": 100.0, "mesi_in_cash": 0.0, "mesi": max(len(eq) - 1, 0)}
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
    print(f"Mercato: {tu.mercato} | Titoli: {len(pannelli)} | Periodo: {mesi[0].date()} → {mesi[-1].date()} "
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
        st = mm.statistiche(eq, turnover_medio=info["turnover"])
        st["variante"] = nome
        st["esposizione_media_%"] = round(info["esposizione_media"], 1) if info["esposizione_media"] is not None else None
        st["mesi_risk_off_%"] = round(info["mesi_in_cash"], 1) if info["mesi_in_cash"] is not None else None
        st["validabile"] = bool(info.get("validabile", False))
        cr = analisi_crash(eq)
        st["max_dd_%"] = cr.get("max_dd_%")
        st["recupero_mesi"] = cr.get("recupero_mesi")
        st["Calmar"] = cr.get("Calmar")
        risultati.append(st)
        curve[nome] = eq
        crash[nome] = cr
        dettagli_var[nome] = info
        print(f"  {nome:<44} CAGR {st['CAGR_%']:+6.2f}%  vol {st['volatilità_%']:5.1f}%  "
              f"Sharpe {st['Sharpe']:+5.2f}  maxDD {st['max_dd_%']:6.1f}%  "
              f"turnover {st.get('turnover_mensile_%', 0):5.1f}%  espos. {st['esposizione_media_%'] or 0:5.1f}%")

    # ---------------- controllo: portafogli casuali ---------------- #
    # Stesso universo trend, stesso buffer e stessi costi della variante di
    # riferimento: cambia solo l'ordinamento (casuale invece di momentum).
    cfg_rand = nuova_cfg(buffer=mc.BUFFER_RANK, casuale=True)
    rand_cagr, rand_returns = [], []
    for s in range(20):
        eq_r, info_r = simula_risk(pannelli, mesi, cfg_rand, f"random-{s}", seed=s)
        if len(eq_r) < 24:
            continue
        st_r = mm.statistiche(eq_r, turnover_medio=info_r["turnover"])
        rand_cagr.append(st_r["CAGR_%"])
        rand_returns.append(eq_r.pct_change())
    if rand_returns:
        # Media dei rendimenti mensili, non media delle equity curve: la seconda
        # sarebbe un portafoglio di portafogli con ribilanciamento implicito.
        r_rm = pd.concat(rand_returns, axis=1).mean(axis=1).fillna(0)
        eq_rm = (1 + r_rm).cumprod() * args.capitale
        eq_rm.iloc[0] = args.capitale
        st = mm.statistiche(eq_rm)
        st["variante"] = f"⓪ Controllo: casuali equip. (media {len(rand_cagr)} seed)"
        risultati.append(st)
        curve[st["variante"]] = eq_rm
        crash[st["variante"]] = analisi_crash(eq_rm)
        print(f"  {st['variante']:<44} CAGR {st['CAGR_%']:+6.2f}%  "
              f"(5°-95° dei seed: {np.percentile(rand_cagr,5):+.2f}% … {np.percentile(rand_cagr,95):+.2f}%)")

    # ---------------- benchmark comparabile scelto dall'utente ----------------
    cfg_bench = nuova_cfg()
    eq_pan, info_pan = simula_paniere(pannelli, mesi, cfg_bench, filtro_mm200=False)
    eq_pan_trend, info_pan_trend = simula_paniere(pannelli, mesi, cfg_bench, filtro_mm200=True)
    for nome_b, eq_b, info_b in (
            (mc.BENCH_PANIERE, eq_pan, info_pan),
            (mc.BENCH_PANIERE_TREND, eq_pan_trend, info_pan_trend)):
        if len(eq_b) < 24:
            continue
        st = mm.statistiche(eq_b, turnover_medio=info_b["turnover"])
        st["variante"] = nome_b
        st["esposizione_media_%"] = 100.0
        st["mesi_risk_off_%"] = 0.0
        risultati.append(st)
        curve[nome_b] = eq_b
        crash[nome_b] = analisi_crash(eq_b)
        dettagli_var[nome_b] = info_b

    # Diagnostica non comparabile: vecchio buy & hold dell'intero universo e
    # indice di prezzo. Hanno date/universo/costi diversi dalla strategia.
    eq_univ = (closes.pct_change().mean(axis=1).fillna(0) + 1).cumprod() * args.capitale
    if len(eq_pan):
        eq_univ = eq_univ.reindex(eq_pan.index).ffill()
        eq_univ = eq_univ / eq_univ.iloc[0] * args.capitale
    st = mm.statistiche(eq_univ)
    st["variante"] = mc.BENCH_UNIVERSO_STORICO
    risultati.append(st)
    curve[st["variante"]] = eq_univ
    crash[st["variante"]] = analisi_crash(eq_univ)
    if mib is not None and len(mib) > 12:
        eq_mib = mib / mib.iloc[0] * args.capitale
        if len(eq_pan):
            eq_mib = eq_mib.reindex(eq_pan.index).ffill()
            eq_mib = eq_mib / eq_mib.iloc[0] * args.capitale
        st = mm.statistiche(eq_mib)
        st["variante"] = mc.bench_indice(tu.mercato)
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

    # ---------------- split storico esplorativo ----------------
    # Non è un out-of-sample intatto: le varianti sono state scelte dopo aver
    # osservato entrambi i periodi. Serve a misurare la stabilità, non a validare.
    print("\n" + "=" * 132)
    print("SPLIT STORICO ESPLORATIVO: 2010-2017 vs 2018-2026 (non è un holdout intatto)")
    print("=" * 132)
    righe = []
    for nome, eq in curve.items():
        for epoca, da, a in (("2010-2017", 2010, 2017), ("2018-2026", 2018, 2100)):
            sub = mm.sotto_periodo(eq, da, a)
            if len(sub) < 24:
                continue
            s = mm.statistiche(sub)
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
    chiavi = [k for k in curve if k.startswith(("①", "②", "③", "⑤", "⑦", "◇"))]
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
    gaps_per_variante = {k: v.get("gaps_dati", []) for k, v in dettagli_var.items()}
    audit = {
        "mercato": tu.mercato,
        "generato_il": pd.Timestamp.now(tz="Europe/Rome").isoformat(),
        "periodo": {"da": str(mesi[0].date()), "a": str(mesi[-1].date()), "mesi": len(mesi)},
        "universo": {"titoli": len(pannelli), "liquidita_eur_giorno": args.liquidita,
                     "sopravvivenza": "solo titoli presenti nella lista attuale: bias non rimosso"},
        "esecuzione": {"segnale": "chiusura ultima sessione del mese",
                       "ingresso": "prima chiusura della sessione successiva",
                       "costo_lato": args.costo, "capitale": args.capitale},
        "benchmark_principale": mc.BENCH_PANIERE,
        "validato": False,
        "nota_validazione": "Nessun holdout intatto; non usare questi numeri come prova di edge.",
        "gaps_dati": gaps_per_variante,
        "varianti": risultati,
        "crash": {k: v for k, v in crash.items()},
        "random_cagr": rand_cagr,
    }
    with open(os.path.join(OUT_DIR, tu.percorso("momentum_risk_riepilogo.json")), "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
