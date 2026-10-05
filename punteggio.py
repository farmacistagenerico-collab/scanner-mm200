#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUNTEGGIO DI AFFIDABILITÀ — quanto è solido ogni singolo titolo
==============================================================

Una pagina, una domanda: **questo titolo, storicamente, quanto spesso è andato
bene?** E il dato su cui si basa è solido o è basato su pochi casi?

Metodo (semplice e verificabile):

  1. si prendono TUTTI i titoli selezionati dalla regola operativa dal 2010
     (top 10 momentum 12-1, sopra MM200, liquidi ≥ 2 M€/giorno): 1.570 posizioni;
  2. si guarda come è finita ciascuna posizione dopo 12 mesi (positiva/negativa);
  3. un modello logistico con 3 caratteristiche osservabili il giorno della
     scelta — momentum relativo nel paniere, distanza dalla MM200, volatilità —
     stima la probabilità di esito positivo → **punteggio 0-100**;
  4. validazione **walk-forward**: per ogni caso storico il modello è stato
     ri-stimato solo con i dati precedenti, quindi le percentuali che vedi sono
     quelle che avresti ottenuto operando davvero.
  5. accanto al punteggio: **affidabilità del dato** = quanti casi storici simili
     esistono (guardando momentum e distanza dalla MM200 del titolo).

Interpretazione: punteggio 75 = nei casi simili del passato, circa 3 su 4 hanno
chiuso positivi a 12 mesi. Non è una previsione: è una frequenza condizionata.

Uso:
    python3 punteggio.py               # calcola, valida, scrive la pagina
    python3 punteggio.py --dettaglio   # mostra anche coefficienti e tabelle
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.optimize import minimize

warnings.filterwarnings("ignore")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import titoli_italiani as tu      # noqa: E402
import indicatori as ind          # noqa: E402
import selezione_oggi as so       # noqa: E402
import grafici as gr              # noqa: E402
import indicatori as ind          # noqa: E402

OUT_DIR = os.path.join(BASE_DIR, "output")
CACHE_LIVE = os.path.join(BASE_DIR, "cache", "scanner_live.pkl")
CACHE_STORICO = os.path.join(BASE_DIR, "cache", "momentum_raw.pkl")

LIQ = 2_000_000.0
N_TITOLI = 10
ORIZZONTE = 12          # mesi
RIDGE = 2e-4            # regolarizzazione (tiene piccoli i coefficienti)
RIFIT = 6               # ri-stima del modello ogni N casi nel walk-forward
FEATURES = ["rk", "dist_%", "vol_%"]
NOMI_FEATURE = {"rk": "momentum relativo nel paniere", "dist_%": "distanza dalla MM200",
                "vol_%": "volatilità"}


# ---------------------------------------------------------------------------
# 1) dati storici e casi (posizioni della regola con esito a 12 mesi)
# ---------------------------------------------------------------------------

def pannelli_storici(raw):
    chiuse, liq, dist, vol = {}, {}, {}, {}
    for t in tu.solo_ticker():
        try:
            d = raw[t].dropna(how="all").dropna(subset=["Close"])
        except Exception:
            continue
        if len(d) < 400:
            continue
        c = d["Close"]
        chiuse[t] = c.resample("ME").last()
        liq[t] = (c * d["Volume"]).resample("ME").median().rolling(3, min_periods=2).median()
        mm = ind.sma(c, 200)
        dist[t] = ((c / mm - 1) * 100).resample("ME").last()
        vol[t] = (c.pct_change().rolling(21).std() * np.sqrt(252) * 100).resample("ME").last()

    C = pd.DataFrame(chiuse).sort_index()
    return (C, pd.DataFrame(liq).reindex(C.index), pd.DataFrame(dist).reindex(C.index),
            pd.DataFrame(vol).reindex(C.index))


def casi_storici(C, L, D, V, dal="2010-01-01") -> pd.DataFrame:
    """Ogni posizione della regola con le sue caratteristiche e l'esito a 12 mesi."""
    C = C[C.index >= pd.Timestamp(dal)]
    L, D, V = L.reindex(C.index), D.reindex(C.index), V.reindex(C.index)
    mesi = list(C.index)
    fwd = (C.shift(-ORIZZONTE) / C - 1) * 100
    righe = []
    for i in range(13, len(mesi) - ORIZZONTE):
        mom = C.iloc[i - 1] / C.iloc[i - 13] - 1
        elig = mom[(mom.notna()) & (L.iloc[i] >= LIQ).fillna(False) & (D.iloc[i] > 0).fillna(False)]
        if len(elig) < N_TITOLI:
            continue
        rk = elig.rank(pct=True) * 100
        for t in elig.sort_values(ascending=False).index[:N_TITOLI]:
            esito = fwd.iloc[i].get(t, np.nan)
            if not np.isfinite(esito):
                continue
            righe.append({"mese": mesi[i], "ticker": t,
                          "mom_%": float(mom[t] * 100), "rk": float(rk[t]),
                          "dist_%": float(D.iloc[i][t]),
                          "vol_%": float(V.iloc[i][t]) if np.isfinite(V.iloc[i][t]) else np.nan,
                          "esito_12m_%": float(esito), "positivo": int(esito > 0)})
    o = pd.DataFrame(righe).sort_values("mese").reset_index(drop=True)
    o["vol_%"] = o["vol_%"].fillna(o["vol_%"].median())
    return o


# ---------------------------------------------------------------------------
# 2) modello logistico (numpy/scipy) + walk-forward
# ---------------------------------------------------------------------------

def _fit(X: np.ndarray, y: np.ndarray):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1
    Z = np.column_stack([np.ones(len(X)), (X - mu) / sd])

    def costo(b):
        z = np.clip(Z @ b, -30, 30)
        return float(np.sum(np.log1p(np.exp(z)) - y * z) + RIDGE * np.sum(b[1:] ** 2))

    b = minimize(costo, np.zeros(Z.shape[1]), method="L-BFGS-B").x
    return b, mu, sd


def _pred(b, mu, sd, X: np.ndarray) -> np.ndarray:
    Z = np.column_stack([np.ones(len(X)), (np.atleast_2d(X) - mu) / sd])
    return 1 / (1 + np.exp(-np.clip(Z @ b, -30, 30)))


def walk_forward(oss: pd.DataFrame) -> pd.DataFrame:
    """Punteggio per ogni caso storico, usando solo il passato (nessun look-ahead)."""
    X = oss[FEATURES].values.astype(float)
    y = oss["positivo"].values.astype(float)
    p = np.full(len(oss), np.nan)
    modello = None
    for i in range(len(oss)):
        if modello is None or i % RIFIT == 0:
            if i >= 250:
                modello = _fit(X[:i], y[:i])
        if modello is not None:
            p[i] = _pred(*modello, X[i:i + 1])[0]
    oss = oss.copy()
    oss["punteggio"] = p * 100
    return oss


def tabella_validazione(oss: pd.DataFrame, dal_oos="2018-01-01") -> tuple[pd.DataFrame, float]:
    o = oss[(oss["mese"] >= pd.Timestamp(dal_oos)) & oss["punteggio"].notna()].copy()
    o["fascia"] = pd.qcut(o["punteggio"], 3, labels=["basso", "medio", "alto"])
    tab = o.groupby("fascia", observed=True).agg(
        da=("punteggio", "min"), a=("punteggio", "max"),
        casi=("positivo", "size"), positivi=("positivo", "mean"),
        mediana=("esito_12m_%", "median")).reset_index()
    tab["positivi"] = (tab["positivi"] * 100).round(1)
    tab["mediana"] = tab["mediana"].round(1)
    tab["da"], tab["a"] = tab["da"].round(0), tab["a"].round(0)
    return tab, float(o["positivo"].mean() * 100)


def spread_portafoglio(oss: pd.DataFrame, dal_oos="2018-01-01") -> tuple[float, float]:
    """Dentro ogni portafoglio mensile: terzo con punteggio alto vs basso."""
    o = oss[(oss["mese"] >= pd.Timestamp(dal_oos)) & oss["punteggio"].notna()].copy()
    o["fascia"] = o.groupby("mese")["punteggio"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 3, labels=["basso", "medio", "alto"]))
    g = o.groupby("fascia", observed=True)["positivo"].mean() * 100
    return float(g.get("alto", np.nan)), float(g.get("basso", np.nan))


# ---------------------------------------------------------------------------
# 3) punteggio del portafoglio di oggi
# ---------------------------------------------------------------------------

def affidabilita_gruppi(oss: pd.DataFrame, confini_mom, confini_dist) -> dict:
    gm = pd.cut(oss["mom_%"], [-np.inf, *confini_mom, np.inf],
                labels=["momentum moderato", "momentum alto", "momentum estremo"])
    gd = pd.cut(oss["dist_%"], [-np.inf, *confini_dist, np.inf],
                labels=["vicino alla MM200", "sopra la MM200", "staccato dalla MM200"])
    g = gm.astype(str) + " · " + gd.astype(str)
    return g.value_counts().to_dict()


def punteggio_oggi(tab: pd.DataFrame, oss: pd.DataFrame,
                   universo: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Modello stimato su tutti i casi; applicato ai titoli indicati.

    `universo` serve per il momentum relativo nel paniere (percentile fra TUTTI i
    titoli liquidi sopra la MM200, come nel modello): senza, il percentile verrebbe
    calcolato sul sottoinsieme passato e i punteggi risulterebbero gonfiati.
    """
    X = oss[FEATURES].values.astype(float)
    y = oss["positivo"].values.astype(float)
    b, mu, sd = _fit(X, y)

    # affidabilità del dato: casi storici nel gruppo del titolo
    confini_mom = [float(oss["mom_%"].quantile(1 / 3)), float(oss["mom_%"].quantile(2 / 3))]
    confini_dist = [float(oss["dist_%"].quantile(1 / 3)), float(oss["dist_%"].quantile(2 / 3))]
    n_gruppi = affidabilita_gruppi(oss, confini_mom, confini_dist)
    med_globale = float(oss["esito_12m_%"].median())

    base = tab if universo is None else universo
    liq = base[base["turnover_mediano"] >= LIQ]
    elig = liq[liq["sopra_mm200"]]
    rk = (elig["mom_%"].rank(pct=True) * 100)

    righe = []
    for t in tab.index:
        r = tab.loc[t]
        feats = np.array([[float(rk.get(t, 50.0)), float(r["dist_mm200_%"]),
                           float(r["vol_annua_%"]) if np.isfinite(r["vol_annua_%"]) else float(oss["vol_%"].median())]])
        p = float(_pred(b, mu, sd, feats)[0] * 100)
        gm = pd.cut([r["mom_%"]], [-np.inf, *confini_mom, np.inf],
                    labels=["momentum moderato", "momentum alto", "momentum estremo"])[0]
        gd = pd.cut([r["dist_mm200_%"]], [-np.inf, *confini_dist, np.inf],
                    labels=["vicino alla MM200", "sopra la MM200", "staccato dalla MM200"])[0]
        gruppo = f"{gm} · {gd}"
        n = int(n_gruppi.get(gruppo, 0))
        # mediana dell'esito nel gruppo storico (se il gruppo è piccolo si usa la mediana globale)
        gm_h = pd.cut(oss["mom_%"], [-np.inf, *confini_mom, np.inf],
                      labels=["momentum moderato", "momentum alto", "momentum estremo"]).astype(str)
        gd_h = pd.cut(oss["dist_%"], [-np.inf, *confini_dist, np.inf],
                      labels=["vicino alla MM200", "sopra la MM200", "staccato dalla MM200"]).astype(str)
        sub = oss[(gm_h == str(gm)) & (gd_h == str(gd))]
        if len(sub) >= 30:
            med = float(sub["esito_12m_%"].median())
        else:
            sub2 = oss[gm_h == str(gm)]
            med = float(sub2["esito_12m_%"].median()) if len(sub2) >= 30 else med_globale
        affid = "alta" if n >= 200 else ("media" if n >= 80 else "bassa")
        righe.append({"ticker": t, "nome": r["nome"], "prezzo": float(r["prezzo"]),
                      "punteggio": round(p, 1), "gruppo": gruppo, "casi_simili": n,
                      "affidabilita": affid, "mediana_12m_%": round(med, 1),
                      "livello_uscita": float(r["prezzo"] / (1 + r["dist_mm200_%"] / 100))})
    out = pd.DataFrame(righe).set_index("ticker")
    return out.sort_values("punteggio", ascending=False)


# ---------------------------------------------------------------------------
# 4) pagina
# ---------------------------------------------------------------------------

def _num(x, dec=1):
    out = f"{x:,.{dec}f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return out.replace("-", "\u2212")


def scrivi_html(path, data_dati, verdetto, righe: pd.DataFrame, val: pd.DataFrame,
                base_rate: float, calib: float, spread_ptf: tuple, n_casi: int):
    def col(p):
        return "#0a7d3c" if p >= 72 else ("#b45309" if p >= 62 else "#b91c1c")

    def etichetta(p):
        return "ALTA" if p >= 72 else ("MEDIA" if p >= 62 else "BASSA")

    trs = []
    for _, r in righe.iterrows():
        atteso = r["prezzo"] * (1 + r["mediana_12m_%"] / 100)
        trs.append(f"""
  <div class="scheda"><div class="griglia">
    <div style="flex:0 0 auto;min-width:180px">
      <div style="font-weight:800;font-size:17px">{r['nome']}</div>
      <div style="color:#64748b;font-size:12px">{r.name.replace('.MI','')} · esce sotto
        <b>{_num(r['livello_uscita'],2)} €</b></div>
      <div style="margin-top:8px">
        <span style="font-size:27px;font-weight:900;color:{col(r['punteggio'])}">{_num(r['punteggio'],0)}</span>
        <span style="color:{col(r['punteggio'])};font-weight:800;font-size:11px">&nbsp;{etichetta(r['punteggio'])}</span>
        <div style="background:#e2e8f0;border-radius:999px;height:6px;margin-top:5px;width:150px;overflow:hidden">
          <div style="width:{min(max(r['punteggio'],0),100)}%;height:6px;background:{col(r['punteggio'])}"></div></div>
        <div style="color:#64748b;font-size:11.5px;margin-top:5px">affidabilità {r['affidabilita'].upper()} ·
          {int(r['casi_simili'])} casi simili</div>
      </div>
    </div>
    <div style="flex:1 1 300px;min-width:250px">{r.get('grafico','') or ''}</div>
    <div style="flex:0 0 auto;min-width:150px;text-align:right">
      <div style="font-weight:800;font-size:17px">{_num(r['prezzo'],2)} €</div>
      <div style="color:#64748b;font-size:12px;margin-top:6px">atteso 12 mesi</div>
      <div style="font-weight:700">{_num(atteso, 2)} €</div>
      <div style="color:#64748b;font-size:12px">{_num(r['mediana_12m_%'],1)}% mediano</div>
    </div>
  </div></div>""")

    val_trs = []
    for _, r in val.iterrows():
        val_trs.append(f"""<tr>
        <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0">{int(r['da'])}–{int(r['a'])}</td>
        <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right">{int(r['casi'])}</td>
        <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right"><b>{_num(r['positivi'],1)}%</b></td>
        <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right">{_num(r['mediana'],1)}%</td>
      </tr>""")

    alto, basso = spread_ptf
    return f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Punteggio di affidabilità — {data_dati}</title>
<style>
  svg {{ max-width: 100%; height: auto; display: block; }}
  .griglia {{ display: flex; flex-wrap: wrap; gap: 14px; align-items: center; }}
  .scheda {{ background:#fff; border-radius:12px; margin-bottom:10px; padding:14px 16px;
            box-shadow:0 1px 3px rgba(15,23,42,.08); }}
</style></head>
<body style="margin:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a">
<div style="max-width:880px;margin:0 auto;padding:16px 12px 36px">

  <div style="background:#0f172a;color:#fff;border-radius:14px;padding:20px">
    <div style="font-size:12px;letter-spacing:1.2px;text-transform:uppercase;color:#94a3b8">
      Piazza Affari · dati al {data_dati}</div>
    <div style="font-size:26px;font-weight:900;margin:8px 0 4px">{verdetto}</div>
    <div style="color:#cbd5e1;font-size:14px">
      Punteggio = probabilità storica di chiusura positiva a 12 mesi per questo titolo.</div>
  </div>

  <div style="margin-top:14px">{''.join(trs)}</div>

  <div style="background:#fff;border-radius:12px;padding:16px 18px;margin-top:14px;box-shadow:0 1px 3px rgba(15,23,42,.08)">
    <div style="font-size:13px;letter-spacing:1px;color:#64748b;text-transform:uppercase;font-weight:700">
      Il punteggio funziona davvero? (verifica fuori campione 2018-2026)</div>
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:8px">
      <thead><tr style="color:#64748b;font-size:11px;text-transform:uppercase">
        <th style="text-align:left;padding:7px 10px">Punteggio</th>
        <th style="text-align:right;padding:7px 10px">Casi</th>
        <th style="text-align:right;padding:7px 10px">Esiti positivi</th>
        <th style="text-align:right;padding:7px 10px">Rend. mediano 12m</th>
      </tr></thead>
      <tbody>{''.join(val_trs)}</tbody>
    </table>
    <div style="color:#64748b;font-size:12px;margin-top:8px;line-height:1.7">
      Modello stimato <b>solo sul passato</b> di ogni caso (walk-forward), quindi questi numeri sono out-of-sample.
      Media generale: <b>{_num(base_rate,1)}%</b> di esiti positivi su {n_casi:,} posizioni dal 2010.
      Calibrazione: il modello prevede in media <b>{_num(calib,1)}%</b> contro il <b>{_num(base_rate,1)}%</b> realizzato.
      Dentro lo stesso portafoglio mensile, il terzo di titoli col punteggio più alto ha chiuso positivo nel
      <b>{_num(alto,1)}%</b> dei casi contro <b>{_num(basso,1)}%</b> del terzo col punteggio più basso.
    </div>
  </div>

  <div style="background:#fff;border-radius:12px;padding:16px 18px;margin-top:14px;box-shadow:0 1px 3px rgba(15,23,42,.08);font-size:13px;line-height:1.8;color:#334155">
    <b>Come si legge, in 3 righe</b>
    <ol style="margin:8px 0 0;padding-left:20px">
      <li><b>Punteggio</b>: 70 significa che nei casi simili del passato circa 7 su 10 hanno chiuso positivi a
          12 mesi. Verde ≥ 72, giallo 62-71, rosso &lt; 62.</li>
      <li><b>Affidabilità del dato</b>: su quanti casi storici simili (per momentum e distanza dalla MM200) è
          costruito il punteggio. <b>Alta</b> ≥ 200 casi, <b>media</b> 80-199, <b>bassa</b> &lt; 80: con
          affidabilità bassa il punteggio viene tirato verso la media proprio per non illudere.</li>
      <li><b>Atteso a 12 mesi</b>: mediana storica del gruppo applicata al prezzo di oggi. Si esce per regola
          (sotto la MM200 o fuori dal rank), mai perché è stato toccato un obiettivo.</li>
      <li><b>Cosa alza il punteggio</b>: titoli meno estremi — momentum relativo non ai massimi, prezzo non
          troppo staccato dalla MM200, volatilità contenuta (i tre coefficienti del modello sono tutti
          negativi sul valore grezzo). I casi più violenti del passato, a sorpresa, sono quelli dei titoli
          più "caldi".</li>
    </ol>
  </div>

  <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;padding:14px 16px;margin-top:14px;font-size:12.5px;color:#7c2d12;line-height:1.7">
    Il punteggio misura la frequenza storica di successo, non la certezza: anche nei gruppi migliori circa
    3 casi su 10 sono andati male, e nel 2020 il portafoglio ha perso il 24,7% in un mese. Non è consulenza
    finanziaria. Dettagli: <code>README.md §7.5</code> · istruzioni: <code>GUIDA.md</code>.
  </div>
</div></body></html>"""


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Punteggio statistico di affidabilità per titolo")
    ap.add_argument("--dettaglio", action="store_true", help="mostra coefficienti e tabelle interne")
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "punteggio.html"))
    args = ap.parse_args()

    for f in (CACHE_STORICO, CACHE_LIVE):
        if not os.path.exists(f):
            raise SystemExit(f"Manca {f}: lancia prima momentum_risk.py e selezione_oggi.py.")

    C, L, D, V = pannelli_storici(pd.read_pickle(CACHE_STORICO))
    oss = casi_storici(C, L, D, V)
    if len(oss) < 300:
        raise SystemExit("Troppi pochi casi storici.")

    oss = walk_forward(oss)
    val, base_rate_oos = tabella_validazione(oss)
    base_rate = float(oss["positivo"].mean() * 100)
    spread_ptf = spread_portafoglio(oss)

    # calibrazione: media prevista (walk-forward) vs realizzata
    oos = oss[(oss["mese"] >= pd.Timestamp("2018-01-01")) & oss["punteggio"].notna()]
    calib = float(oos["punteggio"].mean())

    tab_live = so.costruisci_tabella(pd.read_pickle(CACHE_LIVE), pd.Timestamp(datetime.now().date()))
    tab_live["livello_mm200"] = tab_live["prezzo"] / (1 + tab_live["dist_mm200_%"] / 100)
    tab_live["margin_%"] = tab_live["dist_mm200_%"]
    att = os.path.join(OUT_DIR, "portafoglio_attuale.csv")
    tenuti: list[str] = []
    if os.path.exists(att):
        p = pd.read_csv(att, sep=None, engine="python")
        col = next(c for c in p.columns if "ticker" in c.lower())
        tenuti = [str(x).strip() for x in p[col].dropna().tolist()]
    tenuti = [t for t in (tenuti or []) if t in tab_live.index]
    if not tenuti:
        _, sel = so.seleziona(tab_live, [], N_TITOLI, 5, LIQ)
        tenuti = list(sel.index)

    righe = punteggio_oggi(tab_live.loc[tenuti], oss, universo=tab_live)

    # grafici: ultimi 200 punti di prezzo + MM200 per ogni titolo
    raw_live = pd.read_pickle(CACHE_LIVE)
    grafici = {}
    for t in righe.index:
        try:
            c = raw_live[t].dropna(subset=["Close"])["Close"]
            mm = ind.sma(c, 200)
            grafici[t] = gr.grafico_prezzo(
                righe.loc[t, "nome"], righe.loc[t, "punteggio"], c.index[-200:], c.values[-200:],
                mm.values[-200:], righe.loc[t, "livello_uscita"],
                righe.loc[t, "prezzo"] * (1 + righe.loc[t, "mediana_12m_%"] / 100))
        except Exception:
            grafici[t] = ""
    righe["grafico"] = pd.Series(grafici)

    import operativita_oggi as oo
    stato = oo.verifica_stato(pd.Timestamp(datetime.now().date()), False, tab_live, {}, tenuti, N_TITOLI, 5)
    if stato["oggi_verifica"]:
        verdetto = "È il momento della verifica: applica la regola per il mese nuovo"
    elif stato["sotto"] or stato["fuori_rank"]:
        verdetto = "Attenzione: qualche titolo è fuori regola (si decide a fine mese)"
    else:
        verdetto = "Oggi non devi fare nulla"

    html = scrivi_html(args.out, str(tab_live["ultima_rilevazione"].max()), verdetto, righe, val,
                       base_rate, calib, spread_ptf, len(oss))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    righe.to_csv(os.path.join(OUT_DIR, "punteggio_oggi.csv"), sep=";", decimal=",",
                 encoding="utf-8-sig")

    X = oss[FEATURES].values.astype(float)
    b, mu, sd = _fit(X, oss["positivo"].values.astype(float))
    print(f"Pagina: {args.out}")
    print(f"  casi storici: {len(oss)} · esiti positivi: {base_rate:.1f}% · "
          f"previsto (walk-forward, OOS): {calib:.1f}% vs realizzato {base_rate_oos:.1f}%")
    print("\nPunteggi di oggi:")
    for _, r in righe.iterrows():
        print(f"  {r['punteggio']:5.1f}  {r['nome'][:28]:30s} affidabilità {r['affidabilita']:5s} "
              f"({int(r['casi_simili']):4d} casi) · atteso 12m {r['mediana_12m_%']:+5.1f}% · "
              f"esce sotto {r['livello_uscita']:.2f} €")
    print("\nValidazione walk-forward (2018-2026):")
    print(val[["fascia", "da", "a", "casi", "positivi", "mediana"]].to_string(index=False))
    print(f"  dentro il portafoglio: alto {spread_ptf[0]:.1f}% vs basso {spread_ptf[1]:.1f}% di esiti positivi")
    if args.dettaglio:
        print("\nCoefficienti (caratteristiche standardizzate):")
        for i, nome in enumerate(FEATURES):
            print(f"  {NOMI_FEATURE[nome]:32s} {b[i + 1]:+.3f}")
        print("  (segno + = aumenta la probabilità, − = la riduce)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
