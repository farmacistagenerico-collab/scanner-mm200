#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GRAFICI — SVG generati in casa (nessuna libreria esterna, nessun CDN)
=====================================================================

Due grafici, pensati per stare accanto ai numeri della dashboard:

  1. `grafico_prezzo(...)` — il grafico di un titolo: prezzo (blu), MM200 /
     livello di uscita (arancio, tratteggiato), atteso a 12 mesi (verde) e
     ultimo prezzo. Serve a vedere *a occhio* quanto margine c'è prima di uscire.
  2. `grafico_equity(...)` — la curva della strategia (buffer 5) contro universo
     e portafogli casuali: serve a ricordare cosa aspettarsi, non a prevedere.

Gli SVG sono autonomi (nessuna risorsa esterna): si vedono anche nel preview
senza rete. Font di sistema, colori coerenti con le pagine.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BLU = "#1d4ed8"
ARANCIO = "#b45309"
VERDE = "#0a7d3c"
ROSSO = "#b91c1c"
GRIGIO = "#94a3b8"
SCURO = "#0f172a"


def _num(x: float, dec: int = 2) -> str:
    out = f"{x:,.{dec}f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return out.replace("-", "\u2212")


def _scala(valori: list[np.ndarray], h: float, pad_t: float, pad_b: float):
    """Ritorna (min, max, y(v)) per il grafico."""
    v = np.concatenate([np.asarray(a, dtype=float) for a in valori if len(a)])
    v = v[np.isfinite(v)]
    lo, hi = float(v.min()), float(v.max())
    if hi <= lo:
        hi = lo + 1
    margine = (hi - lo) * 0.06
    lo, hi = lo - margine, hi + margine
    scala = (h - pad_t - pad_b) / (hi - lo)

    def y(vv):
        return pad_t + (hi - vv) * scala

    return lo, hi, y


def _percorso(xs, ys, f_x, f_y) -> str:
    punti = [f"{f_x(x):.1f},{f_y(y):.1f}" for x, y in zip(xs, ys) if np.isfinite(y)]
    return "M" + " L".join(punti) if punti else ""


def grafico_prezzo(nome: str, punteggio: float, date, prezzi, mm200,
                   uscita: float, target: float, w: int = 380, h: int = 176,
                   delta: float | None = None) -> str:
    """Mini grafico: prezzo, MM200 (livello di uscita) e atteso a 12 mesi."""
    prezzi = np.asarray(prezzi, dtype=float)
    mm200 = np.asarray(mm200, dtype=float)
    n = len(prezzi)
    if n < 5:
        return ""

    pad_l, pad_r, pad_t, pad_b = 8, 78, 30, 20
    lo, hi, y = _scala([prezzi, mm200, np.array([uscita, target])], h, pad_t, pad_b)
    x = lambda i: pad_l + i * (w - pad_l - pad_r) / (n - 1)          # noqa: E731

    col_p = VERDE if (delta or 0) >= 0 else ROSSO
    parti = [
        f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Roboto,sans-serif">',
        f'<text x="{pad_l}" y="13" font-size="12.5" font-weight="700" fill="{SCURO}">{nome[:24]}</text>',
        f'<text x="{w - pad_r + 4}" y="13" font-size="13.5" font-weight="800" fill="'
        f'{VERDE if punteggio >= 72 else (ARANCIO if punteggio >= 62 else ROSSO)}">{_num(punteggio, 0)}</text>',
    ]
    # variazione di giornata
    if delta is not None and np.isfinite(delta):
        segno = "+" if delta >= 0 else ""
        parti.append(f'<text x="{pad_l + 160}" y="13" font-size="10.5" fill="{col_p}">'
                     f'{segno}{_num(delta, 2)}% oggi</text>')

    # riempimento sotto il prezzo
    area = _percorso(np.arange(n), prezzi, x, y)
    if area:
        parti.append(f'<path d="{area} L{x(n-1):.1f},{h-pad_b:.1f} L{pad_l:.1f},{h-pad_b:.1f} Z" '
                     f'fill="{BLU}" opacity="0.07"/>')
    # MM200 (linea di uscita mobile)
    parti.append(f'<path d="{_percorso(np.arange(n), mm200, x, y)}" fill="none" stroke="{ARANCIO}" '
                 f'stroke-width="1.3" stroke-dasharray="4 3" opacity="0.9"/>')
    # livello di uscita di oggi (orizzontale, in evidenza)
    inizio_uscita = int(n * 0.55)
    parti.append(f'<line x1="{x(inizio_uscita):.1f}" y1="{y(uscita):.1f}" x2="{w-pad_r+2:.1f}" '
                 f'y2="{y(uscita):.1f}" stroke="{ROSSO}" stroke-width="1" stroke-dasharray="2 2" opacity="0.75"/>')
    # atteso a 12 mesi
    if lo < target < hi:
        parti.append(f'<line x1="{pad_l}" y1="{y(target):.1f}" x2="{w-pad_r:.1f}" y2="{y(target):.1f}" '
                     f'stroke="{VERDE}" stroke-width="1" stroke-dasharray="5 4" opacity="0.8"/>')
    # prezzo
    parti.append(f'<path d="{_percorso(np.arange(n), prezzi, x, y)}" fill="none" stroke="{BLU}" '
                 f'stroke-width="1.7" stroke-linejoin="round"/>')
    # ultimo punto
    parti.append(f'<circle cx="{x(n-1):.1f}" cy="{y(prezzi[-1]):.1f}" r="2.6" fill="{BLU}"/>')

    # etichette a destra (posizioni aggiustate per non uscire dal riquadro)
    for valore, colore, etichetta in ((prezzi[-1], BLU, "prezzo"),
                                      (uscita, ARANCIO, "uscita"),
                                      (target, VERDE, "atteso")):
        yy = min(max(y(valore), pad_t + 8), h - pad_b - 1)
        parti.append(f'<text x="{w-pad_r+4}" y="{yy+3:.1f}" font-size="9.5" fill="{colore}">'
                     f'{_num(valore, 2)} € <tspan fill="{GRIGIO}">{etichetta}</tspan></text>')

    # date
    d0, d1 = pd.Timestamp(date[0]).strftime("%m/%y"), pd.Timestamp(date[-1]).strftime("%m/%y")
    parti.append(f'<text x="{pad_l}" y="{h-6}" font-size="9" fill="{GRIGIO}">{d0}</text>')
    parti.append(f'<text x="{w-pad_r}" y="{h-6}" font-size="9" fill="{GRIGIO}" '
                 f'text-anchor="end">{d1}</text>')
    parti.append("</svg>")
    return "".join(parti)


def grafico_equity(df: pd.DataFrame, serie: dict[str, tuple[str, str]], titolo: str = "",
                   w: int = 880, h: int = 215) -> str:
    """Curve di equity normalizzate a 100 con etichette finali.

    `serie`: etichetta -> (nome della colonna nel DataFrame, colore).
    """
    pad_l, pad_r, pad_t, pad_b = 8, 152, 26, 22
    dati = {}
    for nome, (col, colore) in serie.items():
        if col in df.columns:
            s = df[col].dropna()
            if len(s) > 12:
                dati[nome] = (s / s.iloc[0] * 100, colore)
    if not dati:
        return ""
    n_max = max(len(v[0]) for v in dati.values())
    lo, hi, y = _scala([v[0].values for v in dati.values()], h, pad_t, pad_b)
    x = lambda i, n: pad_l + i * (w - pad_l - pad_r) / (n - 1)      # noqa: E731

    parti = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
             f'xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Roboto,sans-serif">']
    if titolo:
        parti.append(f'<text x="{pad_l}" y="13" font-size="12.5" font-weight="700" fill="{SCURO}">{titolo}</text>')
    # linea del 100
    parti.append(f'<line x1="{pad_l}" y1="{y(100):.1f}" x2="{w-pad_r:.1f}" y2="{y(100):.1f}" '
                 f'stroke="{GRIGIO}" stroke-width="1" stroke-dasharray="4 4" opacity="0.6"/>')

    etichette = []
    for nome, (s, colore) in dati.items():
        valori = s.values
        n = len(valori)
        spesso = 2.2 if "buffer" in nome else (1.5 if "Universo" in nome else 1.1)
        parti.append(f'<path d="{_percorso(np.arange(n), valori, lambda i: x(i, n), y)}" fill="none" '
                     f'stroke="{colore}" stroke-width="{spesso}" opacity="{0.95 if spesso > 1.4 else 0.75}"/>')
        etichette.append((y(valori[-1]), colore, f'{nome[:18]} · {_num(valori[-1], 0)}'))
    etichette.sort()
    usati = []
    for yy, colore, testo in etichette:
        while usati and abs(yy - usati[-1]) < 11:
            yy += 11
        usati.append(yy)
        parti.append(f'<text x="{w-pad_r+4}" y="{min(yy, h-pad_b) + 3:.1f}" font-size="9.5" '
                     f'fill="{colore}">{testo}</text>')
    parti.append(f'<text x="{pad_l}" y="{h-6}" font-size="9" fill="{GRIGIO}">'
                 f'{df.index[0].strftime("%Y-%m")} → {df.index[-1].strftime("%Y-%m")} · scala lineare, base 100</text>')
    parti.append("</svg>")
    return "".join(parti)
