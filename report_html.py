# -*- coding: utf-8 -*-
"""
Generazione del report HTML autonomo (CSS e JS inline, nessuna risorsa esterna).
"""
from __future__ import annotations

import os
from datetime import datetime

import pandas as pd

COLORI = {
    "IN AVVICINAMENTO (sotto)": ("#0d5aa7", "#e8f1fb"),
    "ROTTURA CONFERMATA": ("#0b7a3b", "#e6f7ec"),
    "ROTTURA DA CONFERMARE": ("#8a6d00", "#fff8e1"),
    "FALSO BREAKOUT / RIENTRO": ("#a11212", "#fdecea"),
    "IN PROSSIMITÀ (sotto)": ("#0d5aa7", "#e8f1fb"),
    "IN PROSSIMITÀ (sopra)": ("#0d5aa7", "#e8f1fb"),
    "TREND RIALZISTA (già sopra)": ("#2e7d32", "#f1f8f2"),
    "TREND RIBASSISTA (sotto)": ("#7f1d1d", "#f7f1f1"),
    "ROTTURA RIBASSISTA": ("#a11212", "#fdecea"),
    "NEUTRO": ("#555", "#f5f5f5"),
}

CSS = """
:root { --bordo:#e3e6ea; --testo:#1c1f23; --muto:#6b7280; }
* { box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
       margin:0; background:#f6f7f9; color:var(--testo); }
.wrap { max-width:1180px; margin:0 auto; padding:28px 20px 60px; }
header { background:linear-gradient(135deg,#0b2545,#133b63); color:#fff; padding:26px 20px; }
header .inner { max-width:1180px; margin:0 auto; }
header h1 { margin:0 0 6px; font-size:24px; letter-spacing:-.3px; }
header p { margin:0; opacity:.85; font-size:14px; }
.cards { display:flex; gap:14px; flex-wrap:wrap; margin:22px 0; }
.card { background:#fff; border:1px solid var(--bordo); border-radius:10px; padding:14px 16px; flex:1 1 210px; }
.card .k { font-size:12px; text-transform:uppercase; letter-spacing:.4px; color:var(--muto); }
.card .v { font-size:20px; font-weight:600; margin-top:4px; }
.card .s { font-size:12px; color:var(--muto); margin-top:2px; }
h2 { font-size:17px; margin:30px 0 10px; }
h2 span { color:var(--muto); font-weight:400; font-size:13px; }
table { width:100%; border-collapse:collapse; background:#fff; border:1px solid var(--bordo);
        border-radius:10px; overflow:hidden; font-size:13px; }
th, td { padding:8px 10px; text-align:left; border-bottom:1px solid var(--bordo); }
th { background:#eef1f5; font-size:11.5px; text-transform:uppercase; letter-spacing:.4px;
     color:#374151; cursor:pointer; user-select:none; white-space:nowrap; }
th:hover { background:#e2e7ee; }
tr:last-child td { border-bottom:none; }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
.pill { display:inline-block; padding:2px 8px; border-radius:99px; font-size:11.5px; font-weight:600;
        white-space:nowrap; }
.score { font-weight:700; }
.bar { height:6px; border-radius:3px; background:#e5e7eb; width:70px; display:inline-block;
       vertical-align:middle; margin-right:6px; }
.bar i { display:block; height:100%; border-radius:3px; background:#0d5aa7; }
.pos { color:#0b7a3b; } .neg { color:#a11212; }
.muted { color:var(--muto); }
.flag { font-size:11.5px; color:#4b5563; }
details { background:#fff; border:1px solid var(--bordo); border-radius:10px; padding:12px 16px; margin-top:12px; }
summary { cursor:pointer; font-weight:600; font-size:14px; }
details p, details li { font-size:13px; line-height:1.55; color:#374151; }
footer { margin-top:34px; font-size:12px; color:var(--muto); line-height:1.6; }
.note { background:#fff8e1; border:1px solid #f2e0a8; border-radius:10px; padding:12px 16px;
        font-size:13px; color:#6b5b00; margin-top:18px; }
"""

JS_ORDINA = """
document.querySelectorAll('table.sortable th').forEach(function(th, i){
  let asc = false;
  th.addEventListener('click', function(){
    const tb = th.closest('table').tBodies[0];
    const righe = Array.from(tb.rows);
    asc = !asc;
    righe.sort(function(a,b){
      const x = a.cells[i].getAttribute('data-v') ?? a.cells[i].innerText;
      const y = b.cells[i].getAttribute('data-v') ?? b.cells[i].innerText;
      const nx = parseFloat(x), ny = parseFloat(y);
      if (!isNaN(nx) && !isNaN(ny)) return asc ? nx-ny : ny-nx;
      return asc ? String(x).localeCompare(String(y)) : String(y).localeCompare(String(x));
    });
    righe.forEach(r => tb.appendChild(r));
  });
});
"""


def _fmt(v, dec=2, segno=False, pct=False):
    try:
        if v is None or pd.isna(v):
            return "—"
        s = f"{v:+.{dec}f}" if segno else f"{v:.{dec}f}"
        return s + ("%" if pct else "")
    except Exception:
        return "—"


def _pill(etichetta):
    col, bg = COLORI.get(etichetta, COLORI["NEUTRO"])
    return f'<span class="pill" style="color:{col};background:{bg}">{etichetta}</span>'


def _riga(t, r):
    d = r["distanza_pct"]
    classe_d = "pos" if d > 0 else "neg"
    pt = r["punteggio"]
    barra = f'<span class="bar"><i style="width:{min(100, max(0, pt)):.0f}%;background:{"#0b7a3b" if pt>=70 else "#0d5aa7" if pt>=55 else "#8a8f98"}"></i></span>'
    return f"""<tr>
      <td><b>{t}</b><div class="muted" style="font-size:11.5px">{r['nome']}</div></td>
      <td>{_pill(r['etichetta'])}</td>
      <td class="num" data-v="{r['close']:.4f}">{_fmt(r['close'])}</td>
      <td class="num" data-v="{0 if pd.isna(r['mm200']) else r['mm200']:.4f}">{_fmt(r['mm200'])}</td>
      <td class="num {classe_d}" data-v="{d:.4f}">{_fmt(d, segno=True, pct=True)}</td>
      <td class="num" data-v="{0 if pd.isna(r['distanza_atr']) else r['distanza_atr']:.3f}">{_fmt(r['distanza_atr'], 2, segno=True)}</td>
      <td class="num" data-v="{0 if 'dd_252' not in r or pd.isna(r['dd_252']) else r['dd_252']:.3f}">{_fmt(r['dd_252'] if 'dd_252' in r else None, 1, segno=True, pct=True)}</td>
      <td class="num" data-v="{r.get('score_validato', 0)}"><b style="color:{'#0b7a3b' if r.get('score_validato',0)>=2 else '#8a6d00' if r.get('score_validato',0)==1 else '#6b7280'}">{r.get('score_validato', 0):+d}</b></td>
      <td class="num" data-v="{r['punteggio']:.1f}">{barra}<span class="score">{pt:.0f}</span></td>
      <td class="num" data-v="{0 if pd.isna(r['vol_ratio']) else r['vol_ratio']:.3f}">{_fmt(r['vol_ratio'], 2)}x</td>
      <td class="num" data-v="{r['rsi14']:.2f}">{_fmt(r['rsi14'], 1)}</td>
      <td class="num" data-v="{0 if pd.isna(r['atr_pct']) else r['atr_pct']:.3f}">{_fmt(r['atr_pct'], 2, pct=True)}</td>
      <td class="num" data-v="{0 if pd.isna(r['slope_mm200_20g']) else r['slope_mm200_20g']:.3f}">{_fmt(r['slope_mm200_20g'], 2, segno=True, pct=True)}</td>
      <td class="num" data-v="{0 if pd.isna(r['ret_6m']) else r['ret_6m']:.3f}">{_fmt(r['ret_6m'], 1, segno=True, pct=True)}</td>
      <td style="text-align:center" data-v="{1 if r['sopra_weekly_mm40'] else 0}">{'✔' if r['sopra_weekly_mm40'] else '—'}</td>
      <td class="flag">{r.get('flag_significativita','') or ''}</td>
    </tr>"""


def _tabella(df):
    if df.empty:
        return '<p class="muted">Nessun titolo in questa categoria.</p>'
    intest = "".join(f"<th>{h}</th>" for h in
                     ["Titolo", "Stato", "Prezzo", "MM200", "Dist. MM200", "Dist. ATR", "DD 52w",
                      "Score OOS", "Punteggio", "Vol. rel.", "RSI", "ATR%", "Pend. MM200 20g",
                      "Rend. 6m", "Settim.", "Note"])
    return f'<table class="sortable"><thead><tr>{intest}</tr></thead><tbody>{"".join(_riga(t, r) for t, r in df.iterrows())}</tbody></table>'


def scrivi_report(df, mercato, cfg, mancanti, out_dir, data_rif):
    """Scrive il report HTML e ritorna il percorso."""
    candidati = df[df["candidato"]].sort_values("punteggio", ascending=False)
    rotture = df[df["etichetta"].isin(["ROTTURA CONFERMATA", "ROTTURA DA CONFERMARE"])] \
        .sort_values("punteggio", ascending=False)
    pronte = df[df["etichetta"].isin(["IN PROSSIMITÀ (sotto)", "IN PROSSIMITÀ (sopra)",
                                      "IN AVVICINAMENTO (sotto)"])].sort_values("distanza_pct")
    falsi = df[df["etichetta"] == "FALSO BREAKOUT / RIENTRO"].sort_values("punteggio", ascending=False)
    ribassi = df[df["etichetta"].isin(["ROTTURA RIBASSISTA", "TREND RIBASSISTA (sotto)"])] \
        .sort_values("distanza_pct")
    trend = df[df["etichetta"] == "TREND RIALZISTA (già sopra)"].sort_values("distanza_pct")

    m = mercato or {}
    regime = m.get("regime", "n/d")
    cards = f"""
    <div class="cards">
      <div class="card"><div class="k">Contesto indice</div><div class="v">{m.get('indice','—')} {_fmt(m.get('close'))}</div>
        <div class="s">{regime} · dist. MM200 {_fmt(m.get('distanza_pct'),2,True,True)}</div></div>
      <div class="card"><div class="k">Titoli analizzati</div><div class="v">{len(df)}</div>
        <div class="s">{len(mancanti)} esclusi (dati insufficienti/delistati)</div></div>
      <div class="card"><div class="k">Selezione finale</div><div class="v">{len(candidati)}</div>
        <div class="s">punteggio ≥ {cfg['soglia_punteggio']:.0f}</div></div>
      <div class="card"><div class="k">Rotture ultimi 5 gg</div><div class="v">{len(rotture)}</div>
        <div class="s">{len(falsi)} falsi breakout/rientri</div></div>
    </div>"""

    def sezione(titolo, sotto, nota=""):
        n = f" <span>({len(sotto)})</span>" if len(sotto) else ""
        nota_html = f'<p class="muted" style="font-size:12.5px;margin:6px 0 10px">{nota}</p>' if nota else ""
        return f"<h2>{titolo}{n}</h2>{nota_html}{_tabella(sotto)}"

    if "setup_settimanale" in df.columns:
        # "vicino" = il titolo è ancora nei pressi della MM200 (rottura fresca o retest),
        # non un trend già maturato e lontano dalla media
        vicino = (df["distanza_pct"] <= 5) & (df["distanza_pct"] >= -cfg["distanza_prontezza_pct"])
        validati = df[((df["setup_settimanale"]) | (df["settimanale_ok"])) & vicino] \
            .sort_values("punteggio", ascending=False)
        trend_validati = df[(df["setup_settimanale"]) & (~vicino)] \
            .sort_values("punteggio", ascending=False).head(15)
    else:
        validati, trend_validati = pd.DataFrame(), pd.DataFrame()

    if "score_validato" in df.columns:
        val_oos = df[df["score_validato"] >= 3].sort_values(["score_validato", "punteggio"], ascending=False)
    else:
        val_oos = pd.DataFrame()

    corpo = (
        sezione("★★★ Score validato out-of-sample (calibrato 2005-2015, confermato 2016-2026)", val_oos,
                "Titoli che soddisfano la combinazione validata fuori campione: deep recovery, MM200 in salita, "
                "MM50 sopra MM200, forza relativa ≥50° percentile, senza penalità (vicino ai massimi). "
                "Nel test out-of-sample (2016-2026) lo score ordina l'excess rispetto alla baseline di stato in modo "
                "monotòno: +4 → +18,4% | +3 → +8,5% | +2 → +1,7% | +1 → −1,7% | ≤0 → −4,2% "
                "(≥+3 vs resto: +11,4% contro −2,9%, n=185; ≥+2 vs resto: t=3,19, p=0,0014). "
                "La soglia operativa mostrata qui è ≥+3: più selettiva e con l'excess più alto.")
        + sezione("★★ Segnale settimanale supportato dalla ricerca (campione piccolo: ~2-3 segnali/anno)", validati,
                "Titoli che rispettano l'unica combinazione sopravvissuta ai controlli di robustezza "
                "(finestre non sovrapposte e leave-one-out): volume settimanale ≥1,5x la media, MM40 "
                "settimanale in salita, MM10 sopra MM40, conferma mensile. Storico: +34,6% a 12 mesi contro "
                "+13% di un periodo qualunque (n=53, p ≈ 0,006) — ma il campione è piccolissimo e la resa "
                "si è dimezzata nell'ultimo decennio: trattarlo come spunto di attenzione, non come certezza.")
        + sezione("★ Selezione finale — candidati con punteggio più alto", candidati,
                "Titoli che soddisfano i filtri di significatività: vicinanza alla MM200, "
                "struttura di trend in miglioramento, momentum costruttivo e partecipazione dei volumi.")
        + sezione("A) Rotture appena avvenute (ultimi 5 giorni)", rotture,
                  "Chiuse oltre la MM200 con buffer. 'Confermata' = volume ≥ "
                  f"{cfg['volume_conferma']:.1f}x la media; 'da confermare' = volume debole (rischio falso breakout).")
        + sezione("B) Pronti a rompere al rialzo (prezzo a ridosso della MM200)", pronte,
                  f"Prezzo entro la fascia ±{cfg['buffer_stato_pct']:.1f}% attorno alla media, oppure in "
                  f"avvicinamento dal basso entro il {cfg['distanza_prontezza_pct']:.0f}% e con rimbalzo già "
                  "avviato (prezzo sopra la MM20 e rendimento 3 mesi non in caduta). Sono i titoli su cui "
                  "tenere l'allerta nelle prossime sedute.")
        + sezione("C) Già in trend sopra la MM200 (contesto)", trend)
        + sezione("C-bis) Setup validati già lontani dalla media (trend maturi)", trend_validati,
                  "Stessa combinazione di filtri della sezione ★★, ma con il prezzo ormai molto distante dalla "
                  "MM200: non sono più titoli 'pronti a rompere', sono trend già in corso (utili semmai in un "
                  "approccio di continuazione, non di breakout).")
        + sezione("D) Falsi breakout / rientri sotto la media", falsi,
                  "Segnali recenti rientrati sotto la media: statisticamente sono la categoria con il "
                  "tasso di successo più basso (in letteratura i breakout senza volumi hanno win rate dichiarati "
                  "vicini al 27-37% contro il 60-70% di quelli con volumi ≥1,5-2x).")
        + sezione("E) Sotto la MM200 — ribassiste (escluse dalla selezione)", ribassi)
    )

    ricerca = """
    <details open>
      <summary>📊 Cosa dice la ricerca (2005-2026, ~130 titoli di Piazza Affari)</summary>
      <ul>
        <li><b>Rottura "grezza" della MM200</b>: +11,6% a 12 mesi contro +12,8% di un periodo qualunque →
            <b>nessun vantaggio statistico</b>.</li>
        <li><b>Il volume non filtra</b>: 13 misure testate (livello, percentile, OBV, MFI, compressione,
            volume sostenuto, conferma a 3 giorni…), dose-risposta piatta, nessun effetto.</li>
        <li><b>Quasi tutti i filtri "popolari" sono solo market timing</b>: su 22 testati, regime del MIB,
            breadth, forza relativa e bassa volatilità battono la rottura media ma <u>non</u> la baseline del
            medesimo stato di mercato (es. con MIB sopra la MM200 le rotture fanno +8,7% contro +10,6% di un
            periodo qualunque in quello stesso stato). Nessuna informazione in più sulla qualità della rottura.</li>
        <li><b>L'unico filtro con evidenza specifica sulla rottura è il contesto di prezzo</b>: le rotture in
            <b>deep recovery</b> (titolo ancora ≥20% sotto il massimo a 12 mesi) rendono +16,3% contro +12,1%
            della baseline dello stesso stato (+4,2 punti di excess), con <b>meno falsi breakout</b> (61% vs 67%)
            e reggono il controllo a finestre non sovrapposte (+19,5% vs +10,2%, p≈0,001). Le rotture vicine ai
            massimi hanno invece excess <u>negativo</u> (−2,9 punti).</li>
        <li><b>✅ Validato fuori campione</b> (calibrazione 2005-2015 → verifica 2016-2026): deep recovery
            excess <b>+5,2 punti</b> (p=0,039), non sovrapposte <b>+25,8% vs +11,2%</b> (p=0,0004); il filtro
            si replica anche su <b>56 large cap europee</b> (+8,2 punti di excess, win rate 81,7%, p&lt;0,0001)
            — mercati su cui non è stata fatta alcuna calibrazione.</li>
        <li><b>Score validato OOS</b> (punti fissi: +1 recovery, +1 MM200 in salita, +1 MM50&gt;MM200,
            +1 forza relativa, −1 vicino ai massimi): excess medio monotòno nel 2016-2026 →
            +4: +18,4% · +3: +8,5% · +2: +1,7% · +1: −1,7% · ≤0: −4,2%.</li>
        <li><b>Cautela</b>: la deep recovery è più rischiosa (nel 2008 perse in media −20,7%) e l'excess è
            positivo in media, non in ogni anno; la rottura resta un evento da gestire con stop e size.</li>
      </ul>
    </details>"""

    metodologia = f"""
    <details open>
      <summary>Metodologia e parametri attivi</summary>
      <ul>
        <li><b>MM200</b> semplice su chiusure adjusted, calcolata su barre giornaliere;
            storia minima richiesta: {cfg['min_barre']} sedute.</li>
        <li><b>Buffer anti-rumore</b>: la fascia ±{cfg['buffer_stato_pct']:.1f}% attorno alla MM200 è
            considerata "zona di transizione" — un attraversamento non è una rottura.</li>
        <li><b>Zona di prontezza</b>: prezzo entro {cfg['distanza_prontezza_pct']:.0f}% sotto (o appena sopra)
            la MM200.</li>
        <li><b>Significatività statistica</b>: distanza dalla media anche in unità di ATR (≥0,25 ATR =
            movimento non attribuibile al rumore) e volume relativo ≥ {cfg['volume_conferma']:.1f}x la media a 50 sedute.</li>
        <li><b>Conferma multi-timeframe</b>: controllo sul grafico settimanale (MM40 settimanale ≈ MM200 giornaliera).</li>
        <li><b>Filtro anti-whipsaw</b>: penalità per titoli con ≥6 attraversamenti della MM200 negli ultimi 3 anni.</li>
        <li><b>Punteggio 0-100</b>: 35 pt struttura di trend, 25 pt prossimità alla media, 12 pt qualità,
            8 pt volumi (solo partecipazione), 20 pt contesto di prezzo deep recovery; soglia {cfg['soglia_punteggio']:.0f}.</li>
      </ul>
    </details>"""

    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scanner MM200 — Borsa Italiana {data_rif[6:8]}/{data_rif[4:6]}/{data_rif[:4]}</title>
<style>{CSS}</style>
</head>
<body>
<header><div class="inner">
  <h1>Scanner MM200 — Piazza Affari</h1>
  <p>Titoli pronti a rompere la media mobile a 200 periodi · analisi del {data_rif[6:8]}/{data_rif[4:6]}/{data_rif[:4]}
     · generato il {datetime.now():%d/%m/%Y %H:%M}</p>
</div></header>
<div class="wrap">
  {cards}
  {corpo}
  {ricerca}
  {metodologia}
  <div class="note"><b>Nota</b>: questo report è uno strumento di analisi tecnica automatizzata, non una
  raccomandazione di investimento. Le probabilità storiche non garantiscono risultati futuri; ogni segnale
  va validato con gestione del rischio (stop, sizing) e, se serve, con l'analisi fondamentale del titolo.</div>
  <footer>
    Dati: Yahoo Finance (chiusure adjusted, fonte Borsa Italiana). Universo di partenza: FTSE MIB, FTSE Italia Mid Cap,
    FTSE Italia STAR ({len(df) + len(mancanti)} ticker testati, {len(df)} con storia sufficiente).
    {"Ticker senza dati sufficienti: " + ", ".join(mancanti) if mancanti else ""}
  </footer>
</div>
<script>{JS_ORDINA}</script>
</body></html>"""

    path = os.path.join(out_dir, f"report_mm200_{data_rif}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
