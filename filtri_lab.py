#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FILTRI LAB — quale strumento, abbinato alla MM200, rende la rottura affidabile?
================================================================================

Il volume non filtra (vedi volume_lab.py). Quali altri strumenti funzionano?
Questo modulo testa ~20 candidati, tutti calcolabili AL MOMENTO della rottura,
senza look-ahead:

  REGIME DI MERCATO   FTSE MIB sopra/sotto la sua MM200, pendenza dell'indice,
                      breadth (% titoli dell'universo sopra la propria MM200)
  STRUTTURA           pendenza della MM200, MM50 sopra MM200, medie allineate
  POSIZIONE            vicinanza ai massimi a 12 mesi, drawdown recente
  MOMENTUM            rendimento 6/12 mesi, forza relativa vs universo
  VOLATILITÀ          percentile ATR, compressione di Bollinger, base stretta
  QUALITÀ             RSI, chiusura nella parte alta della barra, estensione
                      della rottura in ATR, "pulizia" (nessun incrocio recente)

Per ogni filtro misura:
  - rendimento a 250 sedute (gruppo "sì" vs "no", test t di Welch)
  - probabilità di FALSO BREAKOUT = rientro sotto la MM200 entro 21 sedute
  - coerenza fra le due metà del campione (2005-2014 / 2015-2026)
  - per i migliori: controllo con finestre non sovrapposte

Uso:
    python3 filtri_lab.py --dal 2005-01-01
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

OUT_DIR = os.path.join(BASE_DIR, "output")
ORIZZONTI = [21, 63, 126, 250]
BUFFER = 1.0


# ---------------------------------------------------------------------------
# serie estese per titolo
# ---------------------------------------------------------------------------

def serie_estese(df: pd.DataFrame) -> dict:
    """Serie di base (volume_lab) + quelle richieste dai filtri aggiuntivi."""
    s = vl.prepara(df)
    c = s["close"]
    s["rsi"] = ind.rsi(c, 14)
    s["m20"] = ind.sma(c, 20)
    s["ret6"] = (c / c.shift(126) - 1) * 100
    s["ret12"] = (c / c.shift(252) - 1) * 100

    hh = c.rolling(252, min_periods=150).max()
    s["prox_high"] = c / hh                 # 1.0 = sui massimi a 12 mesi
    s["dd"] = (c / hh - 1) * 100            # drawdown dal massimo a 12 mesi (%)

    s["atr"] = ind.atr(df, 14)
    s["atr_pct"] = s["atr"] / c * 100
    s["atr_pctile"] = s["atr_pct"].rolling(250, min_periods=100).rank(pct=True) * 100
    s["dist_atr"] = (c - s["mm200"]) / s["atr"]

    std20 = c.rolling(20).std()
    s["bbw"] = 4 * std20 / s["m20"] * 100
    s["bbw_pctile"] = s["bbw"].rolling(250, min_periods=100).rank(pct=True) * 100

    hi20 = df["High"].rolling(20).max()
    lo20 = df["Low"].rolling(20).min()
    s["base_tight"] = ((hi20 - lo20) / c * 100) / s["atr_pct"].replace(0, np.nan)
    s["allineate"] = (c > s["mm50"]) & (s["mm50"] > s["mm200"])
    s["rv0"] = s["rv"]                       # volume relativo del giorno di rottura

    # struttura settimanale (MM40W ≈ MM200 giornaliera) riportata sul giornaliero
    w = ind.serie_settimanale(df)
    w = w[w["Volume"] > 0] if "Volume" in w else w
    if len(w) >= 40:
        wc = w["Close"]
        w40, w10 = ind.sma(wc, 40), ind.sma(wc, 10)
        ok = (wc > w40) & (w10 > w40)
        s["weekly_ok"] = ok.reindex(df.index, method="ffill").astype(float)
    else:
        s["weekly_ok"] = pd.Series(np.nan, index=df.index)
    return s


# ---------------------------------------------------------------------------
# eventi con tutti i campi dei filtri
# ---------------------------------------------------------------------------

def eventi_titolo(df, contesto, rank_ret12, dal=None, ticker=None):
    df = df.dropna(subset=["Close"]).copy()
    if len(df) < 320:
        return []
    if dal is not None:
        df = df[df.index >= pd.Timestamp(dal) - pd.Timedelta(days=420)]
    if len(df) < 320:
        return []

    s = serie_estese(df)
    stato = ind.stato_mm200(s["close"], s["mm200"], BUFFER)
    incroci = ind.trova_incroci(stato, "SOPRA")
    if not incroci:
        return []
    # date di TUTTI gli incroci (su e giù) per il filtro "pulizia"
    tutte_le_date = sorted([d for _, d in incroci] +
                           [d for _, d in ind.trova_incroci(stato, "SOTTO")])

    def ultimo_incrocio_precedente(data):
        prec = [d for d in tutte_le_date if d < data]
        return prec[-1] if prec else None

    uscita = []
    for pos, data in incroci:
        if pos + 5 >= len(df):
            continue

        def g(nome, i=pos):
            try:
                x = s[nome].iloc[i]
                return float(x) if np.isfinite(x) else np.nan
            except Exception:
                return np.nan

        base = float(s["close"].iloc[pos])
        rend = {h: (float((s["close"].iloc[pos + h] / base - 1) * 100)
                    if pos + h < len(df) else np.nan) for h in ORIZZONTI}

        # falso breakout: chiusura di nuovo sotto la MM200 entro 21 sedute
        fallito21, fallito63 = False, False
        for k in range(1, 22):
            if pos + k < len(df) and np.isfinite(s["mm200"].iloc[pos + k]):
                if s["close"].iloc[pos + k] < s["mm200"].iloc[pos + k]:
                    fallito21 = True
                    break
        for k in range(1, 64):
            if pos + k < len(df) and np.isfinite(s["mm200"].iloc[pos + k]):
                if s["close"].iloc[pos + k] < s["mm200"].iloc[pos + k]:
                    fallito63 = True
                    break

        # massima escursione avversa nei 63 giorni
        f63 = min(pos + 63, len(df))
        mae63 = float((s["close"].iloc[pos + 1:f63 + 1].min() / base - 1) * 100) \
            if f63 > pos else np.nan

        # contesto di mercato alla data
        try:
            riga = contesto.loc[data] if data in contesto.index else contesto.iloc[
                contesto.index.searchsorted(data, side="right") - 1]
            mib_above = bool(riga["mib_above"]) if pd.notna(riga["mib_above"]) else None
            mib_slope = float(riga["mib_slope"]) if pd.notna(riga["mib_slope"]) else np.nan
            breadth = float(riga["breadth"]) if pd.notna(riga["breadth"]) else np.nan
        except Exception:
            mib_above, mib_slope, breadth = None, np.nan, np.nan

        # forza relativa (percentile del rendimento 12 mesi nell'universo)
        rs = np.nan
        try:
            if data in rank_ret12.index and ticker in rank_ret12.columns:
                x = rank_ret12.at[data, ticker]
                rs = float(x) if pd.notna(x) else np.nan
        except Exception:
            pass

        prec = ultimo_incrocio_precedente(data)
        giorni_prec = (data - prec).days if prec is not None else None

        uscita.append({
            "titolo": ticker, "data": data.strftime("%Y-%m-%d"), "anno": int(data.year),
            "rend": rend, "fallito21": fallito21, "fallito63": fallito63, "mae63": mae63,
            "slope20": g("slope20"), "mm50_sopra": bool(g("mm50") > g("mm200")) if np.isfinite(g("mm50")) else None,
            "allineate": bool(g("allineate") == 1.0) if np.isfinite(g("allineate")) else None,
            "prox_high": g("prox_high"), "dd": g("dd"),
            "ret6": g("ret6"), "ret12": g("ret12"), "rs_rank": rs,
            "rsi": g("rsi"), "atr_pctile": g("atr_pctile"), "bbw_pctile": g("bbw_pctile"),
            "base_tight": g("base_tight"), "dist_atr": g("dist_atr"), "close_pos": g("close_pos"),
            "giorni_da_incrocio": giorni_prec,
            "rv0": g("rv0"), "weekly_ok": g("weekly_ok"),
            "mib_above": mib_above, "mib_slope": mib_slope, "breadth": breadth,
        })
    return uscita


# ---------------------------------------------------------------------------
# filtri da testare
# ---------------------------------------------------------------------------

FILTRI = {
    "REGIME: FTSE MIB sopra la sua MM200": lambda e: e["mib_above"] is True,
    "REGIME: FTSE MIB con MM200 in salita": lambda e: (e["mib_slope"] or -99) > 0,
    "BREADTH: ≥50% dei titoli sopra la propria MM200": lambda e: (e["breadth"] or -1) >= 0.5,
    "BREADTH: ≥65% dei titoli sopra la propria MM200": lambda e: (e["breadth"] or -1) >= 0.65,
    "STRUTTURA: MM200 in salita (>0%)": lambda e: (e["slope20"] or -99) > 0,
    "STRUTTURA: MM200 chiaramente in salita (>1%)": lambda e: (e["slope20"] or -99) > 1,
    "STRUTTURA: MM50 sopra la MM200": lambda e: e["mm50_sopra"] is True,
    "STRUTTURA: medie allineate (prezzo>MM50>MM200)": lambda e: e["allineate"] is True,
    "POSIZIONE: entro il 5% dai massimi a 12 mesi": lambda e: (e["prox_high"] or 0) >= 0.95,
    "POSIZIONE: drawdown recente contenuto (>-15%)": lambda e: (e["dd"] or -99) > -15,
    "POSIZIONE: deep recovery (drawdown <-20%)": lambda e: (e["dd"] or 0) < -20,
    "MOMENTUM: rendimento 12 mesi > 0": lambda e: (e["ret12"] or -99) > 0,
    "MOMENTUM: rendimento 6 mesi > 0": lambda e: (e["ret6"] or -99) > 0,
    "MOMENTUM: forza relativa top 30% universo": lambda e: (e["rs_rank"] or -1) >= 0.7,
    "MOMENTUM: forza relativa sopra la mediana": lambda e: (e["rs_rank"] or -1) >= 0.5,
    "VOLATILITÀ: bassa (ATR sotto il 50° pct)": lambda e: (e["atr_pctile"] or 999) < 50,
    "VOLATILITÀ: compressione Bollinger (<40° pct)": lambda e: (e["bbw_pctile"] or 999) < 40,
    "VOLATILITÀ: base stretta prima della rottura": lambda e: (e["base_tight"] or 99) < 1.0,
    "QUALITÀ: rottura non estesa (<1,5 ATR)": lambda e: (e["dist_atr"] or 99) < 1.5,
    "QUALITÀ: nessun incrocio da 6+ mesi": lambda e: (e["giorni_da_incrocio"] or 0) >= 126,
    "QUALITÀ: RSI 45-75": lambda e: 45 <= (e["rsi"] or 0) <= 75,
    "QUALITÀ: chiusura nella parte alta della barra": lambda e: (e["close_pos"] or 0) >= 0.6,
}

COMBINAZIONI = {
    "regime + MM200 in salita": lambda e: (e["mib_above"] is True) and (e["slope20"] or -99) > 0,
    "regime + MM200 in salita + forza relativa ≥50° pct":
        lambda e: (e["mib_above"] is True) and (e["slope20"] or -99) > 0 and (e["rs_rank"] or -1) >= 0.5,
    "regime + MM200 in salita + vicino ai massimi (≥95%)":
        lambda e: (e["mib_above"] is True) and (e["slope20"] or -99) > 0 and (e["prox_high"] or 0) >= 0.95,
    "regime + medie allineate": lambda e: (e["mib_above"] is True) and (e["allineate"] is True),
    "regime + MM200 in salita + bassa volatilità":
        lambda e: (e["mib_above"] is True) and (e["slope20"] or -99) > 0 and (e["atr_pctile"] or 999) < 50,
}


# ---------------------------------------------------------------------------
# valutazione
# ---------------------------------------------------------------------------

def valuta(nome, sel, altri, h=250):
    r_si = vl._pulito([e["rend"].get(h, np.nan) for e in sel])
    r_no = vl._pulito([e["rend"].get(h, np.nan) for e in altri])
    if len(r_si) < 8 or len(r_no) < 8:
        return None
    t, p = vl.welch(r_si, r_no)
    f_si = np.mean([1 if e["fallito21"] else 0 for e in sel]) * 100
    f_no = np.mean([1 if e["fallito21"] else 0 for e in altri]) * 100
    return {
        "filtro": nome,
        "n_si": len(r_si), "n_no": len(r_no),
        "win_si": round(float((r_si > 0).mean() * 100), 1),
        "win_no": round(float((r_no > 0).mean() * 100), 1),
        "medio_si": round(float(r_si.mean()), 2), "medio_no": round(float(r_no.mean()), 2),
        "delta": round(float(r_si.mean() - r_no.mean()), 2),
        "falso_si": round(float(f_si), 1), "falso_no": round(float(f_no), 1),
        "t": round(t, 2) if np.isfinite(t) else None,
        "p": round(p, 4) if np.isfinite(p) else None,
    }


def stabilita(f, eventi):
    """Segno dell'effetto nelle due metà del campione."""
    out = []
    for epoca, sub in (("2005-2014", [e for e in eventi if e["anno"] <= 2014]),
                       ("2015-2026", [e for e in eventi if e["anno"] >= 2015])):
        si = [e for e in sub if _ok(f, e)]
        no = [e for e in sub if not _ok(f, e)]
        r_si = vl._pulito([e["rend"].get(250, np.nan) for e in si])
        r_no = vl._pulito([e["rend"].get(250, np.nan) for e in no])
        out.append(round(float(r_si.mean() - r_no.mean()), 2)
                   if len(r_si) >= 8 and len(r_no) >= 8 else None)
    return out


def _ok(cond, e):
    try:
        return bool(cond(e))
    except Exception:
        return False


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


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Quale filtro rende affidabile la rottura della MM200?")
    ap.add_argument("--dal", default="2005-01-01")
    args = ap.parse_args()

    import yfinance as yf

    tickers = tu.solo_ticker()
    print(f"Scarico la storia completa di {len(tickers)} titoli + FTSE MIB...")
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

    # --- contesto di mercato -------------------------------------------------
    closes = pd.DataFrame({t: d["Close"] for t, d in dati.items()})
    mm_univ = closes.rolling(200, min_periods=150).mean()
    valid = closes.notna() & mm_univ.notna()
    above = (closes > mm_univ) & valid
    breadth = above.sum(axis=1) / valid.sum(axis=1).replace(0, np.nan)

    try:
        idx = yf.download("FTSEMIB.MI", period="max", interval="1d",
                          auto_adjust=True, progress=False)
        if isinstance(idx.columns, pd.MultiIndex):
            idx.columns = idx.columns.get_level_values(0)
        ic = idx["Close"].dropna()
        if len(ic) < 500:
            raise ValueError("storia indice troppo corta")
        i_mm = ind.sma(ic, 200)
        mib_above = (ic > i_mm)
        mib_slope = (i_mm / i_mm.shift(20) - 1) * 100
        print(f"Indice FTSE MIB: storia dal {ic.index[0].date()} al {ic.index[-1].date()}")
    except Exception as ex:
        print(f"Indice non disponibile ({ex}): uso un indice equal-weight dell'universo")
        ew = (closes.pct_change().mean(axis=1)).fillna(0)
        ic = (1 + ew).cumprod()
        i_mm = ind.sma(ic, 200)
        mib_above = (ic > i_mm)
        mib_slope = (i_mm / i_mm.shift(20) - 1) * 100

    contesto = pd.DataFrame(index=closes.index)
    contesto["breadth"] = breadth.reindex(closes.index)
    contesto["mib_above"] = mib_above.reindex(closes.index, method="ffill")
    contesto["mib_slope"] = mib_slope.reindex(closes.index, method="ffill")

    ret12_all = closes / closes.shift(252) - 1
    rank_ret12 = ret12_all.rank(axis=1, pct=True)

    # --- eventi --------------------------------------------------------------
    eventi = []
    for t, df in dati.items():
        eventi += eventi_titolo(df, contesto, rank_ret12, dal=args.dal, ticker=t)
    print(f"\nRotture MM200 analizzate: {len(eventi)} su {len({e['titolo'] for e in eventi})} titoli\n")

    # --- valutazione filtri --------------------------------------------------
    righe = []
    for nome, f in FILTRI.items():
        si = [e for e in eventi if _ok(f, e)]
        no = [e for e in eventi if not _ok(f, e)]
        r = valuta(nome, si, no)
        if r:
            r["stabilita"] = stabilita(f, eventi)
            righe.append(r)
    tab = pd.DataFrame(righe).sort_values("t", ascending=False).reset_index(drop=True)

    print("=" * 132)
    print("CLASSIFICA DEI FILTRI (rendimento a 250 sedute; 'sì' = filtro rispettato, 'no' = resto)")
    print("=" * 132)
    print(f"{'filtro':<50}{'n_sì':>6}{'win_sì':>7}{'win_no':>7}{'medio_sì':>9}{'medio_no':>9}"
          f"{'delta':>7}{'falso_sì':>9}{'falso_no':>9}{'t':>7}{'p':>8}{'  stab.':>12}")
    print("-" * 132)
    for _, r in tab.iterrows():
        st = r["stabilita"]
        st_txt = "".join("+" if (x or 0) > 0 else "-" for x in st if x is not None)
        print(f"{r['filtro'][:49]:<50}{r['n_si']:>6}{r['win_si']:>7.1f}{r['win_no']:>7.1f}"
              f"{r['medio_si']:>9.2f}{r['medio_no']:>9.2f}{r['delta']:>7.2f}"
              f"{r['falso_si']:>9.1f}{r['falso_no']:>9.1f}"
              f"{(r['t'] if r['t'] is not None else float('nan')):>7.2f}"
              f"{(r['p'] if r['p'] is not None else float('nan')):>8.4f}{st_txt:>12}")
    print("\n  legenda: 'falso_sì/no' = % di rotture rientrate sotto la MM200 entro 21 sedute;")
    print("           'stab.' = segno del delta nelle due metà del campione (2005-2014, 2015-2026)")

    # --- combinazioni --------------------------------------------------------
    print("\n" + "=" * 132)
    print("COMBINAZIONI DEI FILTRI MIGLIORI")
    print("=" * 132)
    righe_c = []
    for nome, f in COMBINAZIONI.items():
        si = [e for e in eventi if _ok(f, e)]
        no = [e for e in eventi if not _ok(f, e)]
        r = valuta(nome, si, no)
        if r:
            r["stabilita"] = stabilita(f, eventi)
            righe_c.append(r)
    tabc = pd.DataFrame(righe_c).sort_values("t", ascending=False).reset_index(drop=True)
    print(f"{'combinazione':<52}{'n':>6}{'win%':>7}{'medio%':>9}{'delta':>7}"
          f"{'falso%':>8}{'t':>7}{'p':>8}{'  stab.':>12}")
    print("-" * 132)
    for _, r in tabc.iterrows():
        st = r["stabilita"]
        st_txt = "".join("+" if (x or 0) > 0 else "-" for x in st if x is not None)
        print(f"{r['filtro'][:51]:<52}{r['n_si']:>6}{r['win_si']:>7.1f}{r['medio_si']:>9.2f}"
              f"{r['delta']:>7.2f}{r['falso_si']:>8.1f}"
              f"{(r['t'] if r['t'] is not None else float('nan')):>7.2f}"
              f"{(r['p'] if r['p'] is not None else float('nan')):>8.4f}{st_txt:>12}")

    # --- controllo non sovrapposto sui migliori ------------------------------
    print("\n" + "=" * 132)
    print("CONTROLLO CON FINESTRE NON SOVRAPPOSTE (max 1 evento/titolo/anno)")
    print("=" * 132)
    da_controllare = list(tab.head(4)["filtro"]) + list(tabc.head(2)["filtro"])
    mappa = {**FILTRI, **COMBINAZIONI}
    righe_n = []
    for nome in da_controllare:
        f = mappa[nome]
        si = non_sovrapposti([e for e in eventi if _ok(f, e)])
        no = non_sovrapposti([e for e in eventi if not _ok(f, e)])
        r_si = vl._pulito([e["rend"].get(250, np.nan) for e in si])
        r_no = vl._pulito([e["rend"].get(250, np.nan) for e in no])
        if len(r_si) < 8 or len(r_no) < 8:
            continue
        t, p = vl.welch(r_si, r_no)
        righe_n.append({"filtro": nome, "n_si": len(r_si), "medio_si": round(float(r_si.mean()), 2),
                        "n_no": len(r_no), "medio_no": round(float(r_no.mean()), 2),
                        "t": round(t, 2), "p": round(p, 4)})
        print(f"   {nome[:60]:<61} sì: {r_si.mean():+7.2f}% (n={len(r_si):<4})   "
              f"no: {r_no.mean():+7.2f}% (n={len(r_no):<4})   t={t:+.2f}  p={p:.4f}")

    # --- salvataggi ----------------------------------------------------------
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "filtri_lab.json"), "w", encoding="utf-8") as fh:
        json.dump({"n_eventi": len(eventi), "filtri": tab.to_dict(orient="records"),
                   "combinazioni": tabc.to_dict(orient="records"),
                   "non_sovrapposti": righe_n}, fh, ensure_ascii=False, indent=2, default=str)
    tab.to_csv(os.path.join(OUT_DIR, "filtri_lab_riepilogo.csv"), sep=";", decimal=",",
               encoding="utf-8-sig", index=False)
    print(f"\nSalvati: output/filtri_lab.json e output/filtri_lab_riepilogo.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
