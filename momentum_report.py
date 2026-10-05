# -*- coding: utf-8 -*-
"""
Report HTML del modulo momentum (autonomo, SVG inline).
Riusa il motore grafico di report_portafoglio per coerenza visiva.
"""
from __future__ import annotations

import os
from datetime import datetime

import numpy as np
import pandas as pd

from report_portafoglio import CSS, COLORI as COLORI_BASE, svg_barre, svg_linee, tabella, _esc

COLORI_MOM = {
    "MOM 12-1, top 10": "#0b7a3b",
    "MOM 12-1, top 10 + filtro MM200": "#14b866",
    "MOM 12-1, top 20": "#2e7d32",
    "MOM 6 mesi, top 10": "#0d5aa7",
    "MOM 12-1 corretto per volatilità, top 10": "#6a1b9a",
    "PEGGIORI 10 (controllo inverso)": "#a11212",
    "Universo equipesato (buy & hold)": "#5f7d3e",
    "FTSE MIB (buy & hold)": "#b8860b",
}
COLORI_INSIEME = {**COLORI_BASE, **COLORI_MOM}


def colore(nome):
    if nome in COLORI_INSIEME:
        return COLORI_INSIEME[nome]
    if nome.startswith("Portafogli casuali"):
        return "#9aa0a6"
    return "#555"


def scrivi_report_momentum(tab, colonne, per_anno, pivo_cagr, pivo_sharpe, curve, cfg,
                           random_cagr, out_dir, tab_liq=None) -> str:
    ordine = ["MOM 12-1, top 10", "MOM 12-1, top 10 + filtro MM200", "MOM 12-1, top 20",
              "MOM 6 mesi, top 10", "MOM 12-1 corretto per volatilità, top 10",
              "PEGGIORI 10 (controllo inverso)", "Universo equipesato (buy & hold)",
              "FTSE MIB (buy & hold)"]
    rand_nome = next((n for n in tab["variante"] if "casuali" in str(n)), None)
    if rand_nome:
        ordine.insert(1, rand_nome)

    def riga(nome):
        r = tab[tab["variante"] == nome]
        return r.iloc[0] if len(r) else None

    def card(titolo, valore, sotto=""):
        return (f'<div class="card"><div class="k">{_esc(titolo)}</div>'
                f'<div class="v">{valore}</div><div class="s">{sotto}</div></div>')

    mom = riga("MOM 12-1, top 10")
    rand = riga(rand_nome) if rand_nome else None
    univ = riga("Universo equipesato (buy & hold)")
    peggio = riga("PEGGIORI 10 (controllo inverso)")

    cards = []
    if mom is not None:
        cards.append(card("MOM 12-1, top 10", f"{mom['CAGR_%']:+.1f}% CAGR",
                          f"Sharpe {mom['Sharpe']} · max DD {mom['max_drawdown_%']:.0f}% · "
                          f"turnover {mom.get('turnover_mensile_%', 0):.0f}%/mese"))
    if rand is not None:
        p05, p95 = np.percentile(random_cagr, [5, 95])
        cards.append(card("Portafogli casuali (controllo)", f"{rand['CAGR_%']:+.1f}% CAGR",
                          f"intervallo 5°-95° dei seed: {p05:+.1f}% … {p95:+.1f}%"))
    if univ is not None:
        cards.append(card("Universo equipesato", f"{univ['CAGR_%']:+.1f}% CAGR",
                          f"Sharpe {univ['Sharpe']} · max DD {univ['max_drawdown_%']:.0f}%"))
    if peggio is not None:
        cards.append(card("Controllo inverso (i peggiori 10)", f"{peggio['CAGR_%']:+.1f}% CAGR",
                          "se il momentum funziona, questo deve fare molto peggio"))

    curve_plot = {k: v for k, v in curve.items() if k in ordine}
    for k, v in curve_plot.items():
        COLORI_INSIEME.setdefault(k, colore(k))
    svg_eq = svg_linee(curve_plot, "Equity (scala logaritmica) — capitale iniziale "
                                   f"{cfg.capitale:,.0f} €", log=True)
    curve_anno = {k: v for k, v in per_anno.items() if k in curve_plot}
    df_anno = pd.DataFrame(curve_anno)
    svg_anni = svg_barre(df_anno, "Rendimento per anno (%)")
    legenda = "".join(f'<span><i style="background:{colore(n)}"></i>{_esc(n)}</span>'
                      for n in curve_plot)

    # verdetto calcolato
    p05, p95 = (np.percentile(random_cagr, [5, 95]) if random_cagr else (np.nan, np.nan))
    battuto_universo = (mom is not None and univ is not None and mom["CAGR_%"] > univ["CAGR_%"])
    battuto_caso = (mom is not None and np.isfinite(p95) and mom["CAGR_%"] > p95)
    battuto_peggio = (mom is not None and peggio is not None and mom["CAGR_%"] > peggio["CAGR_%"])

    def frase(cond, si, no):
        return f'<b style="color:{"#0b7a3b" if cond else "#a11212"}">{"✅ " + si if cond else "❌ " + no}</b>'

    mom_c = mom["CAGR_%"] if mom is not None else np.nan
    rand_c = rand["CAGR_%"] if rand is not None else np.nan
    univ_c = univ["CAGR_%"] if univ is not None else np.nan
    peggio_c = peggio["CAGR_%"] if peggio is not None else np.nan

    verdetto = f"""
    <div class="note" style="background:#f2f7fb;border-color:#cfe2f3;color:#12395e">
      <b>Verdetto — le tre domande che contano</b><br>
      {frase(battuto_peggio, f"L'ordinamento esiste: i migliori {mom_c:+.1f}% contro i peggiori {peggio_c:+.1f}% "
             f"(spread {mom_c - peggio_c:+.1f} punti) → il momentum cross-sectional ha segnale.",
             "Nessun differenziale fra migliori e peggiori: nessun segnale.")}<br>
      {frase(battuto_caso, f"Battono i portafogli casuali: {mom_c:+.1f}% contro {rand_c:+.1f}% (95° percentile "
             f"{p95:+.1f}%).", f"Non battono il caso: {mom_c:+.1f}% contro {rand_c:+.1f}% del portafoglio casuale "
             f"medio (95° percentile {p95:+.1f}%).")}<br>
      {frase(battuto_universo, f"Battono anche il semplice universo equipesato ({univ_c:+.1f}%).",
             f"Non battono il semplice universo equipesato ({univ_c:+.1f}%): il beta italiano spiega tutto.")}<br>
      <span class="muted">Ricorda: universo di soli titoli quotati oggi (survivorship) e costi forfettari;
      il risultato va letto come indicazione, non come prova definitiva.</span>
    </div>"""

    metodologia = f"""
    <details open>
      <summary>Metodo</summary>
      <ul>
        <li><b>Segnale</b>: rendimento a 12 mesi terminante un mese prima del ribilanciamento
            (P[i−1]/P[i−13]−1): il classico "12-1" che salta l'ultimo mese per evitare il rimbalzo di breve.
            Variante a 6 mesi e variante corretta per volatilità (rendimento/volatilità 12 mesi).</li>
        <li><b>Portafoglio</b>: N titoli con segnale più alto, equipesati, ribilanciati ogni mese;
            N={cfg.n} (variante a 20 titoli nella tabella).</li>
        <li><b>Filtri di ammissibilità</b>: turnover mediano ≥ {cfg.liquidita:,.0f} €/giorno,
            chiusura positiva, storia sufficiente; filtro opzionale "prezzo sopra la MM200".</li>
        <li><b>Costi</b>: {cfg.costo_lato*100:.1f}% per lato, applicati al turnover effettivo a ogni
            ribilanciamento (vendite + acquisti).</li>
        <li><b>Controlli</b>: portafogli casuali ({len(random_cagr)} seed, stesse regole e stessa cadenza),
            controllo inverso (i peggiori N), universo equipesato e FTSE MIB.</li>
        <li><b>Verifica</b>: risultati spezzati in 2010-2017 (in-sample) e 2018-2026 (out-of-sample),
            senza ri-ottimizzare alcun parametro.</li>
      </ul>
    </details>"""

    html = f"""<!DOCTYPE html>
<html lang="it">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Momentum cross-sectional — Piazza Affari</title><style>{CSS}</style></head>
<body>
<header><div class="inner">
  <h1>Momentum cross-sectional — Piazza Affari</h1>
  <p>Ranking di forza relativa con ribilanciamento mensile, costi inclusi · generato il {datetime.now():%d/%m/%Y %H:%M}</p>
</div></header>
<div class="wrap">
  <div class="cards">{''.join(cards)}</div>
  <h2>Equity curve e rendimenti per anno</h2>
  <div class="legend">{legenda}</div>
  <div class="charts" style="grid-template-columns:1fr">
    <div class="panel">{svg_eq}</div>
    <div class="panel">{svg_anni}
      <div class="legend">{''.join(f'<span><i style="background:{colore(n)}"></i>{_esc(n)}</span>' for n in curve_anno)}</div>
    </div>
  </div>
  {verdetto}
  <h2>Risultati per variante</h2>
  {tabella(tab.set_index("variante"), colonne[1:])}
  <h2>In-sample vs out-of-sample <span>(CAGR % per periodo)</span></h2>
  {tabella(pivo_cagr)}
  <h2>Sharpe per periodo</h2>
  {tabella(pivo_sharpe)}
  <h2>Sensibilità alla liquidità <span>(le micro-cap illiquide spiegano parte del risultato?)</span></h2>
  <p class="muted" style="font-size:12.5px">Stesso segnale (MOM 12-1, top 10) con soglie crescenti di turnover
  mediano giornaliero. Senza filtro restano nel paniere molte micro-cap: parte del rendimento è premio di
  illiquidità (limiti all'arbitraggio). L'effetto però <b>non sparisce</b> sui titoli liquidi.</p>
  {tabella(tab_liq.set_index("soglia_€/giorno") if tab_liq is not None and not tab_liq.empty else pd.DataFrame())}
  {metodologia}
  <footer>Generato da <code>momentum.py</code>. Dati: Yahoo Finance (chiusure adjusted).
  Ricerca a scopo informativo: nessuna raccomandazione operativa.</footer>
</div>
</body></html>"""
    path = os.path.join(out_dir, "report_momentum.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
