#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCHEDA OPERATIVA — una pagina HTML semplice: cosa fare, cosa aspettare, target
=============================================================================

Genera `output/scheda_operativa.html`: una pagina autonoma (nessuna risorsa
esterna) pensata per essere letta in 30 secondi da telefono o desktop.

Contenuto:
  1. COSA FARE ORA  — i titoli da comprare/mantenere, quote e importi;
  2. TARGET PRICE   — target STATISTICO: mediana (e quartili) dei rendimenti a
                      3/6/12 mesi realizzati storicamente dai titoli selezionati
                      con la stessa regola (top 10 momentum 12-1, sopra MM200,
                      liquidità >= soglia), applicata al prezzo di oggi;
                      NON è un obiettivo di analisti: è la distribuzione storica.
  3. COSA ASPETTARE — data della prossima verifica, condizioni di uscita
                      (MM200 e rank), e i CANDIDATI IN ATTESA: titoli forti ma
                      sotto la MM200, con il prezzo che li attiverebbe.

Uso:
    python3 scheda_operativa.py
    python3 scheda_operativa.py --capitale 25000 --attuale output/portafoglio_attuale.csv
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import titoli_italiani as tu          # noqa: E402
import selezione_oggi as so           # noqa: E402

OUT_DIR = os.path.join(BASE_DIR, "output")
CACHE_LIVE = os.path.join(BASE_DIR, "cache", "scanner_live.pkl")
CACHE_STORICO = os.path.join(BASE_DIR, "cache", "momentum_raw.pkl")


# ---------------------------------------------------------------------------
# 1) statistiche storiche sui titoli selezionati dalla stessa regola
# ---------------------------------------------------------------------------

def _pannelli_da_raw(raw) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Matrici allineate: chiuse mensili, turnover mediano 3m, flag sopra MM200."""
    import indicatori as ind

    chiuse, liq, sopra = {}, {}, {}
    for t in tu.solo_ticker():
        try:
            d = raw[t].dropna(how="all").dropna(subset=["Close"])
        except Exception:
            continue
        if len(d) < 400:
            continue
        c = d["Close"]
        m = c.resample("ME").last()
        chiuse[t] = m
        # turnover mediano giornaliero degli ultimi 3 mesi (a fine di ogni mese)
        tur = (c * d["Volume"]).resample("ME").median()
        liq[t] = tur.rolling(3, min_periods=2).median()
        mm = ind.sma(c, 200)
        sopra[t] = (c > mm).resample("ME").last()

    C = pd.DataFrame(chiuse).sort_index()
    L = pd.DataFrame(liq).reindex(C.index)
    S = pd.DataFrame(sopra).reindex(C.index).fillna(False).astype(bool)
    return C, L, S


def distribuzione_forward(C: pd.DataFrame, L: pd.DataFrame, S: pd.DataFrame,
                          liquidita: float, n: int = 10, dal: str = "2010-01-01",
                          orizzonti=(3, 6, 12), nsim: int = 8):
    """
    Per ogni mese dal 2010, applica la regola (top n momentum 12-1, sopra MM200,
    liquide) e raccoglie il rendimento realizzato nei successivi 3/6/12 mesi.
    Ritorna dict orizzonte -> dict(mediana, q1, q3, prob_pos, n).
    """
    C = C[C.index >= pd.Timestamp(dal)]
    L = L.reindex(C.index)
    S = S.reindex(C.index)
    mesi = list(C.index)
    out = {h: [] for h in orizzonti}

    for i in range(13, len(mesi) - max(orizzonti)):
        r = C.iloc[i - 1] / C.iloc[i - 13] - 1.0          # mom 12-1 fino a i-1
        liq_ok = (L.iloc[i] >= liquidita).fillna(False)
        sopra_ok = S.iloc[i].fillna(False)
        elig = r[(r.notna()) & liq_ok & sopra_ok]
        if len(elig) < n:
            continue
        top = list(elig.sort_values(ascending=False).index[:n])
        for h in orizzonti:
            fut = (C.iloc[i + h] / C.iloc[i] - 1.0) * 100
            out[h].extend([x for x in fut.reindex(top).tolist() if np.isfinite(x)])

    stat = {}
    for h, v in out.items():
        v = np.array(v)
        if v.size < 30:
            continue
        stat[h] = {
            "n": int(v.size),
            "mediana_%": float(np.median(v)),
            "q1_%": float(np.percentile(v, 25)),
            "q3_%": float(np.percentile(v, 75)),
            "prob_pos_%": float((v > 0).mean() * 100),
            "p10_%": float(np.percentile(v, 10)),
        }
    return stat


# ---------------------------------------------------------------------------
# 2) HTML
# ---------------------------------------------------------------------------

def _eur(x: float) -> str:
    return f"{x:,.0f} €".replace(",", ".")


def _num(x: float, dec: int = 2) -> str:
    out = f"{x:,.{dec}f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return out.replace("-", "\u2212")           # segno meno tipografico


def costruisci_html(args, data_dati: str, sel: pd.DataFrame, stat: dict,
                     attesa: pd.DataFrame, prossima: str, n_operazioni: int,
                     nota_fallback: str, data_decisione: str, vendite: list | None = None) -> str:
    n_acquisti = int((sel["azione"] == "COMPRA").sum())
    n_vendite = len(vendite or [])

    def badge(azione: str) -> str:
        col = {"COMPRA": "#0a7d3c", "MANTIENI": "#1d4ed8", "VENDI": "#b91c1c"}.get(azione, "#475569")
        return (f'<span style="background:{col};color:#fff;padding:3px 10px;border-radius:999px;'
                f'font-size:12px;font-weight:700;letter-spacing:.4px">{azione}</span>')

    righe = []
    for _, r in sel.iterrows():
        tgt = r["prezzo"] * (1 + stat.get(12, {}).get("mediana_%", 0) / 100)
        tgt_a = r["prezzo"] * (1 + stat.get(12, {}).get("q1_%", 0) / 100)
        tgt_b = r["prezzo"] * (1 + stat.get(12, {}).get("q3_%", 0) / 100)
        azione = r.get("azione", "COMPRA")
        righe.append(f"""
      <tr>
        <td style="padding:12px 10px;border-bottom:1px solid #e2e8f0">
          <div style="font-weight:700;font-size:16px">{r['nome']}</div>
          <div style="color:#64748b;font-size:12px">{r['ticker'].replace('.MI','')} · rank {int(r['rank'])}</div>
        </td>
        <td style="padding:12px 10px;border-bottom:1px solid #e2e8f0">{badge(azione)}</td>
        <td style="padding:12px 10px;border-bottom:1px solid #e2e8f0;text-align:right">
          <div style="font-weight:700">{_eur(r['eur_effettivi'])}</div>
          <div style="color:#64748b;font-size:12px">{int(r['quote'])} azioni</div>
        </td>
        <td style="padding:12px 10px;border-bottom:1px solid #e2e8f0;text-align:right">
          <div>{_num(r['prezzo'])} €</div>
          <div style="color:#0a7d3c;font-size:12px">+{_num(r['mom_%'],0)}% in 12 mesi</div>
        </td>
        <td style="padding:12px 10px;border-bottom:1px solid #e2e8f0;text-align:right">
          <div style="font-weight:700;font-size:17px">{_num(tgt)} €</div>
          <div style="color:#64748b;font-size:12px">mediana · range {_num(tgt_a)}–{_num(tgt_b)}</div>
        </td>
        <td style="padding:12px 10px;border-bottom:1px solid #e2e8f0;text-align:right">
          <div>{_num(r['livello_uscita'])} €</div>
          <div style="color:#64748b;font-size:12px">MM200</div>
        </td>
      </tr>""")

    righe_attesa = []
    for _, r in attesa.iterrows():
        righe_attesa.append(f"""
      <tr>
        <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0">{r['nome']}
          <span style="color:#64748b;font-size:12px">({r['ticker'].replace('.MI','')})</span></td>
        <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right">+{_num(r['mom_%'],0)}%</td>
        <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right">
          <span style="color:#b45309;font-weight:600">sopra {_num(r['livello_ingresso'])} €</span></td>
      </tr>""")

    blocco_vendite = ""
    if vendite:
        chips = " ".join(f'<span style="display:inline-block;background:#fee2e2;color:#991b1b;border-radius:8px;'
                         f'padding:5px 10px;margin:3px;font-weight:600">{t.replace(".MI", "")}</span>'
                         for t in vendite)
        blocco_vendite = f"""
  <div style="background:#fff;border-radius:12px;padding:18px;margin-top:14px;box-shadow:0 1px 3px rgba(15,23,42,.08)">
    <div style="font-size:13px;letter-spacing:1px;color:#b91c1c;text-transform:uppercase;font-weight:700">Da vendere alla verifica</div>
    <div style="margin:10px 0 4px">{chips}</div>
    <div style="color:#64748b;font-size:13px">Escono perché sono scesi sotto la MM200 o oltre il rank {args.n + args.buffer}:
      vendi <b>alla chiusura del giorno di verifica</b>, non inseguendo il prezzo.</div>
  </div>"""

    s12 = stat.get(12, {})
    s6 = stat.get(6, {})
    blocco_stat = ""
    if s12:
        n_txt = f"{s12['n']:,}".replace(",", ".")
        blocco_stat = (f"<b>Come è calcolato il target:</b> nei test 2010-2026, i titoli scelti con questa "
                       f"stessa regola hanno reso (mediana) <b>+{_num(s6.get('mediana_%', 0), 1)}% in 6 mesi</b> "
                       f"e <b>+{_num(s12['mediana_%'], 1)}% in 12 mesi</b>, con il 50% centrale dei casi fra "
                       f"{_num(s12['q1_%'], 1)}% e +{_num(s12['q3_%'], 1)}%, e risultato positivo nel "
                       f"{_num(s12['prob_pos_%'], 0)}% dei casi su {n_txt} osservazioni.")

    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scheda operativa — cosa fare, cosa aspettare, target</title>
</head>
<body style="margin:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a">
<div style="max-width:980px;margin:0 auto;padding:18px 14px 40px">

  <div style="background:#0f172a;color:#fff;border-radius:14px;padding:20px 22px">
    <div style="font-size:13px;letter-spacing:1px;color:#94a3b8;text-transform:uppercase">Scheda operativa · Piazza Affari</div>
    <div style="font-size:26px;font-weight:800;margin:6px 0 4px">Cosa fare · Cosa aspettare · Target</div>
    <div style="color:#cbd5e1;font-size:14px">
      Dati al <b>{data_dati}</b> · capitale <b>{_eur(args.capitale)}</b> ·
      regola: <b>momentum 12-1, top {args.n}, sopra MM200, buffer {args.buffer}</b>
    </div>
  </div>

  <div style="display:flex;gap:12px;flex-wrap:wrap;margin:14px 0">
    <div style="flex:1 1 200px;background:#fff;border-radius:12px;padding:16px 18px;box-shadow:0 1px 3px rgba(15,23,42,.08)">
      <div style="color:#64748b;font-size:12px;text-transform:uppercase;letter-spacing:.6px">Da fare adesso</div>
      <div style="font-size:22px;font-weight:800;margin-top:4px">{n_operazioni} operazioni</div>
      <div style="color:#64748b;font-size:13px">{"nessuna: portafoglio già allineato" if n_operazioni == 0 else f"{n_acquisti} acquisti · {n_vendite} vendite"}</div>
    </div>
    <div style="flex:1 1 200px;background:#fff;border-radius:12px;padding:16px 18px;box-shadow:0 1px 3px rgba(15,23,42,.08)">
      <div style="color:#64748b;font-size:12px;text-transform:uppercase;letter-spacing:.6px">Cosa aspettare</div>
      <div style="font-size:22px;font-weight:800;margin-top:4px">{prossima}</div>
      <div style="color:#64748b;font-size:13px">prossima verifica · decisione applicata: {data_decisione}</div>
    </div>
    <div style="flex:1 1 200px;background:#fff;border-radius:12px;padding:16px 18px;box-shadow:0 1px 3px rgba(15,23,42,.08)">
      <div style="color:#64748b;font-size:12px;text-transform:uppercase;letter-spacing:.6px">Target atteso a 12 mesi</div>
      <div style="font-size:22px;font-weight:800;margin-top:4px">+{_num(s12.get('mediana_%', 0), 1)}%</div>
      <div style="color:#64748b;font-size:13px">mediana storica, non una promessa</div>
    </div>
  </div>

  <div style="background:#fff;border-radius:12px;padding:18px 18px 6px;box-shadow:0 1px 3px rgba(15,23,42,.08)">
    <div style="font-size:13px;letter-spacing:1px;color:#64748b;text-transform:uppercase;font-weight:700">1 · Cosa fare ora</div>
    <table style="width:100%;border-collapse:collapse;margin-top:8px;font-size:14px">
      <thead>
        <tr style="color:#64748b;font-size:12px;text-transform:uppercase;letter-spacing:.4px">
          <th style="text-align:left;padding:6px 10px">Titolo</th>
          <th style="text-align:left;padding:6px 10px">Azione</th>
          <th style="text-align:right;padding:6px 10px">Importo</th>
          <th style="text-align:right;padding:6px 10px">Prezzo oggi</th>
          <th style="text-align:right;padding:6px 10px">Target 12 mesi</th>
          <th style="text-align:right;padding:6px 10px">Esce sotto</th>
        </tr>
      </thead>
      <tbody>{''.join(righe)}</tbody>
    </table>
    <div style="color:#64748b;font-size:12px;margin:10px 0 14px">
      Pesi uguali (10%). <b>Esce sotto</b> = il prezzo sotto cui il titolo perde il filtro MM200:
      a fine mese, se chiude lì sotto, esce dal portafoglio alla verifica successiva (senza eccezioni).
    </div>
  </div>

  {blocco_vendite}

  <div style="background:#fff;border-radius:12px;padding:18px;margin-top:14px;box-shadow:0 1px 3px rgba(15,23,42,.08)">
    <div style="font-size:13px;letter-spacing:1px;color:#64748b;text-transform:uppercase;font-weight:700">2 · Cosa aspettare</div>
    <ul style="margin:10px 0 0;padding-left:20px;font-size:14px;line-height:1.85">
      <li><b>Nessun ingresso prima della prossima verifica</b> ({prossima}): la regola si applica una volta
          al mese (o al trimestre), non giorno per giorno.</li>
      <li><b>Nessuna vendita</b> finché il titolo resta sopra la MM200 e nel <b>rank ≤ {args.n + args.buffer}</b>
          (buffer {args.buffer}): il buffer esiste per non pagare commissioni sul rumore.</li>
      <li><b>Niente stop, niente overlay</b>: tutti i test dicono che peggiorano il risultato. Il rischio si
          gestisce con i 10 titoli e la size, non con gli stop sulla strategia.</li>
      <li>Se un titolo <b>scivola sotto la MM200</b> a fine mese, esce: vendi alla verifica, non all'intraday.</li>
    </ul>
  </div>

  <div style="background:#fff;border-radius:12px;padding:18px;margin-top:14px;box-shadow:0 1px 3px rgba(15,23,42,.08)">
    <div style="font-size:13px;letter-spacing:1px;color:#64748b;text-transform:uppercase;font-weight:700">3 · In attesa (non comprare ancora)</div>
    <div style="color:#64748b;font-size:13px;margin:8px 0 4px">
      Titoli con momentum alto ma <b>sotto la MM200</b>: entrerebbero in portafoglio solo se il prezzo
      chiude sopra il livello indicato a una verifica mensile.</div>
    <table style="width:100%;border-collapse:collapse;font-size:14px">
      <thead><tr style="color:#64748b;font-size:12px;text-transform:uppercase">
        <th style="text-align:left;padding:6px 10px">Titolo</th>
        <th style="text-align:right;padding:6px 10px">Momentum 12-1</th>
        <th style="text-align:right;padding:6px 10px">Si attiva sopra</th>
      </tr></thead>
      <tbody>{''.join(righe_attesa) if righe_attesa else '<tr><td colspan="3" style="padding:10px;color:#64748b">Nessun candidato sopra la soglia di liquidità</td></tr>'}</tbody>
    </table>
  </div>

  <div style="background:#fff;border-radius:12px;padding:18px;margin-top:14px;box-shadow:0 1px 3px rgba(15,23,42,.08)">
    <div style="font-size:13px;letter-spacing:1px;color:#64748b;text-transform:uppercase;font-weight:700">4 · Target: cosa significa (e cosa no)</div>
    <div style="font-size:14px;line-height:1.7;margin-top:8px">
      <p style="margin:0 0 8px">{blocco_stat}</p>
      <p style="margin:0 0 8px">Il <b>target in tabella</b> è quel +{_num(s12.get('mediana_%',0),1)}% applicato al prezzo di
      oggi; il <b>range</b> è il 25°-75° percentile storico. Non è il prezzo "giusto" stimato da un analista:
      è dove è finito storicamente il 50% centrale dei casi. Un titolo su cinque, storicamente, chiude
      l'anno in perdita.</p>
      <p style="margin:0"><b>Regola d'oro:</b> si esce per <i>regola</i> (MM200 o rank), non perché il prezzo
      ha toccato il target. Il target serve a sapere cosa aspettarsi, non a decidere quando vendere.</p>
    </div>
  </div>

  <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;padding:16px 18px;margin-top:14px;font-size:13px;color:#7c2d12;line-height:1.7">
    <b>Da sapere.</b> Strumento statistico, non consulenza finanziaria. Il momentum ha crash violenti:
    nel periodo testato il portafoglio ha perso fino al <b>−33,7%</b> dal picco (marzo 2020: −24,7% in un mese).
    Costi 0,2% per lato già inclusi nei test; tasse 26% sul capital gain. Rendimenti passati ≠ rendimenti futuri.
    {nota_fallback}
  </div>

  <div style="color:#94a3b8;font-size:12px;text-align:center;margin-top:16px">
    Generata da <code>scheda_operativa.py</code> · regola completa e verifiche: <code>README.md §7.5</code> ·
    istruzioni: <code>GUIDA.md</code>
  </div>
</div>
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Scheda operativa HTML (cosa fare / aspettare / target)")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--buffer", type=int, default=5)
    ap.add_argument("--liquidita", type=float, default=2_000_000)
    ap.add_argument("--capitale", type=float, default=100_000.0)
    ap.add_argument("--attuale", default="", help="CSV del portafoglio attuale (per marcare VENDI)")
    ap.add_argument("--trimestrale", action="store_true")
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "scheda_operativa.html"))
    args = ap.parse_args()

    oggi = pd.Timestamp(datetime.now().date())

    if not os.path.exists(CACHE_LIVE):
        raise SystemExit("Manca cache/scanner_live.pkl: lancia prima `python3 selezione_oggi.py`.")
    raw_live = pd.read_pickle(CACHE_LIVE)
    tab = so.costruisci_tabella(raw_live, oggi)
    if tab.empty:
        raise SystemExit("Nessun titolo con dati sufficienti nella cache live.")

    # portafoglio precedente (per azione COMPRA/MANTIENI/VENDI)
    precedente: list[str] = []
    if args.attuale and os.path.exists(args.attuale):
        try:
            p = pd.read_csv(args.attuale, sep=None, engine="python")
            col = next(c for c in p.columns if "ticker" in c.lower())
            precedente = [str(x).strip() for x in p[col].dropna().tolist()]
        except Exception as e:
            print(f"[avviso] {args.attuale}: {e}")

    scelti, sel_all = so.seleziona(tab, precedente, args.n, args.buffer, args.liquidita)
    sel = sel_all.copy()
    sel["livello_uscita"] = [float(tab.loc[t, "prezzo"] / (1 + tab.loc[t, "dist_mm200_%"] / 100))
                             for t in sel.index]
    sel["azione"] = ["MANTIENI" if t in precedente else "COMPRA" for t in sel.index]
    sel = sel.reset_index()                       # il ticker diventa colonna
    sel["peso_%"] = 100 / len(sel)
    sel["eur_effettivi"] = args.capitale / len(sel)
    sel["quote"] = np.floor(sel["eur_effettivi"] / sel["prezzo"]).astype(int)
    sel["eur_effettivi"] = (sel["quote"] * sel["prezzo"]).round(2)

    # candidati in attesa: liquidi, momentum alto, ma SOTTO la MM200
    liq = tab[tab["turnover_mediano"] >= args.liquidita]
    attesa = liq[~liq["sopra_mm200"]].sort_values("mom_%", ascending=False).head(5).copy()
    attesa = attesa[attesa["mom_%"] > 0]
    attesa["livello_ingresso"] = [float(tab.loc[t, "prezzo"] / (1 + tab.loc[t, "dist_mm200_%"] / 100))
                                  for t in attesa.index]
    attesa = attesa.reset_index()

    # statistiche storiche
    if not os.path.exists(CACHE_STORICO):
        raise SystemExit("Manca cache/momentum_raw.pkl: lancia prima `python3 momentum_risk.py`.")
    raw_st = pd.read_pickle(CACHE_STORICO)
    C, L, S = _pannelli_da_raw(raw_st)
    stat = distribuzione_forward(C, L, S, args.liquidita, n=args.n)

    data_dati = str(tab["ultima_rilevazione"].max())
    # la finestra di formazione si chiude al mese m-1 → la decisione è a fine dell'ultimo mese concluso
    mese_decisione = pd.Timestamp(tab["rif_mom"].iloc[0]) + pd.offsets.MonthEnd(1)
    passo = 3 if args.trimestrale else 1
    prossima = mese_decisione + pd.offsets.BMonthEnd(passo)
    vendite = [t for t in precedente if t not in scelti]
    n_operazioni = len([t for t in scelti if t not in precedente]) + len(vendite)

    html = costruisci_html(args, data_dati, sel, stat, attesa,
                           prossima.strftime("%d/%m/%Y"), n_operazioni, sel_all.attrs.get("nota", ""),
                           mese_decisione.strftime("%d/%m/%Y"), vendite)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Scheda scritta: {args.out}")
    print(f"  {len(sel)} titoli · operazioni: {n_operazioni} · prossima verifica: {prossima.date()}")
    if stat:
        print("  statistiche storiche (mediana / range 25-75 / % positivi):")
        for h in sorted(stat):
            s = stat[h]
            print(f"    {h:>2} mesi: {s['mediana_%']:+6.1f}%  "
                  f"[{s['q1_%']:+6.1f}% … {s['q3_%']:+6.1f}%]  positivi {s['prob_pos_%']:.0f}%  (n={s['n']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
