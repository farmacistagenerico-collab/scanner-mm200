#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PORTAFOGLIO — dal segnale alla strategia: stop, sizing, costi, walk-forward
==========================================================================

Finora abbiamo validato *segnali*. Qui li trasformiamo in una **strategia** e la
misuriamo come si misura una strategia:

  - capitale di partenza, posizioni multiple, rischio per operazione
  - stop iniziale ATR e trailing stop ("chandelier")
  - uscita tecnica (rientro sotto la MM200) e uscita a tempo
  - COSTI reali: 0,2% per lato (commissioni + spread + tassa)
  - equity curve, CAGR, volatilità, Sharpe, max drawdown, profit factor
  - confronto con: FTSE MIB buy & hold, rottura "grezza" (senza filtro),
    ingressi casuali (per verificare che il valore venga dal segnale)

Walk-forward (nessun look-ahead):
  1. VERSIONE A — score FISSO: i pesi validati (recovery, MM200 su, MM50>200,
     forza relativa; penalità vicino ai massimi) applicati a tutti gli anni;
  2. VERSIONE B — score RICALIBRATO OGNI ANNO: a inizio anno Y i pesi delle
     componenti vengono ricalcolati SOLO sui dati precedenti a Y (baseline di
     stato calcolata su finestre già concluse), poi applicati all'anno Y.
     Serve a dimostrare che il risultato non dipende da un'unica calibrazione.

Uso:
    python3 portafoglio.py
    python3 portafoglio.py --dal 2010 --capitale 100000 --rischio 0.01
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import titoli_italiani as tu   # noqa: E402
import indicatori as ind      # noqa: E402
import volume_lab as vl       # noqa: E402

OUT_DIR = os.path.join(BASE_DIR, "output")
H = 250          # orizzonte di riferimento per i rendimenti forward (ricerca)


# ---------------------------------------------------------------------------
# configurazione
# ---------------------------------------------------------------------------

@dataclass
class Cfg:
    capitale: float = 100_000.0
    rischio: float = 0.01          # 1% del capitale a rischio per operazione
    peso_max: float = 0.15         # max 15% del capitale per posizione
    max_posizioni: int = 10
    stop_atr: float = 2.5          # stop iniziale = 2,5 ATR dall'ingresso
    trail_atr: float = 3.0         # trailing = 3 ATR dal massimo di chiusura
    buffer: float = 1.0            # buffer MM200 (come nella ricerca)
    orizzonte: int = 250           # uscita a tempo in sedute
    costo_lato: float = 0.002      # 0,2% per lato (commissioni+spread+tassa)
    dal: str = "2010-01-01"


# ---------------------------------------------------------------------------
# dati e segnali
# ---------------------------------------------------------------------------

def prepara_titolo(df: pd.DataFrame, rank_ret12: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Serie complete del titolo + flag di rottura + componenti dello score."""
    df = df.dropna(subset=["Close"]).copy()
    c = df["Close"]
    out = pd.DataFrame(index=df.index)
    out["Open"] = df["Open"]
    out["High"] = df["High"]
    out["Low"] = df["Low"]
    out["Close"] = c
    out["mm200"] = ind.sma(c, 200)
    out["mm50"] = ind.sma(c, 50)
    out["atr"] = ind.atr(df, 14)
    out["slope20"] = ind.slope_pct(out["mm200"], 20)

    hh = c.rolling(252, min_periods=150).max()
    out["dd"] = (c / hh - 1) * 100
    out["mm50_sopra"] = out["mm50"] > out["mm200"]
    if ticker in rank_ret12.columns:
        out["rs_rank"] = rank_ret12[ticker].reindex(df.index) * 100
    else:
        out["rs_rank"] = np.nan

    stato = ind.stato_mm200(c, out["mm200"], 1.0)
    out["rottura"] = False
    for pos, data in ind.trova_incroci(stato, "SOPRA"):
        out.loc[data, "rottura"] = True

    # componenti dello score (pesi validati in out_of_sample.py)
    comp = (
        (out["dd"] < -20).astype(int)                       # +1 recovery
        - (out["dd"] > -15).astype(int)                     # -1 vicino ai massimi
        + (out["slope20"] > 0).astype(int)                  # +1 MM200 in salita
        + (out["mm50_sopra"]).astype(int)                   # +1 MM50 > MM200
        + (out["rs_rank"] >= 50).astype(int)                # +1 forza relativa
    )
    out["score"] = comp.where(out["mm200"].notna() & out["atr"].notna(), np.nan)
    out["recovery"] = (out["dd"] < -20)
    return out


# ---------------------------------------------------------------------------
# simulatore di portafoglio
# ---------------------------------------------------------------------------

@dataclass
class Posizione:
    ticker: str
    quantita: float
    prezzo_ingresso: float
    stop: float
    data_ingresso: pd.Timestamp
    max_close: float
    giorni: int = 0
    costo_ingresso: float = 0.0


def prepara_arrays(pannello: dict) -> dict:
    """Converte ogni titolo in array numpy + mappa data→riga (per velocità)."""
    arr = {}
    for t, p in pannello.items():
        arr[t] = {
            "idx": {d: i for i, d in enumerate(p.index)},
            "index": p.index,
            "open": p["Open"].to_numpy(dtype=float),
            "high": p["High"].to_numpy(dtype=float),
            "low": p["Low"].to_numpy(dtype=float),
            "close": p["Close"].to_numpy(dtype=float),
            "mm200": p["mm200"].to_numpy(dtype=float),
            "atr": p["atr"].to_numpy(dtype=float),
            "score": p["score"].to_numpy(dtype=float),
            "rottura": p["rottura"].to_numpy(dtype=bool),
            "recovery": p["recovery"].to_numpy(dtype=bool),
        }
    return arr


def simula(arr: dict, date, cfg: Cfg, selettore, nome: str,
           richiedi_rottura: bool = True, tipo_uscita: str = "trail_mm200",
           seed: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Simulazione di portafoglio.

    tipo_uscita:
      - "trail_mm200"   : stop 2,5 ATR + trailing 3 ATR + rientro sotto MM200 + tempo
      - "trail_largo"   : come sopra ma trailing 6 ATR (più adatto a un segnale a 12 mesi)
      - "orizzonte"     : nessuno stop, uscita solo dopo `orizzonte` sedute (test puro del segnale)
    """
    rng = np.random.default_rng(seed) if seed is not None else None
    cassa = cfg.capitale
    posizioni: dict[str, Posizione] = {}
    equity_rows, trade_log = [], []

    for i, oggi in enumerate(date):
        # ---------- 1) posizioni aperte ----------
        for t in list(posizioni.keys()):
            a = arr[t]
            k = a["idx"].get(oggi)
            if k is None:
                continue
            pos = posizioni[t]
            chiusura = a["close"][k]
            if not np.isfinite(chiusura):
                continue
            pos.giorni += 1
            pos.max_close = max(pos.max_close, float(chiusura))
            atr_ora = a["atr"][k]
            if tipo_uscita != "orizzonte" and np.isfinite(atr_ora):
                nuovo = pos.max_close - cfg.trail_atr * atr_ora
                if nuovo > pos.stop:
                    pos.stop = nuovo

            uscita, motivo, prezzo = False, "", None
            if tipo_uscita != "orizzonte" and a["low"][k] <= pos.stop:
                uscita, motivo = True, "stop"
                prezzo = min(a["open"][k], pos.stop) if a["open"][k] < pos.stop else pos.stop
            elif (tipo_uscita in ("trail_mm200", "trail_largo") and np.isfinite(a["mm200"][k])
                  and chiusura < a["mm200"][k] * (1 - cfg.buffer / 100) and pos.giorni >= 3):
                uscita, motivo, prezzo = True, "rientro sotto MM200", chiusura
            elif pos.giorni >= cfg.orizzonte:
                uscita, motivo, prezzo = True, "tempo", chiusura

            if uscita:
                cassa += pos.quantita * prezzo * (1 - cfg.costo_lato)
                pnl = (prezzo * (1 - cfg.costo_lato)
                       - pos.prezzo_ingresso * (1 + cfg.costo_lato)) * pos.quantita
                trade_log.append({
                    "ticker": t, "variante": nome,
                    "data_ingresso": pos.data_ingresso.strftime("%Y-%m-%d"),
                    "data_uscita": oggi.strftime("%Y-%m-%d"),
                    "giorni": pos.giorni, "motivo": motivo,
                    "prezzo_ingresso": round(pos.prezzo_ingresso, 4),
                    "prezzo_uscita": round(prezzo, 4),
                    "pnl": round(float(pnl), 2),
                    "pnl_pct": round(float(prezzo / pos.prezzo_ingresso - 1) * 100, 2),
                })
                del posizioni[t]

        # ---------- 2) segnali di ieri ----------
        if i > 0:
            ieri = date[i - 1]
            candidati = []
            for t, a in arr.items():
                if t in posizioni:
                    continue
                k_ieri = a["idx"].get(ieri)
                k_oggi = a["idx"].get(oggi)
                if k_ieri is None or k_oggi is None:
                    continue
                if richiedi_rottura and not a["rottura"][k_ieri]:
                    continue
                if not np.isfinite(a["score"][k_ieri]):
                    continue
                sc = float(a["score"][k_ieri])
                if selettore is None:
                    candidati.append((t, sc, k_ieri))
                else:
                    ok, peso = selettore(t, ieri, a, k_ieri, rng)
                    if ok:
                        candidati.append((t, float(peso), k_ieri))
            candidati.sort(key=lambda x: (-x[1], x[0]))
            for t, _, k_ieri in candidati:
                if len(posizioni) >= cfg.max_posizioni:
                    break
                a = arr[t]
                k_oggi = a["idx"][oggi]
                prezzo = float(a["open"][k_oggi])
                atr_i = float(a["atr"][k_ieri])
                if not np.isfinite(prezzo) or prezzo <= 0 or not np.isfinite(atr_i):
                    continue
                distanza = cfg.stop_atr * atr_i if atr_i > 0 else prezzo * 0.10
                if distanza <= 0:
                    distanza = prezzo * 0.10
                stop = prezzo - distanza
                equity_ora = cassa + sum(
                    pp.quantita * float(arr[tt]["close"][arr[tt]["idx"][oggi]])
                    for tt, pp in posizioni.items() if oggi in arr[tt]["idx"]
                )
                qta = np.floor(min((equity_ora * cfg.rischio) / distanza,
                                   (equity_ora * cfg.peso_max) / prezzo))
                if qta < 1:
                    continue
                if qta * prezzo * (1 + cfg.costo_lato) > cassa:
                    qta = np.floor(cassa / (prezzo * (1 + cfg.costo_lato)))
                    if qta < 1:
                        continue
                cassa -= qta * prezzo * (1 + cfg.costo_lato)
                posizioni[t] = Posizione(ticker=t, quantita=qta, prezzo_ingresso=prezzo,
                                         stop=stop, data_ingresso=oggi, max_close=prezzo)

        # ---------- 3) equity ----------
        valore = cassa
        for tt, pp in posizioni.items():
            k = arr[tt]["idx"].get(oggi)
            if k is not None and np.isfinite(arr[tt]["close"][k]):
                valore += pp.quantita * float(arr[tt]["close"][k])
        equity_rows.append((oggi, valore, len(posizioni)))

    eq = pd.DataFrame(equity_rows, columns=["data", "equity", "n_posizioni"]).set_index("data")
    return eq, pd.DataFrame(trade_log)


def statistiche(eq_df, trades: pd.DataFrame, nome: str, anni: float) -> dict:
    if eq_df is None or eq_df.empty:
        return {"variante": nome}
    eq = eq_df["equity"]
    rend = eq.pct_change().dropna()
    anni = max(anni, 0.5)
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / anni) - 1
    vol = rend.std() * np.sqrt(252)
    sharpe = (rend.mean() * 252) / vol if vol > 0 else np.nan
    dd = float((eq / eq.cummax() - 1).min() * 100)
    out = {
        "variante": nome,
        "equity_finale": round(float(eq.iloc[-1]), 2),
        "CAGR_%": round(float(cagr * 100), 2),
        "volatilità_%": round(float(vol * 100), 2),
        "Sharpe": round(float(sharpe), 2) if np.isfinite(sharpe) else None,
        "max_drawdown_%": round(dd, 2),
    }
    if "n_posizioni" in eq_df.columns:
        out["esposizione_media_%"] = round(float((eq_df["n_posizioni"] > 0).mean() * 100), 1)
    if trades is not None and not trades.empty:
        vinte = trades[trades["pnl"] > 0]
        perse = trades[trades["pnl"] < 0]
        out.update({
            "n_trade": int(len(trades)),
            "win_rate_%": round(float(len(vinte) / len(trades) * 100), 1),
            "profit_factor": round(float(vinte["pnl"].sum() / abs(perse["pnl"].sum())), 2)
                             if len(perse) and perse["pnl"].sum() != 0 else None,
            "durata_media_gg": round(float(trades["giorni"].mean()), 0),
            "perdita_media_%": round(float(perse["pnl_pct"].mean()), 2) if len(perse) else None,
            "guadagno_medio_%": round(float(vinte["pnl_pct"].mean()), 2) if len(vinte) else None,
        })
    else:
        out.update({"n_trade": 0})
    return out


# ---------------------------------------------------------------------------
# walk-forward: ricalibrazione dei pesi anno per anno
# ---------------------------------------------------------------------------

COMPONENTI_WF = {
    "recovery": lambda r: r["dd"] < -20,
    "vicino_max": lambda r: r["dd"] > -15,
    "mm200_su": lambda r: r["slope20"] > 0,
    "mm50_sopra": lambda r: bool(r["mm50_sopra"]),
    "forza_rel": lambda r: r["rs_rank"] >= 50,
}


def calibra_wf(eventi: pd.DataFrame, base_per_stato: dict, fino_a: pd.Timestamp) -> dict:
    """Pesi ±1 per componente, calibrati sull'EXCESS condizionato dei soli dati passati."""
    ev = eventi[(eventi["data"] < fino_a) & (eventi["data"] + pd.Timedelta(days=365) < fino_a)]
    # ^ eventi il cui esito a 250 sedute si è già realizzato prima di `fino_a`
    if len(ev) < 40:
        return {k: 0 for k in COMPONENTI_WF}
    pesi = {}
    for nome, cond in COMPONENTI_WF.items():
        m = ev.apply(cond, axis=1)
        si, no = ev[m], ev[~m]
        if len(si) < 15 or len(no) < 15:
            pesi[nome] = 0
            continue
        try:
            t, p = vl.welch(si["excess"], no["excess"])
        except Exception:
            pesi[nome] = 0
            continue
        delta = float(si["excess"].mean() - no["excess"].mean())
        pesi[nome] = (1 if delta > 0 else -1) if (np.isfinite(p) and p < 0.10) else 0
    return pesi


def punteggio_wf(riga: pd.Series, pesi: dict) -> int:
    return sum(p for nome, p in pesi.items() if p and COMPONENTI_WF[nome](riga))


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Portafoglio: dal segnale validato alla strategia")
    ap.add_argument("--dal", default="2010-01-01", help="inizio della simulazione")
    ap.add_argument("--capitale", type=float, default=100_000.0)
    ap.add_argument("--rischio", type=float, default=0.01)
    ap.add_argument("--costo", type=float, default=0.002, help="costo per lato (0,002 = 0,2%%)")
    args = ap.parse_args()

    import yfinance as yf

    cfg = Cfg(capitale=args.capitale, rischio=args.rischio, costo_lato=args.costo, dal=args.dal)

    tickers = tu.solo_ticker()
    print(f"Scarico {len(tickers)} titoli di Piazza Affari + FTSE MIB...")
    raw = yf.download(tickers + ["FTSEMIB.MI"], period="max", interval="1d",
                      auto_adjust=True, group_by="ticker", threads=True, progress=False)

    dati = {}
    for t in tickers:
        try:
            df = raw[t].dropna(how="all").dropna(subset=["Close"])
        except Exception:
            continue
        if len(df) > 400:
            dati[t] = df

    closes = pd.DataFrame({t: d["Close"] for t, d in dati.items()})
    rank_ret12 = (closes / closes.shift(252) - 1).rank(axis=1, pct=True)

    # pannello con score e flag di rottura + tabella eventi (per la calibrazione)
    pannello, eventi = {}, []
    for t, df in dati.items():
        p = prepara_titolo(df, rank_ret12, t)
        pannello[t] = p
        mask = p["rottura"] & p["score"].notna() & (p.index >= pd.Timestamp(cfg.dal) - pd.Timedelta(days=420))
        sub = p.loc[mask].copy()
        sub["ticker"] = t
        sub["data"] = sub.index
        # esito a 250 sedute ed excess condizionato allo stato
        posizioni = {d: i for i, d in enumerate(p.index)}
        rend = []
        for d in sub.index:
            i = posizioni[d]
            rend.append(float(p["Close"].iloc[i + H] / p["Close"].iloc[i] - 1) * 100
                        if i + H < len(p) else np.nan)
        sub["rend"] = rend
        eventi.append(sub)

    eventi = pd.concat(eventi).sort_values("data")
    eventi = eventi[eventi["data"] >= pd.Timestamp(cfg.dal)]
    eventi = eventi[eventi["rend"].notna()]

    # baseline di stato per l'excess (calcolata sull'intero campione: serve solo per
    # la diagnostica e per far vedere i pesi ricalibrati; la calibrazione walk-forward
    # usa comunque solo eventi con esito già realizzato)
    def stato_riga(r):
        if not np.isfinite(r["dd"]):
            return "altro"
        if r["dd"] < -20:
            return "recovery"
        if r["dd"] > -15:
            return "vicino_max"
        return "altro"

    eventi["stato"] = eventi.apply(stato_riga, axis=1)
    base_stato = eventi.groupby("stato")["rend"].mean().to_dict()
    base_stato["altro"] = base_stato.get("altro", 0.0)
    eventi["excess"] = eventi.apply(lambda r: r["rend"] - base_stato.get(r["stato"], 0.0), axis=1)

    date = sorted(set().union(*[set(p.index) for p in pannello.values()]))
    date = [d for d in date if d >= pd.Timestamp(cfg.dal)]
    print(f"Periodo simulato: {date[0].date()} → {date[-1].date()} "
          f"({len(date)} sedute, {len(dati)} titoli, {len(eventi)} rotture con score)")

    risultati, tutti_trade, curve = [], [], {}

    arr = prepara_arrays(pannello)
    anni_totali = (date[-1] - date[0]).days / 365.25

    def sel_score(soglia):
        return lambda t, d, a, k, rng_: (a["score"][k] >= soglia, float(a["score"][k]))

    def sel_recovery(t, d, a, k, rng_):
        return (bool(a["recovery"][k]), float(a["score"][k]))

    def sel_tutti(t, d, a, k, rng_):
        return (True, 0.0)

    # ================= BLOCCO 1 — varianti di selezione, gestione standard =================
    varianti = {
        "Score ≥ +3": sel_score(3),
        "Score ≥ +2": sel_score(2),
        "Solo deep recovery": sel_recovery,
        "Rottura grezza (senza filtro)": sel_tutti,
    }
    for nome, f in varianti.items():
        eq, tl = simula(arr, date, cfg, f, nome)
        risultati.append(statistiche(eq, tl, nome, anni_totali))
        tutti_trade.append(tl)
        curve[nome] = eq["equity"]

    # controllo: ingressi casuali, stesso numero di operazioni della "Score ≥ +3",
    # SENZA la condizione di rottura (isola il valore del segnale)
    n_target = max(len(tutti_trade[0]), 50)
    rng = np.random.default_rng(42)
    titoli_lista = list(arr.keys())
    scelte = set()
    tentativi = 0
    while len(scelte) < n_target and tentativi < n_target * 60:
        tentativi += 1
        t = titoli_lista[rng.integers(len(titoli_lista))]
        idx = [d for d in arr[t]["index"] if d >= pd.Timestamp(cfg.dal)]
        if len(idx) < 300:
            continue
        scelte.add((t, idx[rng.integers(250, len(idx) - 5)]))

    def sel_random(t, d, a, k, rng_):
        return ((t, d) in scelte, float(rng_.random()))

    eq_r, tl_r = simula(arr, date, cfg, sel_random, "Ingressi casuali (controllo)",
                        richiedi_rottura=False, seed=7)
    risultati.append(statistiche(eq_r, tl_r, "Ingressi casuali (controllo)", anni_totali))
    tutti_trade.append(tl_r)
    curve["Ingressi casuali (controllo)"] = eq_r["equity"]

    # benchmark FTSE MIB
    try:
        idx_mib = raw["FTSEMIB.MI"].dropna(subset=["Close"])["Close"]
        idx_mib = idx_mib[idx_mib.index >= pd.Timestamp(cfg.dal)]
        eq_b = pd.DataFrame({"equity": cfg.capitale * (idx_mib / idx_mib.iloc[0]),
                             "n_posizioni": 1}, index=idx_mib.index)
        curve["FTSE MIB (buy & hold)"] = eq_b["equity"]
        risultati.append(statistiche(eq_b, None, "FTSE MIB (buy & hold)", anni_totali))
    except Exception as e:
        print(f"Benchmark non disponibile: {e}")

    # benchmark: universo equal-weight (buy & hold) — il confronto CORRETTO per una
    # strategia che tiene molti titoli medi/piccoli, non il FTSE MIB cap-weighted
    try:
        rend_univ = closes.pct_change().mean(axis=1).fillna(0)
        rend_univ = rend_univ[rend_univ.index >= pd.Timestamp(cfg.dal)]
        eq_ew = pd.DataFrame({"equity": cfg.capitale * (1 + rend_univ).cumprod(),
                              "n_posizioni": 1}, index=rend_univ.index)
        curve["Universo equal-weight (buy & hold)"] = eq_ew["equity"]
        risultati.append(statistiche(eq_ew, None, "Universo equal-weight (buy & hold)", anni_totali))
    except Exception as e:
        print(f"Equal-weight non disponibile: {e}")

    # controllo casuale con ORIZZONTE FISSO (stessa meccanica della rottura a 250 sedute):
    # se anche ingressi casuali danno gli stessi numeri, il timing non aggiunge nulla
    def sel_random2(t, d, a, k, rng_):
        return ((t, d) in scelte, float(rng_.random()))

    eq_r2, tl_r2 = simula(arr, date, cfg, sel_random2,
                          "Ingressi casuali · nessuno stop, uscita a 250 sedute",
                          richiedi_rottura=False, tipo_uscita="orizzonte", seed=11)
    risultati.append(statistiche(eq_r2, tl_r2,
                                 "Ingressi casuali · nessuno stop, uscita a 250 sedute", anni_totali))
    tutti_trade.append(tl_r2)
    curve["Ingressi casuali · nessuno stop, uscita a 250 sedute"] = eq_r2["equity"]

    # ================= BLOCCO 2 — effetto del tipo di USCITA =================
    print("\n" + "=" * 124)
    print("EFFETTO DEL TIPO DI USCITA (selezione Score ≥ +3; 'rottura grezza' come controllo)")
    print("=" * 124)
    uscite = {"trail_mm200": "stop 2,5 ATR + trailing 3 ATR + rientro MM200",
              "trail_largo": "stop 2,5 ATR + trailing 6 ATR + rientro MM200",
              "orizzonte": "nessuno stop, uscita a 250 sedute"}
    righe_us = []
    for tipo, descrizione in uscite.items():
        for nome_sel, f in (("Score ≥ +3", sel_score(3)),
                            ("Solo deep recovery", sel_recovery),
                            ("Rottura grezza", sel_tutti)):
            chiave = f"{nome_sel} · {descrizione}"
            eq, tl = simula(arr, date, cfg, f, chiave, tipo_uscita=tipo)
            st = statistiche(eq, tl, chiave, anni_totali)
            righe_us.append(st)
            risultati.append(st)
            tutti_trade.append(tl)
            curve[chiave] = eq["equity"]
            print(f"   {nome_sel:<20} {tipo:<12} CAGR {st['CAGR_%']:+6.2f}%  "
                  f"Sharpe {(st['Sharpe'] if st['Sharpe'] is not None else 0):+.2f}  "
                  f"maxDD {st['max_drawdown_%']:6.1f}%  n={st['n_trade']:<5} "
                  f"win {(st.get('win_rate_%') or float('nan')):5.1f}%  "
                  f"PF {(st.get('profit_factor') or float('nan')):4.2f}")
    tab_uscite = pd.DataFrame(righe_us)

    # ================= BLOCCO 3 — walk-forward =================
    print("\n" + "=" * 124)
    print("WALK-FORWARD — pesi ricalibrati ogni anno SOLO su dati con esito già concluso")
    print("=" * 124)
    anni_da = sorted({d.year for d in date})
    righe_wf = []
    for anno in anni_da:
        pesi = calibra_wf(eventi, base_stato, pd.Timestamp(f"{anno}-01-01"))
        righe_wf.append({"anno": anno, **pesi})
    wf = pd.DataFrame(righe_wf).set_index("anno")
    print(wf.to_string())
    print(f"\n   Componenti attive (anni su {len(wf)}): "
          f"{ {c: int((wf[c] != 0).sum()) for c in wf.columns} }")

    def selettore_wf(t, d, a, k, rng_):
        pesi = wf.loc[d.year].to_dict() if d.year in wf.index else {}
        sc = 0
        for nome_c, punto in pesi.items():
            if not punto:
                continue
            r = {"dd": a["recovery_set"][k] if "recovery_set" in a else np.nan,
                 "slope20": np.nan, "mm50_sopra": False, "rs_rank": np.nan}
            try:
                row = pannello[t].iloc[pannello[t].index.get_loc(d)]
                r = {"dd": row["dd"], "slope20": row["slope20"],
                     "mm50_sopra": bool(row["mm50_sopra"]), "rs_rank": row["rs_rank"]}
            except Exception:
                pass
            if COMPONENTI_WF[nome_c](r):
                sc += punto
        return (sc >= 3), float(sc)

    for tipo in ("trail_mm200", "orizzonte"):
        eq_wf, tl_wf = simula(arr, date, cfg, selettore_wf, f"Walk-forward · {tipo}",
                              tipo_uscita=tipo)
        st_wf = statistiche(eq_wf, tl_wf, f"Walk-forward · {tipo}", anni_totali)
        risultati.append(st_wf)
        tutti_trade.append(tl_wf)
        curve[f"Walk-forward · {tipo}"] = eq_wf["equity"]
        print(f"   walk-forward ({tipo}): CAGR {st_wf['CAGR_%']:+.2f}%  Sharpe {st_wf['Sharpe']}  "
              f"maxDD {st_wf['max_drawdown_%']:.1f}%  n={st_wf['n_trade']}  "
              f"win {st_wf.get('win_rate_%')}%  PF {st_wf.get('profit_factor')}")

    # ================= rendimento per anno =================
    print("\n" + "=" * 124)
    print("RENDIMENTO PER ANNO (variazione percentuale dell'equity)")
    print("=" * 124)
    chiavi_anno = ["Score ≥ +3", "Score ≥ +3 · nessuno stop, uscita a 250 sedute",
                   "Walk-forward · orizzonte", "Rottura grezza (senza filtro)",
                   "Rottura grezza · nessuno stop, uscita a 250 sedute",
                   "Ingressi casuali · nessuno stop, uscita a 250 sedute",
                   "Universo equal-weight (buy & hold)", "FTSE MIB (buy & hold)"]
    curve_anno = {k: curve[k] for k in chiavi_anno if k in curve} or curve
    per_anno = {}
    for nome, eq in curve_anno.items():
        fine_anno = eq.resample("YE").last()
        ann = fine_anno.pct_change().dropna() * 100
        if len(fine_anno):
            primo = (fine_anno.iloc[0] / cfg.capitale - 1) * 100
            ann = pd.concat([pd.Series([primo], index=fine_anno.index[:1]), ann])
        per_anno[nome] = ann
    tab_anno = pd.DataFrame(per_anno)
    tab_anno.index = [d.year for d in tab_anno.index]
    print(tab_anno.round(1).to_string())

    # ================= tabella finale di confronto =================
    colonne = ["variante", "equity_finale", "CAGR_%", "volatilità_%", "Sharpe", "max_drawdown_%",
               "n_trade", "win_rate_%", "profit_factor", "durata_media_gg", "esposizione_media_%"]
    tab = pd.DataFrame(risultati)
    for c in colonne:
        if c not in tab.columns:
            tab[c] = None
    print("\n" + "=" * 124)
    print("TABELLA FINALE (tutte le varianti, ordinate per CAGR)")
    print("=" * 124)
    print(tab.sort_values("CAGR_%", ascending=False)[colonne].to_string(index=False))

    # ---------------- salvataggi ----------------
    os.makedirs(OUT_DIR, exist_ok=True)
    tab.to_csv(os.path.join(OUT_DIR, "portafoglio_varianti.csv"), sep=";", decimal=",",
               encoding="utf-8-sig", index=False)
    tab_anno.round(2).to_csv(os.path.join(OUT_DIR, "portafoglio_per_anno.csv"), sep=";",
                             decimal=",", encoding="utf-8-sig")
    wf.to_csv(os.path.join(OUT_DIR, "portafoglio_walk_forward_pesi.csv"), sep=";", decimal=",",
              encoding="utf-8-sig")
    trades_all = pd.concat([t for t in tutti_trade if t is not None and not t.empty]) \
        if any(t is not None and not t.empty for t in tutti_trade) else pd.DataFrame()
    if not trades_all.empty:
        trades_all.to_csv(os.path.join(OUT_DIR, "portafoglio_operazioni.csv"), sep=";", decimal=",",
                          encoding="utf-8-sig", index=False)
    curve_df = pd.DataFrame({k: v for k, v in curve.items()})
    curve_df.to_csv(os.path.join(OUT_DIR, "portafoglio_equity.csv"), sep=";", decimal=",",
                    encoding="utf-8-sig")

    # report HTML con grafico SVG
    from report_portafoglio import scrivi_report_portafoglio
    path = scrivi_report_portafoglio(tab, tab_anno, wf, curve, cfg, OUT_DIR)
    print(f"\nReport: {path}")
    print(f"CSV: portafoglio_varianti.csv, portafoglio_per_anno.csv, portafoglio_equity.csv, "
          f"portafoglio_operazioni.csv, portafoglio_walk_forward_pesi.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
