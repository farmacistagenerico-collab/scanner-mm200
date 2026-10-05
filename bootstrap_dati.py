#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BOOTSTRAP DATI — ricostruisce le cache necessarie alla dashboard
================================================================

Serve al primo avvio (o in CI, dove non esiste nessuna cache): scarica da Yahoo
Finance la storia lunga dell'universo (per il modello dei punteggi) e i dati
giornalieri recenti (per lo scanner e la dashboard), poi prepara
`output/portafoglio_attuale.csv` se manca.

Uso:
    python3 bootstrap_dati.py                  # scarica solo ciò che manca
    python3 bootstrap_dati.py --forza          # riscarica tutto (circa 3-5 minuti)
    python3 bootstrap_dati.py --solo-storico   # solo la cache lunga (modello punteggi)

Tempi indicativi: cache storica ~2-4 minuti (130 titoli, storia massima),
dati giornalieri ~10 secondi.
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings

import pandas as pd

warnings.filterwarnings("ignore")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import titoli_italiani as tu        # noqa: E402
import selezione_oggi as so         # noqa: E402

CACHE_DIR = os.path.join(BASE_DIR, "cache")
CACHE_STORICO = os.path.join(CACHE_DIR, "momentum_raw.pkl")
CACHE_LIVE = os.path.join(CACHE_DIR, "scanner_live.pkl")


@tu.osserva
def _percorsi_segui_mercato(cod=None):
    global CACHE_STORICO, CACHE_LIVE
    CACHE_STORICO = os.path.join(CACHE_DIR, tu.percorso("momentum_raw.pkl"))
    CACHE_LIVE = os.path.join(CACHE_DIR, tu.percorso("scanner_live.pkl"))
OUT_DIR = os.path.join(BASE_DIR, "output")


def cache_storico(forza: bool = False) -> bool:
    """Storia lunga dell'universo (per il modello dei punteggi): ~2-4 minuti."""
    if os.path.exists(CACHE_STORICO) and not forza:
        mb = os.path.getsize(CACHE_STORICO) / 1e6
        print(f"[storico] già presente ({mb:.0f} MB): salto")
        return True
    try:
        import yfinance as yf
    except ImportError:
        print("[storico] yfinance non installato: pip install -r requirements.txt")
        return False

    tickers = tu.solo_ticker()
    print(f"[storico] scarico la storia massima di {len(tickers)} titoli + benchmark "
          f"(qualche minuto)…")
    raw = yf.download(tickers + [tu.BENCHMARK], period="max", interval="1d",
                      auto_adjust=True, group_by="ticker", threads=True, progress=False)
    if raw is None or len(raw) == 0:
        print("[storico] download non riuscito")
        return False
    os.makedirs(CACHE_DIR, exist_ok=True)
    pd.to_pickle(raw, CACHE_STORICO)
    print(f"[storico] salvato: {os.path.getsize(CACHE_STORICO)/1e6:.0f} MB")
    return True


def cache_live(forza: bool = False) -> bool:
    """Dati giornalieri recenti (dashboard, scanner): ~10 secondi."""
    if os.path.exists(CACHE_LIVE) and not forza:
        print("[live] già presente: salto")
        return True
    try:
        so.scarica("2y")
        print("[live] salvato")
        return True
    except Exception as e:
        print(f"[live] errore: {type(e).__name__}: {e}")
        return False


def portafoglio_iniziale() -> bool:
    """Crea output/portafoglio_attuale.csv se non esiste (prima selezione)."""
    percorso = os.path.join(OUT_DIR, tu.percorso("portafoglio_attuale.csv"))
    if os.path.exists(percorso):
        print("[portafoglio] già presente: salto")
        return True
    try:
        import subprocess
        print("[portafoglio] creo la prima selezione…")
        esito = subprocess.run([sys.executable, "selezione_oggi.py", "--no-download",
                                "--mercato", tu.mercato],
                               cwd=BASE_DIR, capture_output=True, text=True, timeout=600)
        ok = os.path.exists(percorso)
        print(f"[portafoglio] {'creato' if ok else 'non creato'}")
        if not ok and esito.stdout:
            print(esito.stdout[-500:])
        return ok
    except Exception as e:
        print(f"[portafoglio] errore: {type(e).__name__}: {e}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepara le cache necessarie alla dashboard")
    ap.add_argument("--forza", action="store_true", help="riscarica tutto")
    ap.add_argument("--solo-storico", action="store_true", help="solo la cache storica")
    ap.add_argument("--mercato", default="IT", help="IT, DE, FR oppure TUTTI (default IT)")
    args = ap.parse_args()

    codici = tu.elenco_mercati() if args.mercato.upper() in ("TUTTI", "ALL", "*") else [args.mercato.upper()]
    esiti = []
    for cod in codici:
        m = tu.imposta_mercato(cod)
        print(f"\n=== {cod} · {m['paese']} ({m['nome']}) — {len(tu.solo_ticker())} titoli · benchmark {m['benchmark_nome']} ===")
        esiti.append((cod, cache_storico(args.forza),
                      True if args.solo_storico else cache_live(args.forza),
                      True if args.solo_storico else portafoglio_iniziale()))

    print("\nRiepilogo bootstrap:")
    for cod, ok_s, ok_l, ok_p in esiti:
        etichetta = f"{cod:2} {tu.MERCATI[cod]['nome']:14}"
        if args.solo_storico:
            print(f"  {etichetta} cache storica: {'ok' if ok_s else 'MANCANTE'}")
        else:
            print(f"  {etichetta} storica {'ok' if ok_s else 'MANCANTE'} · giornaliera {'ok' if ok_l else 'MANCANTE'} · portafoglio {'ok' if ok_p else 'MANCANTE'}")
    return 0 if all(all(e[1:]) for e in esiti) else 1

    ok_storico = cache_storico(args.forza)
    ok_live = True if args.solo_storico else cache_live(args.forza)
    ok_ptf = True if args.solo_storico else portafoglio_iniziale()

    print("\nRiepilogo bootstrap:")
    print(f"  cache storica (modello punteggi): {'ok' if ok_storico else 'MANCANTE'}")
    if not args.solo_storico:
        print(f"  cache giornaliera (dashboard):    {'ok' if ok_live else 'MANCANTE'}")
        print(f"  portafoglio attuale:              {'ok' if ok_ptf else 'MANCANTE'}")
    return 0 if (ok_storico and ok_live and ok_ptf) else 1


if __name__ == "__main__":
    sys.exit(main())
