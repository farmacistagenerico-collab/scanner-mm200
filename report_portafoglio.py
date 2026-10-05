# -*- coding: utf-8 -*-
"""
Report HTML del portafoglio: KPI, equity curve in SVG, tabelle.
Tutto inline (nessuna risorsa esterna), così il file si apre ovunque.
"""
from __future__ import annotations

import os
from datetime import datetime

import numpy as np
import pandas as pd

COLORI = {
    "Score ≥ +3": "#0b7a3b",
    "Score ≥ +2": "#2e7d32",
    "Solo deep recovery": "#0d5aa7",
    "Rottura grezza (senza filtro)": "#a11212",
    "Ingressi casuali (controllo)": "#8a8f98",
    "FTSE MIB (buy & hold)": "#b8860b",
    "Universo equal-weight (buy & hold)": "#5f7d3e",
    "Score ≥ +3 · nessuno stop, uscita a 250 sedute": "#14b866",
    "Rottura grezza · nessuno stop, uscita a 250 sedute": "#e2725b",
    "Ingressi casuali · nessuno stop, uscita a 250 sedute": "#9aa0a6",
    "Walk-forward · orizzonte": "#6a1b9a",
    "Walk-forward · trail_mm200": "#b39ddb",
}

CSS = """
:root { --bordo:#e3e6ea; --testo:#1c1f23; --muto:#6b7280; }
* { box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
       margin:0; background:#f6f7f9; color:var(--testo); }
header { background:linear-gradient(135deg,#0b2545,#133b63); color:#fff; padding:26px 20px; }
header .inner { max-width:1180px; margin:0 auto; }
header h1 { margin:0 0 6px; font-size:24px; letter-spacing:-.3px; }
header p { margin:0; opacity:.85; font-size:14px; }
.wrap { max-width:1180px; margin:0 auto; padding:26px 20px 60px; }
.cards { display:flex; gap:14px; flex-wrap:wrap; margin:6px 0 22px; }
.card { background:#fff; border:1px solid var(--bordo); border-radius:10px; padding:14px 16px; flex:1 1 190px; }
.card .k { font-size:12px; text-transform:uppercase; letter-spacing:.4px; color:var(--muto); }
.card .v { font-size:20px; font-weight:600; margin-top:4px; }
.card .s { font-size:12px; color:var(--muto); margin-top:2px; }
h2 { font-size:17px; margin:30px 0 10px; }
h2 span { color:var(--muto); font-weight:400; font-size:13px; }
table { width:100%; border-collapse:collapse; background:#fff; border:1px solid var(--bordo);
        border-radius:10px; overflow:hidden; font-size:13px; }
th, td { padding:8px 10px; text-align:left; border-bottom:1px solid var(--bordo); }
th { background:#eef1f5; font-size:11.5px; text-transform:uppercase; letter-spacing:.4px;
     color:#374151; white-space:nowrap; }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
tr:last-child td { border-bottom:none; }
.pos { color:#0b7a3b; } .neg { color:#a11212; }
.muted { color:var(--muto); }
.legend { display:flex; gap:16px; flex-wrap:wrap; font-size:12px; margin:10px 0 4px; }
.legend i { display:inline-block; width:14px; height:3px; vertical-align:middle; margin-right:6px; }
details { background:#fff; border:1px solid var(--bordo); border-radius:10px; padding:12px 16px; margin-top:14px; }
summary { cursor:pointer; font-weight:600; font-size:14px; }
details p, details li { font-size:13px; line-height:1.55; color:#374151; }
.note { background:#fff8e1; border:1px solid #f2e0a8; border-radius:10px; padding:12px 16px;
        font-size:13px; color:#6b5b00; margin-top:18px; }
footer { margin-top:30px; font-size:12px; color:var(--muto); line-height:1.6; }
.charts { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
@media (max-width:900px){ .charts { grid-template-columns:1fr; } }
.panel { background:#fff; border:1px solid var(--bordo); border-radius:10px; padding:12px; }
.panel h3 { margin:2px 0 8px; font-size:13.5px; }
"""


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_linee(serie: dict[str, pd.Series], titolo: str, w=560, h=260, log=False,
              solo_positivo=False) -> str:
    """Grafico a linee SVG autonomo (nessuna libreria esterna)."""
    px, py = 62, 18            # margini sinistra/alto
    pw, ph = w - px - 14, h - py - 34
    tutte = pd.concat([s.dropna() for s in serie.values()])
    if tutte.empty:
        return "<p class='muted'>nessun dato</p>"
    tutti_idx = sorted(set().union(*[s.dropna().index for s in serie.values()]))
    t0, t1 = tutti_idx[0], tutti_idx[-1]
    span = max((t1 - t0).days, 1)

    def yminmax(vals):
        v = np.asarray(vals, dtype=float)
        v = v[np.isfinite(v)]
        return float(v.min()), float(v.max())

    vmin, vmax = yminmax(tutte.values)
    if solo_positivo:
        vmin = 0.0
    if log:
        vals = [max(x, 1.0) for x in tutte.values]
        vmin, vmax = np.log10(min(vals)), np.log10(max(vals))
        scal = lambda v: (np.log10(max(v, 1.0)) - vmin) / (vmax - vmin + 1e-12)
    else:
        scal = lambda v: (v - vmin) / (vmax - vmin + 1e-12)
    pad = (vmax - vmin) * 0.06
    if not log:
        vmin -= pad; vmax += pad
        scal = lambda v: (v - vmin) / (vmax - vmin + 1e-12)

    def X(d):
        return px + (d - t0).days / span * pw

    def Y(v):
        return py + ph - scal(v) * ph

    # griglia orizzontale
    parti = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;font-family:inherit">']
    parti.append(f'<rect x="0" y="0" width="{w}" height="{h}" fill="#fff"/>')
    for k in range(5):
        valore = vmin + (vmax - vmin) * k / 4
        y = Y(10 ** valore) if log else Y(valore)
        etichetta = (f"{10**valore:,.0f}" if log else f"{valore:,.0f}")
        parti.append(f'<line x1="{px}" y1="{y:.1f}" x2="{px+pw}" y2="{y:.1f}" stroke="#eef1f5"/>')
        parti.append(f'<text x="{px-6}" y="{y+4:.1f}" font-size="10" fill="#6b7280" '
                     f'text-anchor="end">{etichetta}</text>')
    # assi temporali
    for anno in range(t0.year, t1.year + 1, max(1, (t1.year - t0.year) // 6)):
        d = pd.Timestamp(f"{anno}-01-01")
        if d < t0 or d > t1:
            continue
        x = X(d)
        parti.append(f'<line x1="{x:.1f}" y1="{py}" x2="{x:.1f}" y2="{py+ph}" stroke="#f4f6f8"/>')
        parti.append(f'<text x="{x:.1f}" y="{py+ph+16}" font-size="10" fill="#6b7280" '
                     f'text-anchor="middle">{anno}</text>')
    # linee (con downsampling: max ~900 punti per serie per tenere il file leggero)
    for nome, s in serie.items():
        s = s.dropna()
        if len(s) < 2:
            continue
        passo = max(1, len(s) // 900)
        s = s.iloc[::passo]
        if s.index[-1] != serie[nome].dropna().index[-1]:        # conserva l'ultimo punto
            s = pd.concat([s, serie[nome].dropna().iloc[-1:]])
        col = COLORI.get(nome, "#333")
        punti = " ".join(f"{X(d):.1f},{Y(v):.1f}" for d, v in s.items())
        parti.append(f'<polyline points="{punti}" fill="none" stroke="{col}" stroke-width="1.8"/>')
    parti.append(f'<text x="{px}" y="{py-4}" font-size="11.5" fill="#374151">{_esc(titolo)}</text>')
    parti.append("</svg>")
    return "".join(parti)


def tabella(df: pd.DataFrame, colonne=None, percentuali=False, evidenzia=None) -> str:
    if df is None or df.empty:
        return "<p class='muted'>nessun dato</p>"
    d = df.copy()
    if colonne:
        d = d[[c for c in colonne if c in d.columns]]
    intest = "".join(f"<th>{_esc(c)}</th>" for c in d.columns)
    righe = []
    for idx, r in d.iterrows():
        celle = []
        for c in d.columns:
            v = r[c]
            cls = "num" if isinstance(v, (int, float, np.floating)) and not isinstance(v, bool) else ""
            if isinstance(v, float) and np.isfinite(v) and percentuali and ("%" in str(c) or "%" in str(c)):
                cls += " pos" if v > 0 else (" neg" if v < 0 else "")
            testo = "—" if (v is None or (isinstance(v, float) and not np.isfinite(v))) else (
                f"{v:,.2f}" if isinstance(v, (int, float, np.floating)) and not isinstance(v, bool) else str(v))
            celle.append(f'<td class="{cls}">{_esc(testo)}</td>')
        righe.append(f"<tr>{''.join(celle)}</tr>")
    return f'<table><thead><tr><th></th>{intest}</tr></thead><tbody>{"".join(righe)}</tbody></table>'


def scrivi_report_portafoglio(tab: pd.DataFrame, per_anno: pd.DataFrame, wf: pd.DataFrame,
                              curve: dict, cfg, out_dir: str, uscite: pd.DataFrame = None) -> str:
    ordine = ["Score ≥ +3", "Score ≥ +3 · nessuno stop, uscita a 250 sedute",
              "Walk-forward · orizzonte", "Walk-forward · trail_mm200",
              "Rottura grezza (senza filtro)",
              "Rottura grezza · nessuno stop, uscita a 250 sedute",
              "Ingressi casuali · nessuno stop, uscita a 250 sedute",
              "Universo equal-weight (buy & hold)", "FTSE MIB (buy & hold)"]
    principale = None
    for nome in ordine:
        if nome in tab["variante"].values:
            principale = tab[tab["variante"] == nome].iloc[0]
            break
    wf_row = tab[tab["variante"] == "Walk-forward · orizzonte"]
    grezza = tab[tab["variante"] == "Rottura grezza (senza filtro)"]
    mib = tab[tab["variante"] == "FTSE MIB (buy & hold)"]

    def card(k, v, s=""):
        return f'<div class="card"><div class="k">{k}</div><div class="v">{v}</div><div class="s">{s}</div></div>'

    cards = []
    if wf_row is not None and len(wf_row):
        r = wf_row.iloc[0]
        cards.append(card("Walk-forward (la strategia)", f"{r['CAGR_%']:+.1f}% CAGR",
                          f"Sharpe {r['Sharpe']} · max DD {r['max_drawdown_%']:.0f}% · "
                          f"{int(r['n_trade'])} operazioni"))
    if grezza is not None and len(grezza):
        r = grezza.iloc[0]
        cards.append(card("Rottura senza filtro (stop stretto)", f"{r['CAGR_%']:+.1f}% CAGR",
                          f"Sharpe {r['Sharpe']} · max DD {r['max_drawdown_%']:.0f}%"))
    ew = tab[tab["variante"] == "Universo equal-weight (buy & hold)"]
    if len(ew):
        r = ew.iloc[0]
        cards.append(card("Universo equal-weight (benchmark giusto)", f"{r['CAGR_%']:+.1f}% CAGR",
                          f"Sharpe {r['Sharpe']} · max DD {r['max_drawdown_%']:.0f}%"))
    if mib is not None and len(mib):
        r = mib.iloc[0]
        cards.append(card("FTSE MIB buy & hold", f"{r['CAGR_%']:+.1f}% CAGR",
                          f"Sharpe {r['Sharpe']} · max DD {r['max_drawdown_%']:.0f}%"))
    cards.append(card("Costi applicati", f"{cfg.costo_lato*100:.1f}% per lato",
                      f"rischio {cfg.rischio*100:.0f}%/operazione · max {cfg.max_posizioni} posizioni"))

    # equity in scala logaritmica
    curve_plot = {k: v for k, v in curve.items()}
    svg_eq = svg_linee(curve_plot, "Equity (scala logaritmica) — capitale iniziale "
                                   f"{cfg.capitale:,.0f} €", log=True)

    # rendimenti per anno (solo le varianti principali)
    sel_anni = [c for c in ordine if c in per_anno.columns]
    svg_anni = svg_barre(per_anno[sel_anni], "Rendimento per anno (%)", solo_positivo=False)

    legenda = "".join(
        f'<span><i style="background:{COLORI.get(n, "#333")}"></i>{_esc(n)}</span>' for n in curve_plot)

    tab_var = tab.copy()
    colonne = ["variante", "equity_finale", "CAGR_%", "volatilità_%", "Sharpe", "max_drawdown_%",
               "n_trade", "win_rate_%", "profit_factor", "durata_media_gg", "esposizione_media_%"]
    colonne = [c for c in colonne if c in tab_var.columns]

    metodologia = f"""
    <details open>
      <summary>Metodo della simulazione</summary>
      <ul>
        <li><b>Universo</b>: {len(curve)} serie — titoli di Piazza Affari (MIB/Mid/Star) + FTSE MIB come benchmark.</li>
        <li><b>Ingresso</b>: all'apertura del giorno successivo alla rottura della MM200 (buffer ±{cfg.buffer:.0f}%),
            purché il titolo soddisfi la regola di selezione della variante.</li>
        <li><b>Stop iniziale</b>: {cfg.stop_atr:.1f} ATR; <b>trailing stop</b>: {cfg.trail_atr:.1f} ATR dal massimo
            di chiusura (chandelier, solo rialzo); <b>uscite</b>: rientro sotto la MM200 (min 3 sedute)
            oppure {cfg.orizzonte} sedute.</li>
        <li><b>Sizing</b>: rischio {cfg.rischio*100:.0f}% del capitale per operazione,
            peso max {cfg.peso_max*100:.0f}%, massimo {cfg.max_posizioni} posizioni; cassa non remunerata.</li>
        <li><b>Costi</b>: {cfg.costo_lato*100:.1f}% per lato applicati all'ingresso e all'uscita.</li>
        <li><b>Componenti score (pesi validati out-of-sample)</b>: +1 deep recovery (dd&lt;−20%),
            +1 MM200 in salita, +1 MM50&gt;MM200, +1 forza relativa ≥50° percentile, −1 vicino ai massimi.</li>
        <li><b>Walk-forward</b>: a inizio anno i pesi delle componenti vengono ricalcolati SOLO su eventi
            con esito già concluso (finestra forward a 250 sedute chiusa prima dell'anno); la selezione
            risultante applica punteggio ≥ 3.</li>
        <li><b>Limiti</b>: universo = titoli quotati oggi (survivorship); eseguito a prezzi di chiusura/apertura
            senza slippage oltre il costo forfettario; nessuna tassa sulle plusvalenze.</li>
      </ul>
    </details>"""

    # ---- verdetto calcolato dai numeri ----
    def cagr(nome, default=None):
        r = tab[tab["variante"] == nome]
        return float(r.iloc[0]["CAGR_%"]) if len(r) else default

    def sharpe(nome, default=None):
        r = tab[tab["variante"] == nome]
        return float(r.iloc[0]["Sharpe"]) if len(r) else default

    ew_c, rand_c, raw_c = (cagr("Universo equal-weight (buy & hold)"),
                           cagr("Ingressi casuali · nessuno stop, uscita a 250 sedute"),
                           cagr("Rottura grezza · nessuno stop, uscita a 250 sedute"))
    wf_c = cagr("Walk-forward · orizzonte")
    migliore_strategia = max([c for c in (wf_c, raw_c) if c is not None], default=None)
    verdetto = f"""
    <div class="note" style="background:#fdecea;border-color:#f5c2c0;color:#7a1c17">
      <b>Verdetto (leggi i numeri, non le speranze)</b><br>
      1. Nessuna variante batte il semplice <b>buy &amp; hold equal-weight dell'universo</b>
         ({ew_c:+.1f}% CAGR): né i filtri, né la rottura grezza, né gli ingressi casuali.<br>
      2. Con la stessa meccanica di uscita a 250 sedute, <b>ingressi casuali</b> ({rand_c:+.1f}% CAGR)
         e <b>rotture grezze</b> ({raw_c:+.1f}% CAGR) rendono quasi identicamente al benchmark:
         il timing della rottura della MM200 <b>non aggiunge valore</b>.<br>
      3. I filtri "validati" <b>non migliorano</b> in portafoglio (score ≥3: {cagr("Score ≥ +3 · nessuno stop, uscita a 250 sedute"):+.1f}%),
         e il walk-forward ricalibrato fa {wf_c:+.1f}%: <b>l'edge misurato negli studi sugli eventi non si trasferisce
         in una strategia operativa</b>.<br>
      4. La gestione con stop stretto distrugge i risultati (rottura grezza: {cagr("Rottura grezza (senza filtro)"):+.1f}%
         contro {raw_c:+.1f}% con orizzonte lungo): il segnale è a bassa frequenza, non sopporta un trailing aggressivo.<br>
      5. Attenzione ai limiti: l'universo è fatto di titoli <i>ancora quotati oggi</i> (survivorship) e include molte
         mid/small cap che nel periodo hanno corso; il benchmark equal-weight è quindi ottimisticamente distorto.
         La conclusione onesta è che <b>il rialzo osservato è beta del mercato italiano, non alpha del metodo</b>.
    </div>"""

    html = f"""<!DOCTYPE html>
<html lang="it">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Portafoglio MM200 — Piazza Affari</title><style>{CSS}</style></head>
<body>
<header><div class="inner">
  <h1>Dal segnale alla strategia — Portafoglio MM200</h1>
  <p>Stop ATR, trailing, sizing sul rischio e costi su {curve and min(s.index[0] for s in curve.values()).strftime('%d/%m/%Y')}
     → {curve and max(s.index[-1] for s in curve.values()).strftime('%d/%m/%Y')} · generato il {datetime.now():%d/%m/%Y %H:%M}</p>
</div></header>
<div class="wrap">
  <div class="cards">{''.join(cards)}</div>
  <h2>Equity curve e rendimenti per anno</h2>
  <div class="legend">{legenda}</div>
  <div class="charts" style="grid-template-columns:1fr">
    <div class="panel">{svg_eq}</div>
    <div class="panel">{svg_anni}
      <div class="legend">{''.join(f'<span><i style="background:{COLORI.get(n, "#333")}"></i>{_esc(n)}</span>' for n in sel_anni)}</div>
    </div>
  </div>
  <h2>Risultati per variante <span>(stesso motore, stessa gestione: cambia solo la regola di selezione)</span></h2>
  {tabella(tab_var, colonne)}
  <h2>Walk-forward — pesi ricalibrati ogni anno</h2>
  <p class="muted" style="font-size:12.5px">Ogni riga è ciò che l'operatore avrebbe deciso a inizio anno usando
  solo il passato: +1 / −1 / 0 per componente. La colonna <b>punteggio ≥3</b> mostra quante componenti erano
  attive.</p>
  {tabella(wf)}
  {verdetto}
  {metodologia}
  <div class="note"><b>Nota</b>: simulazione a scopo di ricerca. Nessuna raccomandazione operativa; i costi
  sono forfettari e il mercato reale ha slippage, liquidità e tasse. Il campione selezionato è piccolo:
  leggi sempre l'incertezza insieme ai numeri.</div>
  <footer>Generato da <code>portafoglio.py</code> + <code>report_portafoglio.py</code>.
  Dati: Yahoo Finance (chiusure adjusted).</footer>
</div>
</body></html>"""
    path = os.path.join(out_dir, "report_portafoglio.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def svg_barre(df: pd.DataFrame, titolo: str, w=560, h=300, solo_positivo=False) -> str:
    """Barre raggruppate per anno (una serie per variante)."""
    if df is None or df.empty:
        return "<p class='muted'>nessun dato</p>"
    px, py = 46, 20
    pw, ph = w - px - 14, h - py - 40
    n_serie = max(len(df.columns), 1)
    anni = list(df.index)
    vmin = min(float(df.min().min()), 0.0) if not solo_positivo else 0.0
    vmax = max(float(df.max().max()), 0.0)
    span = max(vmax - vmin, 1e-9)

    def Y(v):
        return py + ph - (v - vmin) / span * ph

    larghezza_gruppo = pw / max(len(anni), 1)
    larghezza_barra = max(2.0, larghezza_gruppo * 0.8 / n_serie)
    parti = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto">']
    parti.append(f'<rect width="{w}" height="{h}" fill="#fff"/>')
    for k in range(5):
        v = vmin + span * k / 4
        y = Y(v)
        parti.append(f'<line x1="{px}" y1="{y:.1f}" x2="{px+pw}" y2="{y:.1f}" stroke="#eef1f5"/>')
        parti.append(f'<text x="{px-6}" y="{y+4:.1f}" font-size="10" fill="#6b7280" '
                     f'text-anchor="end">{v:.0f}%</text>')
    y0 = Y(0)
    parti.append(f'<line x1="{px}" y1="{y0:.1f}" x2="{px+pw}" y2="{y0:.1f}" stroke="#c9cfd6"/>')
    for i, anno in enumerate(anni):
        base_x = px + i * larghezza_gruppo + larghezza_gruppo * 0.1
        for j, nome in enumerate(df.columns):
            v = float(df.loc[anno, nome]) if np.isfinite(df.loc[anno, nome]) else 0.0
            x = base_x + j * larghezza_barra
            y = Y(max(v, 0))
            hh = abs(Y(v) - Y(0))
            col = COLORI.get(nome, "#555")
            parti.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{larghezza_barra:.1f}" '
                         f'height="{max(hh,0.5):.1f}" fill="{col}" opacity="0.9"/>')
        parti.append(f'<text x="{base_x + larghezza_gruppo*0.4:.1f}" y="{py+ph+16}" font-size="10" '
                     f'fill="#6b7280" text-anchor="middle">{anno}</text>')
    parti.append(f'<text x="{px}" y="{py-6}" font-size="11.5" fill="#374151">{_esc(titolo)}</text>')
    parti.append("</svg>")
    return "".join(parti)
