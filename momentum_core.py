"""Regole condivise fra selezione operativa e verifica del momentum.

Un solo posto per definizione del segnale, filtri e costo di ribilanciamento.
Non contiene ottimizzazioni né promesse di rendimento.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Iterable

import numpy as np
import pandas as pd

N_TITOLI = 10
BUFFER_RANK = 5
LIQUIDITA_EUR = 2_000_000.0
COSTO_LATO = 0.002
CALENDARI = {"IT": "XMIL", "DE": "XETR", "FR": "XPAR"}

VARIANTE_RIFERIMENTO = "② + buffer di rank 5"
BENCH_PANIERE = "◇ Paniere liquido equipesato (stessi costi/date)"
BENCH_PANIERE_TREND = "◇ Paniere liquido + MM200 (stessi costi/date)"
BENCH_UNIVERSO_STORICO = "◇ Universo storico equipesato (buy & hold, non comparabile)"


def bench_indice(mercato: str) -> str:
    nome = {"IT": "FTSE MIB", "DE": "DAX", "FR": "CAC 40"}[mercato.upper()]
    return f"◇ {nome} (indice, non comparabile)"


@lru_cache(maxsize=3)
def calendario_mercato(mercato: str):
    import exchange_calendars as xcals
    return xcals.get_calendar(CALENDARI[mercato.upper()])


def ultima_sessione_utile(ora: pd.Timestamp, mercato: str = "IT") -> pd.Timestamp:
    """Data massima utilizzabile da un feed giornaliero, con conferma dopo le 18.

    Prima delle 18 non consideriamo definitiva la barra odierna. Nei giorni non
    di borsa si usa l'ultima sessione precedente. È una scelta prudente per non
    scambiare una barra intraday per la chiusura del mese.
    """
    ora = pd.Timestamp(ora)
    if ora.tzinfo is not None:
        ora = ora.tz_convert("Europe/Rome").tz_localize(None)
    cal = calendario_mercato(mercato)
    giorno = ora.normalize()
    if cal.is_session(giorno):
        if ora.hour < 18:
            giorno = cal.previous_session(giorno)
    else:
        giorno = cal.date_to_session(giorno, direction="previous")
    return giorno.normalize()


def ultima_chiusura_mese(sessioni: Iterable[pd.Timestamp], mercato: str = "IT") -> pd.Timestamp:
    """Ultimo giorno di borsa effettivamente concluso nel mese di `sessioni`."""
    sessioni = pd.DatetimeIndex(sessioni).sort_values()
    if sessioni.empty:
        raise ValueError("Nessuna sessione disponibile")
    if sessioni.tz is not None:
        sessioni = sessioni.tz_localize(None)
    ultima = sessioni[-1].normalize()
    cal = calendario_mercato(mercato)
    inizio = ultima.replace(day=1)
    fine = ultima + pd.offsets.MonthEnd(0)
    return cal.sessions_in_range(inizio, fine)[-1].normalize()


def mesi_conclusi(close: pd.Series, data_massima: pd.Timestamp,
                  mercato: str = "IT") -> pd.Series:
    """Chiuse mensili, escludendo il mese corrente se non è finita la borsa.

    La presenza di una barra il venerdì non basta: il calendario ufficiale dice
    se quella è davvero l'ultima sessione del mese.
    """
    c = close.dropna().sort_index().copy()
    if c.empty:
        return pd.Series(dtype=float)
    if c.index.tz is not None:
        c.index = c.index.tz_localize(None)
    limite = pd.Timestamp(data_massima).normalize()
    c = c[c.index.normalize() <= limite]
    if c.empty:
        return pd.Series(dtype=float)
    m = c.resample("ME").last()
    chiusura_attesa = ultima_chiusura_mese(c.index, mercato)
    if c.index[-1].normalize() < chiusura_attesa:
        m = m.iloc[:-1]
    return m


def finestra_momentum(mesi: pd.Series) -> tuple[float, pd.Timestamp, pd.Timestamp] | None:
    """12-1: rendimento di 12 mesi che termina il mese prima del mese t."""
    if len(mesi) < 14:
        return None
    fine, inizio = mesi.index[-2], mesi.index[-13 - 1]
    if not np.isfinite(mesi.iloc[-2]) or not np.isfinite(mesi.iloc[-14]) or mesi.iloc[-14] <= 0:
        return None
    return float(mesi.iloc[-2] / mesi.iloc[-14] - 1), inizio, fine


def liquidita_storica(turnover_mensile: pd.Series, pos: int) -> float:
    """Mediana delle tre mediane mensili t-3, t-2, t-1 (mai il mese t)."""
    if pos < 3:
        return float("nan")
    return float(turnover_mensile.iloc[pos - 3:pos].median())


def pesi_target(scelti: Iterable[str], n: int = N_TITOLI,
                esposizione: float = 1.0) -> dict[str, float]:
    """Peso fisso per slot: i posti non riempiti restano liquidità, non leva."""
    if n <= 0 or not 0 <= esposizione <= 1:
        raise ValueError("n deve essere positivo ed esposizione fra 0 e 1")
    scelti = list(dict.fromkeys(scelti))[:n]
    return {t: float(esposizione / n) for t in scelti}


def seleziona_buffer(eligibili: pd.DataFrame, precedente: Iterable[str],
                     n: int = N_TITOLI, buffer: int = BUFFER_RANK,
                     filtro_mm200: bool = True, casuale: bool = False,
                     rng=None) -> list[str]:
    """Selezione senza allentare i filtri per riempire il portafoglio.

    `eligibili` deve già rispettare il filtro di liquidità. Il buffer riguarda
    solo il ranking, non il trend. I titoli sotto MM200 non vengono mantenuti.
    Il controllo casuale usa lo stesso universo trend e lo stesso buffer.
    """
    if n <= 0 or buffer < 0:
        raise ValueError("n deve essere positivo e buffer non negativo")
    e = eligibili
    if filtro_mm200:
        if "sopra_mm200" not in e.columns:
            raise ValueError("Manca lo stato MM200")
        e = e[e["sopra_mm200"].astype(bool)]
    if e.empty:
        return []
    if casuale:
        if rng is None:
            raise ValueError("Il controllo casuale richiede un generatore")
        ordine = list(e.index)
        rng.shuffle(ordine)
    else:
        colonna = "mom_%" if "mom_%" in e.columns else "mom"
        ordine = list(e.sort_values(colonna, ascending=False, kind="stable").index)
    precedenti = set(precedente)
    tenuti = [t for t in ordine[:n + buffer] if t in precedenti]
    nuovi = [t for t in ordine if t not in tenuti]
    return (tenuti + nuovi)[:n]


def variazione_pesi(prima: dict[str, float], dopo: dict[str, float]) -> float:
    """Nozionale scambiato su titoli / patrimonio: somma delle |variazioni|."""
    titoli = set(prima) | set(dopo)
    return float(sum(abs(dopo.get(t, 0.0) - prima.get(t, 0.0)) for t in titoli))


def turnover_pesi(prima: dict[str, float], dopo: dict[str, float]) -> float:
    """Turnover convenzionale a un lato fra portafogli titoli (metà del nozionale)."""
    return variazione_pesi(prima, dopo) / 2


def turnover_operativo(prima: dict[str, float], dopo: dict[str, float]) -> float:
    """Lato prevalente dell'operazione: max(acquisti, vendite) sul patrimonio.

    Ingresso da liquidità al 100% -> 100%; sostituzione di 1/10 -> 10%;
    riduzione dell'esposizione dal 100% al 30% -> 70%.
    """
    titoli = set(prima) | set(dopo)
    acquisti = sum(max(dopo.get(t, 0.0) - prima.get(t, 0.0), 0.0) for t in titoli)
    vendite = sum(max(prima.get(t, 0.0) - dopo.get(t, 0.0), 0.0) for t in titoli)
    return float(max(acquisti, vendite))


def costo_transizione(prima: dict[str, float], dopo: dict[str, float],
                      costo_lato: float) -> float:
    """Costo sul nozionale effettivamente comprato/venduto; la liquidità è gratis.

    Esempi: ingresso 100% -> costo_lato; sostituzione di un decimo -> 2*costo_lato/10;
    riduzione esposizione da 100% a 30% -> 0.7*costo_lato.
    """
    if costo_lato < 0:
        raise ValueError("costo_lato non può essere negativo")
    return variazione_pesi(prima, dopo) * costo_lato


def pesi_dopo_rendimenti(pesi: dict[str, float], rendimenti: dict[str, float]) -> dict[str, float]:
    """Lascia correre i pesi con i prezzi; la liquidità non si muove."""
    valori = {t: w * (1 + rendimenti[t]) for t, w in pesi.items()}
    totale = sum(valori.values()) + (1 - sum(pesi.values()))
    if totale <= 0:
        raise ValueError("Patrimonio nullo: impossibile normalizzare i pesi")
    return {t: v / totale for t, v in valori.items() if v != 0}
