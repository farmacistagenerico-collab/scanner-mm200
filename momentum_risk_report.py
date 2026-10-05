# -*- coding: utf-8 -*-
"""
Report HTML del modulo "momentum + risk management" (autonomo, SVG inline).
"""
from __future__ import annotations

import os
from datetime import datetime

import numpy as np
import pandas as pd

from report_portafoglio import CSS, svg_barre, svg_linee, tabella, _esc

COLORI_RISK = {
    "① Base MOM 12-1 top10 + MM200 (mensile)": "#0b7a3b",
    "①-bis Base senza filtro MM200": "#8bc34a",
    "② + buffer di rank 5": "#2e7d32",
    "③ + ribilanciamento trimestrale (buffer 5)": "#0d5aa7",
    "④ + volatility targeting 15%": "#6a1b9a",
    "⑤ + overlay trend su equity (MA10)": "#e2725b",
    "⑥ + overlay drawdown (15%/25%)": "#b8860b",
    "⑦ Combinato: trimestrale + VT + MA10": "#a11212",
    "⑧ Combinato: mensile + buffer + VT + DD": "#00838f",
    "◇ Universo equipesato (buy & hold)": "#5f7d3e",
    "◇ FTSE MIB (buy & hold)": "#9e9e9e",
}


def colore(nome: str) -> str:
    if nome in COLORI_RISK:
        return COLORI_RISK[nome]
    if nome.startswith("⓪"):
        return "#9aa0a6"
    return "#555"


def scrivi_report_risk(tab, colonne, per_anno_tab, crash_tab, pivo_c, pivo_s, pivo_d,
                       curve, args, random_cagr, out_dir) -> str:
    def riga(nome):
        r = tab[tab["variante"] == nome]
        return r.iloc[0] if len(r) else None

    base = riga("① Base MOM 12-1 top10 + MM200 (mensile)")
    combo = riga("⑦ Combinato: trimestrale + VT + MA10")
    vt = riga("④ + volatility targeting 15%")
    ov = riga("⑤ + overlay trend su equity (MA10)")
    univ = riga("◇ Universo equipesato (buy & hold)")
    rand = riga(next((n for n in tab["variante"] if str(n).startswith("⓪")), ""))

    def card(t, v, s=""):
        return (f'<div class="card"><div class="k">{_esc(t)}</div><div class="v">{v}</div>'
                f'<div class="s">{_esc(s)}</div></div>')

    cards = []
    if base is not None:
        cards.append(card("Base (mensile)", f"{base['CAGR_%']:+.1f}% CAGR",
                          f"Sharpe {base['Sharpe']} · maxDD {base['max_dd_%']:.0f}% · "
                          f"turnover {base['turnover_mensile_%']:.0f}%/mese"))
    if combo is not None:
        cards.append(card("Combinato (trim+VT+MA10)", f"{combo['CAGR_%']:+.1f}% CAGR",
                          f"Sharpe {combo['Sharpe']} · maxDD {combo['max_dd_%']:.0f}% · "
                          f"turnover {combo['turnover_mensile_%']:.0f}%/mese"))
    if univ is not None:
        cards.append(card("Universo equipesato", f"{univ['CAGR_%']:+.1f}% CAGR",
                          f"Sharpe {univ['Sharpe']} · maxDD {univ['max_dd_%']:.0f}%"))
    if rand is not None:
        p05, p95 = np.percentile(random_cagr, [5, 95]) if random_cagr else (np.nan, np.nan)
        cards.append(card("Controllo casuale", f"{rand['CAGR_%']:+.1f}% CAGR",
                          f"5°-95° dei seed: {p05:+.1f}% … {p95:+.1f}%"))

    # --------- grafici ---------
    ordine = [k for k in ["① Base MOM 12-1 top10 + MM200 (mensile)",
                          "③ + ribilanciamento trimestrale (buffer 5)",
                          "④ + volatility targeting 15%",
                          "⑤ + overlay trend su equity (MA10)",
                          "⑦ Combinato: trimestrale + VT + MA10",
                          "⓪ Controllo: casuali equip. (media 20 seed)",
                          "◇ Universo equipesato (buy & hold)"] if k in curve]
    curve_plot = {k: curve[k] for k in ordine}
    svg_eq = svg_linee(curve_plot, f"Equity (scala logaritmica) — capitale iniziale "
                                   f"{args.capitale:,.0f} €", log=True)
    curve_anno = {k: per_anno_tab[k] for k in per_anno_tab.columns if k in curve_plot}
    svg_anni = svg_barre(pd.DataFrame(curve_anno), "Rendimento per anno (%)")
    legenda = "".join(f'<span><i style="background:{colore(n)}"></i>{_esc(n)}</span>'
                      for n in curve_plot)

    # --------- verdetto calcolato ---------
    def g(r, k):
        return r[k] if r is not None and k in r else None

    frasi = []
    if base is not None and vt is not None:
        frasi.append(
            f"Volatility targeting: Sharpe {g(base,'Sharpe'):+.2f} → {g(vt,'Sharpe'):+.2f}, "
            f"max drawdown {g(base,'max_dd_%'):+.1f}% → {g(vt,'max_dd_%'):+.1f}% "
            f"({'migliora' if (g(vt,'Sharpe') or 0) > (g(base,'Sharpe') or 0) else 'non migliora'} il rischio "
            f"a parità di rendimento: CAGR {g(base,'CAGR_%'):+.1f}% → {g(vt,'CAGR_%'):+.1f}%).")
    if base is not None and ov is not None:
        frasi.append(
            f"Overlay trend su equity: Sharpe {g(ov,'Sharpe'):+.2f}, max drawdown {g(ov,'max_dd_%'):+.1f}%, "
            f"ma resta investito solo il {100 - (g(ov,'mesi_risk_off_%') or 0):.0f}% dei mesi.")
    if base is not None and combo is not None:
        frasi.append(
            f"Combinazione completa: CAGR {g(combo,'CAGR_%'):+.1f}% con Sharpe {g(combo,'Sharpe'):+.2f} "
            f"e turnover {g(combo,'turnover_mensile_%'):.0f}%/mese (contro {g(base,'turnover_mensile_%'):.0f}%): "
            f"il trimestrale con buffer taglia i costi ma riduce anche la reattività del segnale.")
    if univ is not None and base is not None:
        frasi.append(
            f"Confronto con il beta: l'universo equipesato rende {g(univ,'CAGR_%'):+.1f}% con Sharpe "
            f"{g(univ,'Sharpe'):+.2f} — il momentum resta {'sopra' if g(base,'CAGR_%') > g(univ,'CAGR_%') else 'sotto'}.")

    verdetto = ('<div class="note" style="background:#f2f7fb;border-color:#cfe2f3;color:#12395e">'
                '<b>Verdetto — cosa fanno davvero gli strumenti di rischio</b><br>'
                + "<br>".join(frasi) +
                '<br><span class="muted">Nota: i costi sono forfettari, l\'universo contiene solo titoli quotati '
                'oggi (survivorship) e le tasse non sono modellate. Gli overlay riducono il rischio ma anche '
                'l\'esposizione: il confronto va fatto sempre a parità di rischio percepito.</span></div>')

    metodologia = f"""
    <details open>
      <summary>Metodo</summary>
      <ul>
        <li><b>Segnale</b>: momentum 12-1 (rendimento a 12 mesi terminante un mese prima), top 10,
            equipesati, ribilanciati secondo la variante; filtro liquidità ≥ {args.liquidita:,.0f} €/giorno
            e (dove indicato) prezzo sopra la MM200.</li>
        <li><b>Volatility targeting</b>: esposizione = target 15% / volatilità realizzata dei 12 mesi
            precedenti, limitata fra 30% e 100% (nessuna leva).</li>
        <li><b>Overlay trend</b>: se l'equity della strategia chiude sotto la sua media a 10 mesi si va in
            cash per il mese successivo; <b>overlay drawdown</b>: −50% di esposizione oltre −15% di
            drawdown, cash oltre −25%.</li>
        <li><b>Buffer di rank</b>: un titolo in portafoglio viene sostituito solo se il sostituto lo supera
            di 5 posizioni in graduatoria (riduce il turnover "da rumore").</li>
        <li><b>Costi</b>: {args.costo*100:.1f}% per lato sul turnover effettivo della parte investita.</li>
        <li><b>Controlli</b>: 20 portafogli casuali con la stessa meccanica, universo equipesato e FTSE MIB;
            split in-sample 2010-2017 / out-of-sample 2018-2026 senza ri-ottimizzazione.</li>
      </ul>
    </details>"""

    html = f"""<!DOCTYPE html>
<html lang="it">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Momentum + risk management — Piazza Affari</title><style>{CSS}</style></head>
<body>
<header><div class="inner">
  <h1>Momentum cross-sectional + gestione del rischio</h1>
  <p>Volatility targeting, overlay di drawdown, buffer di ribilanciamento · costi inclusi ·
     generato il {datetime.now():%d/%m/%Y %H:%M}</p>
</div></header>
<div class="wrap">
  <div class="cards">{''.join(cards)}</div>
  {verdetto}
  <h2>Equity curve e rendimenti per anno</h2>
  <div class="legend">{legenda}</div>
  <div class="charts" style="grid-template-columns:1fr">
    <div class="panel">{svg_eq}</div>
    <div class="panel">{svg_anni}
      <div class="legend">{''.join(f'<span><i style="background:{colore(n)}"></i>{_esc(n)}</span>' for n in curve_anno)}</div>
    </div>
  </div>
  <h2>Varianti <span>(ordinate per Sharpe)</span></h2>
  {tabella(tab.sort_values("Sharpe", ascending=False).set_index("variante"), colonne[1:])}
  <h2>Diagnostica dei crash</h2>
  {tabella(crash_tab.set_index("variante") if not crash_tab.empty else pd.DataFrame())}
  <h2>In-sample / out-of-sample</h2>
  <h3 style="font-size:13.5px;margin:14px 0 6px">CAGR %</h3>
  {tabella(pivo_c)}
  <h3 style="font-size:13.5px;margin:14px 0 6px">Sharpe</h3>
  {tabella(pivo_s)}
  <h3 style="font-size:13.5px;margin:14px 0 6px">Max drawdown %</h3>
  {tabella(pivo_d)}
  {metodologia}
  <footer>Generato da <code>momentum_risk.py</code>. Dati: Yahoo Finance (chiusure adjusted).
  Ricerca a scopo informativo: nessuna raccomandazione operativa.</footer>
</div>
</body></html>"""
    path = os.path.join(out_dir, "report_momentum_risk.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
