# -*- coding: utf-8 -*-
"""
Mini-previsione statistica — cosa è successo DAVVERO, in passato, partendo da una
situazione di mercato come quella di oggi.

Attenzione al vocabolario: qui non si prevede nulla. Si prende la curva della
strategia (Italia / Germania / Francia) dal 2010, si isolano i mesi in cui il
mercato era nello stesso stato di adesso (indice sopra la MM200, ampiezza del
mercato sufficiente) e si guarda come sono andati i 12 mesi successivi a quei
mesi. Il risultato è una distribuzione di esiti passati: mediana, quartili,
casi positivi. È il "più probabile" nel senso di "più frequente in passato",
non di "previsione".

Uso:
    python3 previsione.py                 # tutti i mercati, scrive output/previsione.html
    python3 previsione.py --mercato DE    # solo Germania
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import titoli_italiani as tu      # noqa: E402
import sito                        # noqa: E402

CACHE_DIR = os.path.join(BASE_DIR, "cache")
OUT_DIR = os.path.join(BASE_DIR, "output")

ORIZZONTI = [1, 3, 6, 12]         # mesi

# quale curva rappresenta "il nostro metodo" su ogni mercato
VARIANTE = {
    "IT": "③ + ribilanciamento trimestrale (buffer 5)",
    "DE": "① Base MOM 12-1 top10 + MM200 (mensile)",
    "FR": "① Base MOM 12-1 top10 + MM200 (mensile)",
}
NOTE = {
    "IT": "Regola operativa consigliata (buffer di rank 5, ri-bilanciamento trimestrale).",
    "DE": "Variante base: in Germania ha fatto meglio di quella con buffer (+17,0% contro +15,8%).",
    "FR": "Curva mostrata solo come monitor: in Francia la selezione non ha battuto l'insieme dei titoli.",
}


# ---------------------------------------------------------------------------
#  dati
# ---------------------------------------------------------------------------

def curva_equity(cod: str) -> pd.Series:
    """Curva mensile della strategia per il mercato indicato."""
    nome = "momentum_risk_equity.csv" if cod == "IT" else f"momentum_risk_equity_{cod}.csv"
    d = pd.read_csv(os.path.join(OUT_DIR, nome), sep=";", decimal=",", index_col=0)
    d.index = pd.to_datetime(d.index)
    col = VARIANTE[cod]
    if col not in d.columns:
        raise SystemExit(f"[{cod}] variante non trovata: {col}")
    return d[col].dropna().astype(float)


def stato_mercato(cod: str) -> pd.DataFrame:
    """Per ogni fine mese: indice sopra la MM200? quanti titoli sopra la MM200 (%)?"""
    raw = pd.read_pickle(os.path.join(CACHE_DIR, tu.percorso("momentum_raw.pkl", cod)))
    bm = tu.MERCATI[cod]["benchmark"]

    chiusura = raw[bm].dropna(subset=["Close"])["Close"]
    sopra_indice = (chiusura > chiusura.rolling(200).mean())
    regime = sopra_indice.resample("ME").last()

    sopra = []
    for t in tu.solo_ticker():
        try:
            c = raw[t].dropna(subset=["Close"])["Close"]
            if len(c) > 400:
                sopra.append((c > c.rolling(200).mean()))
        except Exception:
            continue
    breadth = pd.concat(sopra, axis=1).resample("ME").mean().mean(axis=1) * 100
    return pd.DataFrame({"regime": regime, "breadth": breadth})


# ---------------------------------------------------------------------------
#  calcolo
# ---------------------------------------------------------------------------

def _q(x, p):
    return float(np.nanpercentile(x, p)) if len(x) else float("nan")


def stato_oggi(stato: pd.DataFrame) -> tuple[bool, float]:
    """Lo stato di mercato attuale: indice sopra la MM200? ampiezza del mercato?"""
    buono = stato.dropna()
    return bool(buono["regime"].iloc[-1]), float(buono["breadth"].iloc[-1])


def proietta(cod: str, eq: pd.Series, stato: pd.DataFrame, orizzonte: int) -> dict:
    """Distribuzione dei rendimenti a `orizzonte` mesi dai mesi simili a oggi.

    "Simile a oggi" = indice nello stesso stato rispetto alla sua MM200
    (sopra la media come adesso, oppure sotto come adesso).

    Nota di metodo: restringere di più (per esempio "e con la stessa ampiezza di
    mercato") riduce il campione a poche decine di mesi, spesso tutti dello stesso
    episodio storico: i numeri diventano più belli ma molto meno affidabili.
    Meglio un campione largo e una lettura onesta delle fasce."""
    regime_oggi, _ = stato_oggi(stato)
    mesi = list(eq.index)
    posizioni = []
    for i, m in enumerate(mesi):
        if i + orizzonte >= len(mesi):
            continue
        try:
            r = bool(stato.loc[m, "regime"])
        except Exception:
            continue
        if r == regime_oggi:
            posizioni.append(i)

    fwd = np.array([eq.iloc[i + orizzonte] / eq.iloc[i] - 1 for i in posizioni]) * 100
    tutte = np.array([eq.iloc[i + orizzonte] / eq.iloc[i] - 1
                      for i in range(len(mesi) - orizzonte)]) * 100

    def blocco(x, mesi_idx):
        if not len(x):
            return {}
        a = pd.to_datetime(pd.Index(mesi_idx)).values   # le date dei mesi selezionati
        primo = a < pd.Timestamp("2018-01-01")
        pos = sorted(mesi_idx)
        indice_tempo = {m: i for i, m in enumerate(eq.index)}
        episodi = 0
        for i, m in enumerate(pos):
            if i == 0 or indice_tempo[m] != indice_tempo[pos[i - 1]] + 1:
                episodi += 1
        return {
            "n": int(len(x)),
            "episodi": int(episodi),
            "mediana": _q(x, 50), "q25": _q(x, 25), "q75": _q(x, 75),
            "q10": _q(x, 10), "q90": _q(x, 90),
            "positivi_%": float((x > 0).mean() * 100),
            "primo": float(np.nanmedian(x[primo])) if primo.any() else float("nan"),
            "secondo": float(np.nanmedian(x[~primo])) if (~primo).any() else float("nan"),
        }

    return {
        "orizzonte": orizzonte,
        "condizionato": blocco(fwd, [mesi[i] for i in posizioni]),
        "sempre": blocco(tutte, mesi[:len(mesi) - orizzonte]),
    }


def curva_percorsi(cod: str, eq: pd.Series, stato: pd.DataFrame) -> dict:
    """Mediana e fasce per ogni mese da 1 a 12, partendo da oggi."""
    out = {k: [] for k in ("h", "mediana", "q25", "q75", "q10", "q90")}
    for h in range(1, 13):
        d = proietta(cod, eq, stato, h)["condizionato"]
        if not d:
            continue
        out["h"].append(h)
        out["mediana"].append(d["mediana"])
        out["q25"].append(d["q25"])
        out["q75"].append(d["q75"])
        out["q10"].append(d["q10"])
        out["q90"].append(d["q90"])
    return out


# ---------------------------------------------------------------------------
#  grafico (SVG puro, senza librerie e senza risorse esterne)
# ---------------------------------------------------------------------------

def _n(x, dec=1):
    if x is None or not np.isfinite(x):
        return "—"
    s = f"{x:,.{dec}f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return s


def grafico_percorsi(perc: dict, titolo: str, colore="#0a7d3c") -> str:
    """Ventaglio dei percorsi storici: mediana + fascia 25-75 + fascia 10-90."""
    W, H = 760, 300
    ml, mr, mt, mb = 58, 16, 26, 40
    h = perc["h"]
    if not h:
        return ""
    valori = perc["q10"] + perc["q90"] + [0.0]
    lo, hi = min(valori), max(valori)
    margine = max(2.0, (hi - lo) * 0.12)
    lo, hi = lo - margine, hi + margine

    def px(m):        # x: 0..12 mesi
        return ml + (W - ml - mr) * (m / 12.0)

    def py(v):        # y: rendimento %
        return mt + (H - mt - mb) * (hi - v) / (hi - lo)

    def percorso(vals, h_extra=None):
        xs, ys = [px(0)], [py(0)]
        for m, v in zip(h, vals):
            xs.append(px(m)); ys.append(py(v))
        if h_extra == "futuro":
            xs.append(px(12)); ys.append(ys[-1])
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))

    def fascia(sup, inf):
        avanti = " ".join(f"{px(m):.1f},{py(v):.1f}" for m, v in zip(h, sup))
        indietro = " ".join(f"{px(m):.1f},{py(v):.1f}" for m, v in reversed(list(zip(h, inf))))
        return f"M {px(0):.1f},{py(0):.1f} L " + avanti + " L " + indietro + " Z"

    griglia = []
    for v in np.linspace(lo, hi, 5):
        y = py(float(v))
        griglia.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{W-mr}" y2="{y:.1f}" stroke="#e2e8f0" stroke-width="1"/>')
        griglia.append(f'<text x="{ml-6}" y="{y+3.5:.1f}" text-anchor="end" font-size="10.5" fill="#94a3b8">{_n(float(v),0)}%</text>')
    for m in range(0, 13, 3):
        x = px(m)
        griglia.append(f'<line x1="{x:.1f}" y1="{mt}" x2="{x:.1f}" y2="{H-mb}" stroke="#f1f5f9" stroke-width="1"/>')
        etichetta = "oggi" if m == 0 else f"+{m} mesi"
        griglia.append(f'<text x="{x:.1f}" y="{H-mb+16}" text-anchor="middle" font-size="10.5" fill="#94a3b8">{etichetta}</text>')

    y0 = py(0)
    return f"""<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{titolo}" style="max-width:100%;height:auto;display:block">
  <rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff" rx="10"/>
  <text x="{ml}" y="16" font-size="12.5" font-weight="700" fill="#334155">{titolo}</text>
  {''.join(griglia)}
  <line x1="{ml}" y1="{y0:.1f}" x2="{W-mr}" y2="{y0:.1f}" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="4 3"/>
  <path d="{fascia(perc['q90'], perc['q10'])}" fill="{colore}" opacity="0.14"/>
  <path d="{fascia(perc['q75'], perc['q25'])}" fill="{colore}" opacity="0.22"/>
  <polyline points="{percorso(perc['mediana'])}" fill="none" stroke="{colore}" stroke-width="3"/>
  <polyline points="{percorso(perc['q25'])}" fill="none" stroke="{colore}" stroke-width="1.2" opacity="0.55"/>
  <polyline points="{percorso(perc['q75'])}" fill="none" stroke="{colore}" stroke-width="1.2" opacity="0.55"/>
  <circle cx="{px(12):.1f}" cy="{py(perc['mediana'][-1]):.1f}" r="4.5" fill="{colore}"/>
  <text x="{px(12)-8:.1f}" y="{py(perc['mediana'][-1])-9:.1f}" text-anchor="end" font-size="11.5" font-weight="700" fill="{colore}">{_n(perc['mediana'][-1])}%</text>
</svg>"""


# ---------------------------------------------------------------------------
#  pagina
# ---------------------------------------------------------------------------

def avviso_periodi(cod: str, d12: dict) -> str:
    """Se il primo e il secondo periodo raccontano storie diverse, dillo in chiaro."""
    p, q = d12.get("primo", float("nan")), d12.get("secondo", float("nan"))
    if not (np.isfinite(p) and np.isfinite(q)):
        return ""
    if p > 0 and q < p * 0.5:
        testo = (f"⚠️ Attenzione: la mediana a 12 mesi era <b>{_n(p)}%</b> nel primo periodo "
                 f"(2010-2017) e <b>{_n(q)}%</b> nel secondo (2018-2026): il vantaggio visto sopra "
                 f"appartiene soprattutto al passato lontano. Conta più la seconda colonna.")
    elif abs(p - q) <= 5:
        testo = (f"✅ I due periodi raccontano la stessa storia ({_n(p)}% e {_n(q)}%): "
                 f"il comportamento è stabile nel tempo.")
    else:
        testo = (f"I due periodi differiscono un po' ({_n(p)}% e {_n(q)}%): guardali entrambi.")
    return (f'<div style="font-size:12.5px;color:#334155;background:#f8fafc;border-radius:9px;'
            f'padding:10px 12px;margin-top:9px;line-height:1.6">{testo}</div>')


def tabella_html(risultati: dict) -> str:
    righe = []
    for cod, r in risultati.items():
        m = tu.MERCATI[cod]
        righe.append(f'<tr><td colspan="7" style="padding-top:14px;font-weight:800;color:#0f172a">'
                     f'{m["paese"]} — {m["nome"]}</td></tr>')
        for d in r:
            c = d["condizionato"]
            if not c:
                continue
            pos = c["positivi_%"]
            colore = "#0a7d3c" if pos >= 60 else ("#b45309" if pos >= 50 else "#b91c1c")
            righe.append(
                f'<tr style="border-top:1px solid #eef2f7">'
                f'<td style="padding:7px 8px;font-weight:600">{d["orizzonte"]} mesi</td>'
                f'<td style="padding:7px 8px"><b>{_n(c["mediana"])}%</b></td>'
                f'<td style="padding:7px 8px;color:#475569">{_n(c["q25"])}% … {_n(c["q75"])}%</td>'
                f'<td style="padding:7px 8px;color:#94a3b8">{_n(c["q10"])}% … {_n(c["q90"])}%</td>'
                f'<td style="padding:7px 8px;color:{colore};font-weight:700">{_n(pos, 0)}%</td>'
                f'<td style="padding:7px 8px;color:#64748b">{_n(c["primo"])}% · {_n(c["secondo"])}%</td>'
                f'<td style="padding:7px 8px;color:#94a3b8">{c["n"]} · {c.get("episodi", "—")}</td></tr>')
    return f"""<table style="width:100%;border-collapse:collapse;font-size:13px">
  <thead><tr style="color:#64748b;text-align:left;font-size:11.5px;text-transform:uppercase;letter-spacing:.6px">
    <th style="padding:6px 8px">Orizzonte</th><th style="padding:6px 8px">Mediana</th>
    <th style="padding:6px 8px">Metà centrale</th><th style="padding:6px 8px">Quasi tutti</th>
    <th style="padding:6px 8px">Casi positivi</th><th style="padding:6px 8px">1º · 2º periodo</th>
    <th style="padding:6px 8px">Mesi · periodi</th></tr></thead>
  <tbody>{''.join(righe)}</tbody></table>"""


def scrivi_pagina(risultati, contesti, percorsi) -> str:
    sezioni = []
    for cod, r in risultati.items():
        m = tu.MERCATI[cod]
        c = contesti[cod]
        d12 = [d for d in r if d["orizzonte"] == 12][0]["condizionato"]
        sezioni.append(f"""
  <div class="box" style="margin-top:14px">
    <div style="font-size:17px;font-weight:900;margin-bottom:2px">{m['paese']} — {m['nome']}</div>
    <div style="font-size:12.5px;color:#64748b;margin-bottom:10px">{NOTE[cod]}<br>
      oggi: indice <b>{'sopra' if c['regime'] else 'sotto'} la MM200</b> · ampiezza del mercato
      <b>{_n(c['breadth'], 0)}%</b> di titoli sopra la MM200</div>
    {grafico_percorsi(percorsi[cod], f"Percorsi storici dopo mesi come questo — {m['paese']}")}
    <div style="font-size:13px;color:#334155;line-height:1.7;margin-top:10px">
      A 12 mesi la <b>mediana</b> dei casi simili è <b>{_n(d12['mediana'])}%</b>, con la metà centrale
      dei casi fra {_n(d12['q25'])}% e {_n(d12['q75'])}% e il 90% fra {_n(d12['q10'])}% e {_n(d12['q90'])}%.
      Esito positivo nel <b>{_n(d12['positivi_%'], 0)}%</b> dei casi ({d12['n']} mesi simili, in
      {d12.get('episodi', '—')} periodi distinti, su {len(curva_equity(cod))} mesi di storia).
      La fascia "quasi tutti i casi" è larga <b>{_n(d12['q90'] - d12['q10'], 0)} punti</b>: è questa
      l'incertezza vera, non il numero in mezzo.
    </div>
    {avviso_periodi(cod, d12)}
  </div>""")

    html = f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mini-previsione statistica — Italia · Germania · Francia</title>
<style>
  body {{ margin:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a }}
  .contenitore {{ max-width:860px;margin:0 auto;padding:16px 12px 36px }}
  .box {{ background:#fff;border-radius:12px;padding:16px 18px;box-shadow:0 1px 3px rgba(15,23,42,.08) }}
  svg {{ max-width:100%;height:auto;display:block }}
</style></head>
<body><div class="contenitore">
  {sito.nav_html('previsione.html')}
  <div style="background:#0f172a;color:#fff;border-radius:14px;padding:20px">
    <div style="font-size:12px;letter-spacing:1.2px;text-transform:uppercase;color:#94a3b8">
      Mini-previsione statistica · {datetime.now().strftime('%d/%m/%Y')}</div>
    <div style="font-size:23px;font-weight:900;margin:8px 0 6px">Dove sono andate a finire, in passato, le situazioni come questa</div>
    <div style="color:#cbd5e1;font-size:13.5px;line-height:1.6">
      Non è una previsione del prezzo: è la distribuzione degli esiti realmente accaduti dal 2010
      nei mesi con lo stesso stato di mercato di oggi. Serve a sapere quanto è larga la fascia,
      non a indovinare il numero finale.</div>
  </div>

  <div class="box" style="margin-top:14px">
    <div style="font-size:13px;letter-spacing:1px;color:#64748b;text-transform:uppercase;font-weight:700;margin-bottom:8px">
      Come leggerla</div>
    <div style="font-size:13.5px;color:#334155;line-height:1.75">
      • la <b>linea piena</b> è la mediana: metà dei casi passati è finita sopra, metà sotto;<br>
      • la <b>fascia scura</b> contiene la metà centrale dei casi, la <b>fascia chiara</b> il 90%;<br>
      • "casi positivi" è quante volte l'esito è stato in guadagno;<br>
      • la colonna <b>1º · 2º periodo</b> spezza la storia in 2010-2017 e 2018-2026: se i due
      numeri sono simili, la tendenza è stabile nel tempo.
    </div>
  </div>

  {''.join(sezioni)}

  <div class="box" style="margin-top:14px">
    <div style="font-size:13px;letter-spacing:1px;color:#64748b;text-transform:uppercase;font-weight:700;margin-bottom:8px">
      Tutti i numeri</div>
    {tabella_html(risultati)}
  </div>

  <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;padding:14px 16px;margin-top:14px;font-size:12.5px;color:#7c2d12;line-height:1.75">
    <b>Come si usa in pratica:</b> la regola operativa è in
    <a href="operativo.html" style="color:#9a3412;font-weight:700">Operativo →</a><br><br>
    <b>Cosa questa pagina non è.</b> Non è una previsione: nessuno dei nostri dati contiene il futuro.
    La fascia a 12 mesi è larga decine di punti percentuali, e in un caso su tre il risultato è stato
    negativo. La regola della strategia non cambia: <b>si controlla una volta al mese e si esce per
    regola, mai a target</b> — la "mediana" qui sopra non è un obiettivo di prezzo e non deve diventare
    un motivo per non vendere quando la regola dice di vendere.
  </div>
</div></body></html>"""
    percorso = os.path.join(OUT_DIR, "previsione.html")
    with open(percorso, "w", encoding="utf-8") as f:
        f.write(html)
    return percorso


# ---------------------------------------------------------------------------

def genera(codici=None, verboso: bool = True) -> str:
    """Calcola i ventagli e scrive output/previsione.html.

    Richiamabile da dashboard.py (senza argparse). `codici=None` = tutti i mercati."""
    codici = list(tu.elenco_mercati()) if codici is None else list(codici)
    mercato_iniziale = tu.mercato       # alla fine si torna al mercato di partenza

    risultati, contesti, percorsi = {}, {}, {}
    for cod in codici:
        tu.imposta_mercato(cod)
        eq = curva_equity(cod)
        stato = stato_mercato(cod)
        r = [proietta(cod, eq, stato, h) for h in ORIZZONTI]
        risultati[cod] = r
        ultimo = stato.dropna().iloc[-1]
        contesti[cod] = {"regime": bool(ultimo["regime"]), "breadth": float(ultimo["breadth"])}
        percorsi[cod] = curva_percorsi(cod, eq, stato)

        if verboso:
            print(f"\n=== {cod} · {tu.MERCATI[cod]['paese']} — oggi: indice "
                  f"{'sopra' if contesti[cod]['regime'] else 'sotto'} MM200, breadth {contesti[cod]['breadth']:.0f}% ===")
            for d in r:
                c = d["condizionato"]
                s = d["sempre"]
                print(f"  {d['orizzonte']:>2} mesi: mediana {c['mediana']:6.1f}%  "
                      f"[{c['q25']:6.1f} … {c['q75']:6.1f}]  10-90 [{c['q10']:6.1f} … {c['q90']:6.1f}]  "
                      f"positivi {c['positivi_%']:.0f}%  (n={c['n']} in {c['episodi']} periodi, "
                      f"1º {c['primo']:.1f}% / 2º {c['secondo']:.1f}%, senza condizione {s['mediana']:.1f}%)")

    percorso = scrivi_pagina(risultati, contesti, percorsi)
    tu.imposta_mercato(mercato_iniziale)
    return percorso


def main() -> int:
    ap = argparse.ArgumentParser(description="Mini-previsione statistica dai percorsi storici")
    ap.add_argument("--mercato", default="TUTTI", help="IT, DE, FR oppure TUTTI (default)")
    args = ap.parse_args()
    codici = None if args.mercato.upper() in ("TUTTI", "ALL", "*") else [args.mercato.upper()]
    percorso = genera(codici)
    print(f"\nPagina: {percorso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
