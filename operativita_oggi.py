#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OPERATIVITÀ DI OGGI — la risposta alla domanda "oggi cosa faccio?"
==================================================================

Un cruscotto giornaliero, non un nuovo segnale. La strategia validata è
mensile: nei 20 giorni di borsa intermedi la risposta corretta è quasi sempre
"non fare nulla". Questa pagina dice *esattamente* quando non fare nulla e
quando invece c'è qualcosa da fare, senza richiedere interpretazioni.

Verdetto in cima, uno dei quattro casi:
  1. OGGI È IL GIORNO DELLA VERIFICA  → lancia selezione_oggi.py ed esegui
  2. QUALCOSA È SOTTO IL LIVELLO DI USCITA → attenzione, deciderà a fine mese
  3. CANDIDATI VICINI ALL'ATTIVAZIONE → solo da guardare, non si compra ora
  4. NON FARE NULLA → nessuna condizione operativa oggi

Contenuto della pagina:
  - verdetto + giorni di borsa alla prossima verifica
  - portafoglio riga per riga: prezzo, livello di uscita (MM200), margine,
    rank attuale, semaforo (verde/giallo/rosso)
  - candidati in attesa: quanto manca al prezzo di attivazione
  - contesto di mercato (breadth, FTSE MIB vs MM200, rotture recenti)
    etichettato per quello che è: CONTESTO, non segnale operativo
  - checklist quotidiana in 3 punti

Uso:
    python3 operativita_oggi.py                       # dati freschi, verdetto a video
    python3 operativita_oggi.py --no-download         # riusa la cache
    python3 operativita_oggi.py --attuale output/portafoglio_attuale.csv
    python3 operativita_oggi.py --solo-verdetto       # una riga, per notifiche

Output: `output/operativita_oggi.html` (pagina autonoma) + stampa a video.
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
import indicatori as ind              # noqa: E402
import selezione_oggi as so           # noqa: E402

OUT_DIR = os.path.join(BASE_DIR, "output")


def _num(x: float, dec: int = 2) -> str:
    out = f"{x:,.{dec}f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return out.replace("-", "\u2212")


def _eur(x: float) -> str:
    return f"{x:,.0f} €".replace(",", ".")


# ---------------------------------------------------------------------------
# dati e stato
# ---------------------------------------------------------------------------

def stato_giorno(raw, oggi: pd.Timestamp, liquidita: float, n: int, buffer: int):
    tab = so.costruisci_tabella(raw, oggi)
    tab["livello_mm200"] = tab["prezzo"] / (1 + tab["dist_mm200_%"] / 100)
    tab["margin_%"] = (tab["prezzo"] / tab["livello_mm200"] - 1) * 100

    elig = tab[(tab["turnover_mediano"] >= liquidita) & tab["sopra_mm200"]].sort_values(
        "mom_%", ascending=False)
    rank = {t: i + 1 for i, t in enumerate(elig.index)}

    # rotture MM200 negli ultimi 5 giorni di borsa + breadth + regime
    rotture, sopra_cnt, tot_cnt = [], 0, 0
    for t in tu.solo_ticker():
        try:
            d = raw[t].dropna(subset=["Close"])
        except Exception:
            continue
        c = d["Close"]
        if len(c) < 260:
            continue
        s = ind.sma(c, 200)
        st = (c > s).dropna()
        if len(st) < 6:
            continue
        tot_cnt += 1
        sopra_cnt += int(bool(st.iloc[-1]))
        if not st.iloc[-6] and st.iloc[-5:].any():      # incrocio in su nelle ultime 5 sedute
            rotture.append(t)

    breadth = 100 * sopra_cnt / tot_cnt if tot_cnt else np.nan
    regime = None
    try:
        cm = raw[tu.BENCHMARK].dropna(subset=["Close"])["Close"]
        regime = bool(cm.iloc[-1] > ind.sma(cm, 200).iloc[-1])
    except Exception:
        pass

    data_ultima = tab["ultima_rilevazione"].max()
    return tab, rank, breadth, regime, rotture, data_ultima


def verifica_stato(oggi: pd.Timestamp, trimestrale: bool, tab: pd.DataFrame,
                   rank: dict, tenuti: list[str], n: int, buffer: int):
    """Determina il verdetto del giorno e la prossima data di verifica."""
    off = pd.offsets.BQuarterEnd if trimestrale else pd.offsets.BMonthEnd
    prossima = oggi + off(0)
    ultima = oggi - off(1)
    giorni_borsa = max(int(len(pd.bdate_range(oggi, prossima))) - 1, 0)
    # è giorno di verifica se chiude oggi il periodo, oppure se la chiusura è avvenuta da poco
    oggi_verifica = (prossima == oggi) or ((oggi - ultima).days <= 3)

    sotto, vicini_uscita, fuori_rank = [], [], []
    for t in tenuti:
        if t not in tab.index:
            continue
        r = tab.loc[t]
        if not bool(r["sopra_mm200"]):
            sotto.append(t)
        elif float(r.get("margin_%", r.get("dist_mm200_%", 99.0))) < 3:
            vicini_uscita.append(t)
        if t not in rank:
            fuori_rank.append(t)
        elif rank[t] > n + buffer:
            fuori_rank.append(t)

    return {
        "prossima": prossima, "giorni_borsa": giorni_borsa, "oggi_verifica": oggi_verifica,
        "ultima": ultima,
        "sotto": sotto, "vicini_uscita": vicini_uscita, "fuori_rank": fuori_rank,
    }


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def costruisci_html(args, data_ultima, tab: pd.DataFrame, tenuti: list[str], rank: dict,
                    stato: dict, attesa: pd.DataFrame, breadth, regime, rotture,
                    perf: float = float("nan")) -> str:
    if stato["oggi_verifica"]:
        quando = ("chiude oggi" if stato["prossima"] == stato.get("_oggi")
                  else f"chiusura del {stato['ultima'].strftime('%d/%m/%Y')}")
        bg, titolo, sottot = "#b45309", "È IL MOMENTO DELLA VERIFICA", \
            f"{quando}: esegui <code>python3 selezione_oggi.py --attuale output/portafoglio_attuale.csv</code> e applica le operazioni"
    elif stato["sotto"] or stato["fuori_rank"]:
        bg, titolo, sottot = "#b91c1c", "ATTENZIONE — TITOLI FUORI REGOLA", \
            "se restano così a fine mese, escono dal portafoglio: non agire oggi"
    elif stato["vicini_uscita"]:
        bg, titolo, sottot = "#0f766e", "NESSUN ORDINE — SOLO DA OSSERVARE", \
            "alcuni titoli sono vicini al livello di uscita: si decide a fine mese"
    else:
        bg, titolo, sottot = "#0a7d3c", "OGGI NON DEVI FARE NULLA", \
            "nessuna condizione operativa è attiva"

    def semaforo(r) -> tuple[str, str]:
        if not bool(r["sopra_mm200"]):
            return "#b91c1c", "SOTTO MM200"
        if r["margin_%"] < 3:
            return "#b45309", "VICINO AL LIMITE"
        return "#0a7d3c", "REGOLARE"

    righe = []
    for t in tenuti:
        if t not in tab.index:
            continue
        r = tab.loc[t]
        col, lab = semaforo(r)
        rk = rank.get(t)
        rank_txt = f"rank {rk}" if rk else "fuori dai 15"
        righe.append(f"""
      <tr>
        <td style="padding:11px 10px;border-bottom:1px solid #e2e8f0">
          <div style="font-weight:700">{r['nome']}</div>
          <div style="color:#64748b;font-size:12px">{t.replace('.MI','')} · {rank_txt}</div>
        </td>
        <td style="padding:11px 10px;border-bottom:1px solid #e2e8f0;text-align:right">{_num(r['prezzo'])} €</td>
        <td style="padding:11px 10px;border-bottom:1px solid #e2e8f0;text-align:right">
          {_num(r['livello_mm200'])} €<div style="color:#64748b;font-size:12px">uscita</div></td>
        <td style="padding:11px 10px;border-bottom:1px solid #e2e8f0;text-align:right">
          <span style="color:{col};font-weight:700">{"+" if r['margin_%'] >= 0 else ""}{_num(r['margin_%'],1)}%</span></td>
        <td style="padding:11px 10px;border-bottom:1px solid #e2e8f0;text-align:right">
          <span style="background:{col};color:#fff;padding:3px 9px;border-radius:999px;font-size:11px;font-weight:700">{lab}</span></td>
      </tr>""")

    righe_attesa = []
    for _, r in attesa.iterrows():
        righe_attesa.append(f"""
      <tr>
        <td style="padding:9px 10px;border-bottom:1px solid #e2e8f0">{r['nome']}
          <span style="color:#64748b;font-size:12px">({r['ticker'].replace('.MI','')})</span></td>
        <td style="padding:9px 10px;border-bottom:1px solid #e2e8f0;text-align:right">{_num(r['prezzo'])} €
          <span style="color:#64748b;font-size:12px">ora</span></td>
        <td style="padding:9px 10px;border-bottom:1px solid #e2e8f0;text-align:right">
          <b>{_num(r['livello_ingresso'])} €</b> <span style="color:#b45309">(+{_num(r['distanza_attivazione_%'],1)}%)</span></td>
      </tr>""")

    mib_txt = ("sopra" if regime else "sotto") if regime is not None else "n/d"
    mib_col = "#0a7d3c" if regime else "#b45309"
    elenco_rotture = ", ".join([t.replace(".MI", "") for t in rotture[:12]]) or "nessuna"
    nota_fuori = ""
    if stato["fuori_rank"]:
        nota_fuori = ("<li><b>Fuori dal rank " + str(args.n + args.buffer) + ":</b> " +
                      ", ".join([t.replace('.MI', '') for t in stato["fuori_rank"]]) +
                      " — se restano fuori anche a fine mese, escono.</li>")
    nota_sotto = ""
    if stato["sotto"]:
        nota_sotto = ("<li><b>Sotto la MM200:</b> " +
                      ", ".join([t.replace('.MI', '') for t in stato["sotto"]]) +
                      " — condizione di uscita a fine mese.</li>")

    return f"""<!DOCTYPE html>
<html lang="it">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Operatività di oggi — {data_ultima}</title></head>
<body style="margin:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a">
<div style="max-width:980px;margin:0 auto;padding:18px 14px 40px">

  <div style="background:{bg};color:#fff;border-radius:14px;padding:22px">
    <div style="font-size:12px;letter-spacing:1.2px;text-transform:uppercase;opacity:.85">
      Operatività di oggi · dati di borsa al {data_ultima}</div>
    <div style="font-size:30px;font-weight:900;margin:8px 0 6px;line-height:1.15">{titolo}</div>
    <div style="font-size:15px;opacity:.95">{sottot}</div>
  </div>

  <div style="display:flex;gap:12px;flex-wrap:wrap;margin:14px 0">
    <div style="flex:1 1 180px;background:#fff;border-radius:12px;padding:15px 17px;box-shadow:0 1px 3px rgba(15,23,42,.08)">
      <div style="color:#64748b;font-size:12px;text-transform:uppercase;letter-spacing:.6px">Prossima verifica</div>
      <div style="font-size:20px;font-weight:800;margin-top:3px">{stato['prossima'].strftime('%d/%m/%Y')}</div>
      <div style="color:#64748b;font-size:12px">fra {stato['giorni_borsa']} giorni di borsa</div>
    </div>
    <div style="flex:1 1 180px;background:#fff;border-radius:12px;padding:15px 17px;box-shadow:0 1px 3px rgba(15,23,42,.08)">
      <div style="color:#64748b;font-size:12px;text-transform:uppercase;letter-spacing:.6px">Titoli in regola</div>
      <div style="font-size:20px;font-weight:800;margin-top:3px">{len(tenuti) - len(stato['sotto']) - len(stato['fuori_rank'])} / {len(tenuti)}</div>
      <div style="color:#64748b;font-size:12px">{len(stato['sotto'])} sotto MM200 · {len(stato['fuori_rank'])} fuori rank</div>
    </div>
    <div style="flex:1 1 180px;background:#fff;border-radius:12px;padding:15px 17px;box-shadow:0 1px 3px rgba(15,23,42,.08)">
      <div style="color:#64748b;font-size:12px;text-transform:uppercase;letter-spacing:.6px">Dal giorno della selezione</div>
      <div style="font-size:20px;font-weight:800;margin-top:3px;color:{('#0a7d3c' if (perf == perf and perf >= 0) else '#b91c1c') if perf == perf else '#0f172a'}">
        {"+" if (perf == perf and perf >= 0) else ""}{_num(perf, 1) + "%" if perf == perf else "n/d"}</div>
      <div style="color:#64748b;font-size:12px">portafoglio equipesato, senza costi</div>
    </div>
    <div style="flex:1 1 180px;background:#fff;border-radius:12px;padding:15px 17px;box-shadow:0 1px 3px rgba(15,23,42,.08)">
      <div style="color:#64748b;font-size:12px;text-transform:uppercase;letter-spacing:.6px">FTSE MIB</div>
      <div style="font-size:20px;font-weight:800;margin-top:3px;color:{mib_col}">{mib_txt} la MM200</div>
      <div style="color:#64748b;font-size:12px">breadth: {_num(breadth,0)}% dei titoli sopra la MM200</div>
    </div>
  </div>

  <div style="background:#fff;border-radius:12px;padding:18px;box-shadow:0 1px 3px rgba(15,23,42,.08)">
    <div style="font-size:13px;letter-spacing:1px;color:#64748b;text-transform:uppercase;font-weight:700">
      Portafoglio — margine rispetto al livello di uscita</div>
    <table style="width:100%;border-collapse:collapse;margin-top:8px;font-size:14px">
      <thead><tr style="color:#64748b;font-size:12px;text-transform:uppercase">
        <th style="text-align:left;padding:6px 10px">Titolo</th>
        <th style="text-align:right;padding:6px 10px">Prezzo</th>
        <th style="text-align:right;padding:6px 10px">Livello uscita</th>
        <th style="text-align:right;padding:6px 10px">Margine</th>
        <th style="text-align:right;padding:6px 10px">Stato</th>
      </tr></thead>
      <tbody>{''.join(righe)}</tbody>
    </table>
    <div style="color:#64748b;font-size:12px;margin-top:10px">
      <b>Livello di uscita</b> = MM200 di oggi. Il titolo esce solo se <i>a fine mese</i> chiude sotto quel livello
      (o scivola oltre il rank {args.n + args.buffer}): la distanza in % è il margine di sicurezza che hai oggi.
    </div>
  </div>

  <div style="background:#fff;border-radius:12px;padding:18px;margin-top:14px;box-shadow:0 1px 3px rgba(15,23,42,.08)">
    <div style="font-size:13px;letter-spacing:1px;color:#64748b;text-transform:uppercase;font-weight:700">
      Candidati in attesa — non si comprano oggi</div>
    <div style="color:#64748b;font-size:13px;margin:8px 0 4px">Entrano in portafoglio solo se a una verifica mensile
      chiudono sopra il livello indicato.</div>
    <table style="width:100%;border-collapse:collapse;font-size:14px">
      <thead><tr style="color:#64748b;font-size:12px;text-transform:uppercase">
        <th style="text-align:left;padding:6px 10px">Titolo</th>
        <th style="text-align:right;padding:6px 10px">Prezzo</th>
        <th style="text-align:right;padding:6px 10px">Si attiva sopra</th>
      </tr></thead>
      <tbody>{''.join(righe_attesa) if righe_attesa else '<tr><td colspan="3" style="padding:10px;color:#64748b">Nessun candidato</td></tr>'}</tbody>
    </table>
  </div>

  <div style="background:#fff;border-radius:12px;padding:18px;margin-top:14px;box-shadow:0 1px 3px rgba(15,23,42,.08)">
    <div style="font-size:13px;letter-spacing:1px;color:#64748b;text-transform:uppercase;font-weight:700">Checklist di oggi (10 secondi)</div>
    <ol style="margin:10px 0 0;padding-left:20px;font-size:14px;line-height:1.9">
      <li>È l'ultimo giorno di borsa del mese? <b>{"sì → esegui la verifica" if stato['oggi_verifica'] else "no"}</b>
          (prossima: {stato['prossima'].strftime('%d/%m')}, fra {stato['giorni_borsa']} sedute).</li>
      {nota_sotto}
      {nota_fuori}
      <li>Tutto il resto è rumore: <b>non fare nulla</b>. Niente stop, niente overlay, nessun ingresso fuori data.</li>
    </ol>
  </div>

  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:16px 18px;margin-top:14px;font-size:13px;color:#475569;line-height:1.7">
    <b>Contesto di mercato</b> (informativo, <u>non</u> operativo): FTSE MIB {mib_txt} la MM200 ·
    {_num(breadth,0)}% dei {len(tab)} titoli sopra la MM200 · rotture della MM200 nelle ultime 5 sedute:
    {elenco_rotture}.
    <br>Nei test, il regime di mercato e le rotture della media <b>non</b> hanno prodotto un edge misurabile
    (README §1 e §6): servono a capire il contesto, non a decidere.
  </div>

  <div style="color:#94a3b8;font-size:12px;text-align:center;margin-top:16px">
    Generata da <code>operativita_oggi.py</code> · scheda mensile: <code>output/scheda_operativa.html</code> ·
    istruzioni: <code>GUIDA.md</code> · non è consulenza finanziaria
  </div>
</div>
</body></html>"""


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Operatività di oggi: cosa fare adesso, per davvero")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--buffer", type=int, default=5)
    ap.add_argument("--liquidita", type=float, default=2_000_000)
    ap.add_argument("--attuale", default=None, help="default: output/portafoglio_attuale.csv (o _XX)")
    ap.add_argument("--trimestrale", action="store_true")
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--solo-verdetto", action="store_true", help="stampa una riga sola")
    ap.add_argument("--out", default=None, help="default: output/operativita_oggi.html (o _XX)")
    args = ap.parse_args()

    oggi = pd.Timestamp(datetime.now().date())
    raw = so.scarica("2y", usa_cache=args.no_download)
    tab, rank, breadth, regime, rotture, data_ultima = stato_giorno(
        raw, oggi, args.liquidita, args.n, args.buffer)

    tenuti: list[str] = []
    prezzi_ingresso: dict[str, float] = {}
    if os.path.exists(args.attuale):
        try:
            p = pd.read_csv(args.attuale, sep=None, engine="python")
            col = next(c for c in p.columns if "ticker" in c.lower())
            tenuti = [str(x).strip() for x in p[col].dropna().tolist()]
            if "prezzo" in p.columns:
                prezzi_ingresso = {}
                for _, r in p.iterrows():
                    v = r.get("prezzo")
                    if pd.isna(v):
                        continue
                    prezzi_ingresso[str(r[col]).strip()] = float(str(v).replace(",", "."))
        except Exception as e:
            print(f"[avviso] {args.attuale}: {e}")
    if not tenuti:
        print("[avviso] nessun portafoglio attuale: mostro solo il verdetto e il contesto.")

    stato = verifica_stato(oggi, args.trimestrale, tab, rank, tenuti, args.n, args.buffer)
    stato["_oggi"] = oggi

    perf = np.nan
    if prezzi_ingresso:
        rr = []
        for t in tenuti:
            if t in tab.index and prezzi_ingresso.get(t):
                rr.append(tab.loc[t, "prezzo"] / prezzi_ingresso[t] - 1)
        if rr:
            perf = float(np.mean(rr) * 100)

    # candidati in attesa: liquidi, sotto MM200, momentum positivo
    liq = tab[tab["turnover_mediano"] >= args.liquidita]
    attesa = liq[~liq["sopra_mm200"]].sort_values("mom_%", ascending=False).head(5).copy()
    attesa = attesa[attesa["mom_%"] > 0]
    attesa["livello_ingresso"] = attesa["livello_mm200"]
    attesa["distanza_attivazione_%"] = (attesa["livello_ingresso"] / attesa["prezzo"] - 1) * 100
    attesa = attesa.reset_index()

    if stato["oggi_verifica"]:
        verdetto = f"OGGI È IL GIORNO DELLA VERIFICA ({stato['prossima'].date()}) → lancia selezione_oggi.py"
    elif stato["sotto"] or stato["fuori_rank"]:
        verdetto = ("ATTENZIONE — fuori regola: "
                    + ", ".join([t.replace('.MI', '') for t in stato["sotto"] + stato["fuori_rank"]])
                    + " (si decide a fine mese, oggi non si agisce)")
    elif stato["vicini_uscita"]:
        verdetto = ("NESSUN ORDINE — da osservare: "
                    + ", ".join([t.replace('.MI', '') for t in stato["vicini_uscita"]]))
    else:
        verdetto = "OGGI NON DEVI FARE NULLA: nessuna condizione operativa attiva"

    print(f"OPERATIVITÀ DI OGGI — dati al {data_ultima} · prossima verifica {stato['prossima'].date()} "
          f"({stato['giorni_borsa']} sedute)")
    print(f"  {verdetto}")
    print(f"  FTSE MIB {'sopra' if regime else 'sotto'} la MM200 · breadth {breadth:.0f}% · "
          f"portafoglio in regola: {len(tenuti) - len(stato['sotto']) - len(stato['fuori_rank'])}/{len(tenuti)}"
          + ((" · dal giorno della selezione: " + f"{perf:+.1f}%".replace(".", ",")) if perf == perf else ""))
    if args.solo_verdetto:
        return 0

    html = costruisci_html(args, data_ultima, tab, tenuti, rank, stato, attesa, breadth, regime, rotture, perf)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  pagina: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
