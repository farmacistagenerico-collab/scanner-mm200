# -*- coding: utf-8 -*-
"""
Elementi comuni alle pagine del sito: la barra di navigazione.

Tutte le pagine pubblicate (Italia, Germania, Francia, Punteggi, Operativo,
Previsione) la usano, così ci si muove fra le sezioni dal telefono con un tocco.
"""

from __future__ import annotations

import titoli_italiani as tu

# (file pubblicato, etichetta, codice mercato o None)
VOCI = [
    ("index.html", "Italia", "IT"),
    ("de.html", "Germania", "DE"),
    ("fr.html", "Francia", "FR"),
    ("punteggio.html", "Punteggi", None),
    ("operativo.html", "Operativo", None),
    ("previsione.html", "Previsione", None),
]


def nav_html(attivo: str = "", chiara: bool = True) -> str:
    """Barra di navigazione. `attivo` è il file della pagina corrente."""
    if chiara:
        base, acceso, spento = "#e2e8f0", "background:#0f172a;color:#fff;font-weight:800", \
                               "background:#fff;color:#334155;font-weight:600;border:1px solid #e2e8f0"
    else:
        base, acceso, spento = "#1e293b", "background:#fff;color:#0f172a;font-weight:800", \
                               "background:#1e293b;color:#cbd5e1;font-weight:600"
    pezzi = []
    for file, etichetta, _cod in VOCI:
        stile = acceso if file == attivo else spento
        pezzi.append(f'<a href="{file}" style="text-decoration:none;border-radius:9px;'
                     f'padding:8px 13px;font-size:13.5px;white-space:nowrap;{stile}">{etichetta}</a>')
    return (f'<div style="display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin:0 0 12px">'
            + "".join(pezzi) + "</div>")


def nav_per_mercato(cod: str) -> str:
    """Barra con i tre mercati in evidenza + le altre sezioni."""
    file_mercato = "index.html" if cod == "IT" else f"{cod.lower()}.html"
    return nav_html(attivo=file_mercato)
