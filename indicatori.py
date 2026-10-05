# -*- coding: utf-8 -*-
"""
Indicatori tecnici e logica di rilevazione dei segnali sulla media mobile
a 200 periodi (MM200). Nessuna dipendenza esterna oltre a pandas/numpy.

I pesi del punteggio non sono scelti a occhio: derivano dal modulo
`backtest.py`, che misura sui titoli di Piazza Affari (2005-oggi) quali
filtri rendono la rottura della MM200 statisticamente più affidabile.

Sintesi delle evidenze (volume_lab.py + controllo_robustezza.py, 2005-2026):
  - rottura "grezza" della MM200: rendimento a 12 mesi in linea con un
    periodo qualunque (nessun vantaggio statistico);
  - IL VOLUME NON È UN FILTRO: 13 misure testate, dose-risposta piatta,
    nessun effetto incrementale sulla struttura; anche attendere la conferma
    dei volumi 3 giorni dopo non migliora l'esito;
  - in giornaliero nemmeno la struttura (MM200 in salita + MM50>MM200)
    regge ai controlli con finestre non sovrapposte;
  - in SETTIMANALE l'unica combinazione che resiste (non sovrapposta +
    leave-one-out) è: volume settimanale ≥1,5x + MM40 settimanale in salita
    + MM10 sopra MM40 + conferma mensile → +34,6% (n=53) vs +13% baseline,
    p ≈ 0,006, ma ~2-3 segnali/anno e resa in calo nell'ultimo decennio.
  - filtri_lab.py/filtri_check.py (22 filtri testati): quasi tutti i "filtri"
    popolari (regime MIB, breadth, forza relativa, bassa volatilità) sono in
    realtà SOLO market timing: battono la rottura media ma non la baseline
    dello stesso stato di mercato.
  - L'unico filtro con evidenza SPECIFICA sulla rottura è il CONTESTO DI
    PREZZO: la rottura vale +4,2 punti in più di un periodo qualunque dello
    stesso stato quando il titolo è ancora in deep recovery (drawdown dal
    massimo a 12 mesi < -20%), con meno falsi breakout (61% vs 67%); le
    rotture vicine ai massimi hanno invece excess NEGATIVO (-2,9).
  Il punteggio è quindi un ranking di ATTENZIONE (vicinanza e contesto),
  non una probabilità di profitto.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# Indicatori di base
# ----------------------------------------------------------------------------

def sma(serie: pd.Series, periodo: int) -> pd.Series:
    """Media mobile semplice."""
    return serie.rolling(periodo, min_periods=periodo).mean()


def ema(serie: pd.Series, periodo: int) -> pd.Series:
    """Media mobile esponenziale."""
    return serie.ewm(span=periodo, adjust=False, min_periods=periodo).mean()


def rsi(serie: pd.Series, periodo: int = 14) -> pd.Series:
    """RSI di Wilder."""
    delta = serie.diff()
    su = delta.clip(lower=0).ewm(alpha=1 / periodo, adjust=False).mean()
    giu = (-delta.clip(upper=0)).ewm(alpha=1 / periodo, adjust=False).mean()
    rs = su / giu.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def atr(df: pd.DataFrame, periodo: int = 14) -> pd.Series:
    """Average True Range di Wilder (richiede colonne High/Low/Close)."""
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / periodo, adjust=False).mean()


def slope_pct(serie: pd.Series, finestra: int) -> pd.Series:
    """Pendenza percentuale del valore corrente rispetto a `finestra` periodi fa."""
    return (serie / serie.shift(finestra) - 1) * 100


def percentile_rolling(serie: pd.Series, finestra: int) -> pd.Series:
    """Percentile (0-100) del valore corrente dentro la finestra mobile."""
    return serie.rolling(finestra, min_periods=finestra).apply(
        lambda x: (x[-1] >= x).mean() * 100, raw=True
    )


def serie_settimanale(df: pd.DataFrame) -> pd.DataFrame:
    """Aggrega le barre giornaliere in barre settimanali (chiusura del venerdì)."""
    out = pd.DataFrame({
        "Open": df["Open"].resample("W-FRI").first(),
        "High": df["High"].resample("W-FRI").max(),
        "Low": df["Low"].resample("W-FRI").min(),
        "Close": df["Close"].resample("W-FRI").last(),
        "Volume": df["Volume"].resample("W-FRI").sum(),
    }).dropna()
    return out


# ----------------------------------------------------------------------------
# Stato del prezzo rispetto alla MM200
# ----------------------------------------------------------------------------

def stato_mm200(close, mm200, buffer_pct=1.0):
    """
    Stato del prezzo rispetto alla MM200 con buffer anti-rumore:

      'SOPRA'         -> chiusura > MM200 * (1 + buffer)      (rottura netta)
      'IN_TRANSIZIONE'-> dentro la fascia ±buffer (indecisione/whipsaw)
      'SOTTO'         -> chiusura < MM200 * (1 - buffer)      (rottura ribassista netta)
    """
    sopra = close > mm200 * (1 + buffer_pct / 100)
    sotto = close < mm200 * (1 - buffer_pct / 100)
    stato = pd.Series("IN_TRANSIZIONE", index=close.index, dtype=object)
    stato[sotto] = "SOTTO"
    stato[sopra] = "SOPRA"
    return stato


def trova_incroci(stato: pd.Series, tipo="SOPRA"):
    """Individua le date in cui lo stato cambia verso `tipo`. Ritorna [(pos, data)]."""
    cambi = []
    precedente = None
    for i, (data, val) in enumerate(stato.items()):
        if val == tipo and precedente is not None and precedente != tipo:
            cambi.append((i, data))
        if val != "IN_TRANSIZIONE":
            precedente = val
    return cambi


# ----------------------------------------------------------------------------
# Pacchetto di metriche per un singolo titolo
# ----------------------------------------------------------------------------

def calcola_metriche(df: pd.DataFrame, cfg: dict) -> dict | None:
    """
    Calcola tutte le metriche usate dai filtri e dal punteggio per un titolo.

    `df`  : DataFrame giornaliero con Open/High/Low/Close/Volume (auto-adjusted)
    `cfg` : dizionario di configurazione (vedi scanner.py)
    Ritorna None se la storia è troppo corta per costruire la MM200.
    """
    if df is None or len(df) < cfg["min_barre"]:
        return None
    df = df.dropna(subset=["Close"]).copy()
    if len(df) < cfg["min_barre"]:
        return None

    c = df["Close"]
    m200 = sma(c, cfg["periodo_mm"])
    m50 = sma(c, cfg["periodo_mm_breve"])
    m20 = sma(c, 20)

    vol_medio = df["Volume"].rolling(50, min_periods=20).mean()
    vol_ratio = df["Volume"] / vol_medio          # volume relativo alla media 50 sedute
    # se l'ultima barra ha volume mancante/zero (dato parziale), usa la media a 5 sedute
    if len(vol_ratio) and (pd.isna(vol_ratio.iloc[-1]) or vol_ratio.iloc[-1] <= 0.01):
        vol_ratio.iloc[-1] = vol_ratio.tail(5).mean()

    a = atr(df, 14)
    r = rsi(c, 14)

    stato = stato_mm200(c, m200, cfg["buffer_stato_pct"])
    distanza_pct = (c / m200 - 1) * 100           # distanza % dalla MM200
    distanza_atr = (c - m200) / a                 # distanza in unità di ATR (significatività)
    hh252 = c.rolling(252, min_periods=150).max()
    dd_252 = (c / hh252 - 1) * 100                # drawdown dal massimo a 12 mesi

    # --- contesto multi-timeframe (settimanale) -----------------------------
    # NB: l'ultima barra settimanale è la settimana in corso (parziale).
    sett = serie_settimanale(df)
    sett = sett[sett["Volume"] > 0]
    sma40_sett = sma(sett["Close"], 40) if len(sett) >= 40 else pd.Series(np.nan, index=sett.index)
    sma10_sett = sma(sett["Close"], 10) if len(sett) >= 10 else pd.Series(np.nan, index=sett.index)
    sopra_settimanale = bool(len(sett) and not np.isnan(sma40_sett.iloc[-1])
                             and sett["Close"].iloc[-1] > sma40_sett.iloc[-1])
    mm10w_sopra = bool(len(sett) and not np.isnan(sma10_sett.iloc[-1])
                       and not np.isnan(sma40_sett.iloc[-1])
                       and sma10_sett.iloc[-1] > sma40_sett.iloc[-1])
    volw_prev = sett["Volume"].rolling(10, min_periods=5).mean().shift(1)
    vol_weekly_ratio = (float(sett["Volume"].iloc[-1] / volw_prev.iloc[-1])
                        if len(sett) and np.isfinite(volw_prev.iloc[-1]) and volw_prev.iloc[-1] > 0
                        else np.nan)
    slope_weekly_mm40 = (float((sma40_sett.iloc[-1] / sma40_sett.iloc[-5] - 1) * 100)
                         if len(sett) >= 45 and np.isfinite(sma40_sett.iloc[-5]) else np.nan)

    # --- incroci storici ----------------------------------------------------
    incroci_su = trova_incroci(stato, "SOPRA")
    incroci_giu = trova_incroci(stato, "SOTTO")

    def giorni_da(incroci, stato_atteso):
        if not incroci:
            return None
        i, data = incroci[-1]
        if stato.iloc[-1] != stato_atteso:
            return None
        return len(df) - 1 - i

    ultimo = {
        "close": float(c.iloc[-1]),
        "mm200": float(m200.iloc[-1]) if not np.isnan(m200.iloc[-1]) else np.nan,
        "mm50": float(m50.iloc[-1]) if not np.isnan(m50.iloc[-1]) else np.nan,
        "mm20": float(m20.iloc[-1]) if not np.isnan(m20.iloc[-1]) else np.nan,
        "stato": str(stato.iloc[-1]),
        "distanza_pct": float(distanza_pct.iloc[-1]),
        "distanza_atr": float(distanza_atr.iloc[-1]),
        "dd_252": float(dd_252.iloc[-1]) if not np.isnan(dd_252.iloc[-1]) else np.nan,
        "vol_ratio": float(vol_ratio.iloc[-1]) if not np.isnan(vol_ratio.iloc[-1]) else np.nan,
        "vol_ratio_5g": float(vol_ratio.tail(5).mean()),
        "atr_pct": float(a.iloc[-1] / c.iloc[-1] * 100),
        "atr_percentile": float(percentile_rolling(a / c * 100, 250).iloc[-1])
                          if len(df) > 260 else np.nan,
        "rsi14": float(r.iloc[-1]),
        "slope_mm200_20g": float(slope_pct(m200, 20).iloc[-1]) if len(df) > 220 else np.nan,
        "slope_mm200_60g": float(slope_pct(m200, 60).iloc[-1]) if len(df) > 260 else np.nan,
        "ret_3m": float((c / c.shift(63) - 1).iloc[-1] * 100),
        "ret_6m": float((c / c.shift(126) - 1).iloc[-1] * 100),
        "ret_12m": float((c / c.shift(252) - 1).iloc[-1] * 100),
        "mm50_sopra_mm200": bool(m50.iloc[-1] > m200.iloc[-1])
                            if not (np.isnan(m50.iloc[-1]) or np.isnan(m200.iloc[-1])) else False,
        "sopra_weekly_mm40": sopra_settimanale,
        "mm10w_sopra_mm40": mm10w_sopra,
        "vol_weekly_ratio": vol_weekly_ratio,
        "slope_weekly_mm40": slope_weekly_mm40,
        "giorni_da_incrocio_su": giorni_da(incroci_su, "SOPRA"),
        "giorni_da_incrocio_giu": giorni_da(incroci_giu, "SOTTO"),
        "n_incroci_3a": sum(1 for _, d in incroci_su + incroci_giu
                            if d >= df.index[-1] - pd.Timedelta(days=1100)),
        "data": df.index[-1].strftime("%Y-%m-%d"),
    }

    segnali = classifica_segnali(c, m200, stato, distanza_pct, distanza_atr, vol_ratio, ultimo, cfg)
    ultimo.update(segnali)
    return ultimo


def classifica_segnali(c, m200, stato, distanza_pct, distanza_atr, vol_ratio, u, cfg):
    """
    Traduce le metriche in etichette operative e in un punteggio 0-100.

    I pesi replicano i filtri risultati statisticamente rilevanti nel
    backtest (volume, pendenza della MM200, allineamento delle medie,
    conferma del timeframe superiore): non sono una scelta arbitraria.
    """
    dist = float(distanza_pct.iloc[-1])
    v_ratio = float(vol_ratio.iloc[-1]) if not np.isnan(vol_ratio.iloc[-1]) else 0.0
    v_ratio_5 = float(vol_ratio.tail(5).mean())
    d_atr = float(distanza_atr.iloc[-1]) if not np.isnan(distanza_atr.iloc[-1]) else 0.0
    s20 = u["slope_mm200_20g"] if not np.isnan(u["slope_mm200_20g"]) else -99
    g_su = u["giorni_da_incrocio_su"]
    g_giu = u["giorni_da_incrocio_giu"]

    # ---------------- etichetta di stato -----------------------------------
    if u["stato"] == "SOPRA":
        if g_su is not None and g_su <= 5:
            etichetta = "ROTTURA CONFERMATA" if v_ratio >= cfg["volume_conferma"] else "ROTTURA DA CONFERMARE"
        else:
            etichetta = "TREND RIALZISTA (già sopra)"
    elif u["stato"] == "SOTTO":
        in_avvicinamento = (dist >= -cfg["distanza_prontezza_pct"]
                            and u["close"] > u["mm20"]      # rimbalzo già partito
                            and u["ret_3m"] > -3)           # non è caduta libera
        if g_giu is not None and g_giu <= 5:
            etichetta = "ROTTURA RIBASSISTA"
        elif in_avvicinamento:
            etichetta = "IN AVVICINAMENTO (sotto)"
        else:
            etichetta = "TREND RIBASSISTA (sotto)"
    else:
        if g_su is not None and g_su <= 10:
            etichetta = "FALSO BREAKOUT / RIENTRO"
        elif dist > 0:
            etichetta = "IN PROSSIMITÀ (sopra)"
        else:
            etichetta = "IN PROSSIMITÀ (sotto)"

    # ---------------- punteggio 0-100 --------------------------------------
    punteggio, dettagli = 0.0, []

    # 1) CONTESTO DI TREND (35 pt) — utile ma con effetto non robusto ai
    #    controlli: pesa, senza però "garantire" nulla.
    if s20 > 1:
        punteggio += 20; dettagli.append("MM200 in salita")
    elif s20 > -1:
        punteggio += 8; dettagli.append("MM200 piatta/stabilizzazione")
    if u["mm50_sopra_mm200"]:
        punteggio += 15; dettagli.append("MM50 sopra MM200")

    # 2) PROSSIMITÀ ALLA MM200 (25 pt)
    if -cfg["distanza_prontezza_pct"] <= dist <= cfg["buffer_stato_pct"]:
        punteggio += 25; dettagli.append("prezzo a ridosso della MM200")
    elif -2 * cfg["distanza_prontezza_pct"] <= dist:
        punteggio += 14; dettagli.append("distanza ridotta dalla MM200")
    elif u["stato"] == "SOPRA":
        punteggio += 6

    # 3) QUALITÀ DEL MOVIMENTO (12 pt)
    if 45 <= u["rsi14"] <= 75:
        punteggio += 6; dettagli.append("RSI in zona costruttiva")
    if u["ret_6m"] > 0:
        punteggio += 4; dettagli.append("rendimento 6 mesi positivo")
    if u["atr_percentile"] and not np.isnan(u["atr_percentile"]) and u["atr_percentile"] < 40:
        punteggio += 2; dettagli.append("volatilità compressa")

    # 4) VOLUMI (8 pt) — declassati: la ricerca NON ha trovato alcun potere
    #    predittivo nel volume. Restano solo come partecipazione.
    if v_ratio >= cfg["volume_conferma"]:
        punteggio += 5; dettagli.append(f"volume {v_ratio:.2f}x la media (partecipazione)")
    elif v_ratio_5 >= 1.0:
        punteggio += 3; dettagli.append("volumi in media/ripresa")

    # 5) CONTESTO DI PREZZO (20 pt) — l'unico filtro con evidenza SPECIFICA
    #    sulla rottura (filtri_lab/filtri_check): +4,2 punti di rendimento
    #    extra rispetto alla baseline dello stesso stato quando il titolo è in
    #    deep recovery; excess negativo quando è vicino ai massimi.
    dd = u["dd_252"] if np.isfinite(u["dd_252"]) else np.nan
    if np.isfinite(dd):
        if dd < -20:
            punteggio += 20
            dettagli.append(f"rottura da deep recovery (dd {dd:.0f}%, filtro con evidenza)")
        elif dd <= -10:
            punteggio += 10
            dettagli.append(f"contesto di recovery intermedio (dd {dd:.0f}%)")
        elif dd > -15:
            punteggio -= 5
            dettagli.append(f"rottura vicino ai massimi (dd {dd:.0f}%, contesto debole)")

    # penalità: titoli che attraversano la media in continuazione = whipsaw
    if u["n_incroci_3a"] >= 6:
        punteggio -= 15; dettagli.append("molti incroci negli ultimi 3 anni (whipsaw)")

    punteggio = float(max(0, min(100, punteggio)))

    # ---------------- setup settimanale (l'unico che regge i controlli) -----
    # Combo verificata in controllo_robustezza.py (finestre non sovrapposte e
    # leave-one-out): volume settimanale ≥1,5x + MM40W in salita + MM10W sopra
    # MM40W, con conferma mensile. Resa +34,6% vs +13% baseline (n=53,
    # p≈0,006) ma ~2-3 segnali/anno e resa dimezzata nell'ultimo decennio.
    _slope_w = u["slope_weekly_mm40"] if np.isfinite(u["slope_weekly_mm40"]) else -99
    _vol_w = u["vol_weekly_ratio"] if np.isfinite(u["vol_weekly_ratio"]) else 0.0
    settimanale_ok = bool(u["sopra_weekly_mm40"] and u["mm10w_sopra_mm40"] and _slope_w > 0)
    setup_settimanale = bool(settimanale_ok and _vol_w >= cfg["volume_conferma"])
    if setup_settimanale:
        punteggio = min(100.0, punteggio + 10)
        dettagli.append("segnale settimanale confermato (+10)")

    # ---------------- flag esplicativi -------------------------------------
    flag = []
    if setup_settimanale:
        flag.append("★ segnale settimanale supportato dalla ricerca")
    elif settimanale_ok:
        flag.append("struttura settimanale allineata (manca il volume)")
    if u["stato"] == "SOPRA" and v_ratio >= cfg["volume_conferma"] and g_su is not None and g_su <= 10:
        flag.append("rottura supportata da volumi")
    if u["stato"] == "SOPRA" and u["sopra_weekly_mm40"]:
        flag.append("conferma settimanale")
    if u["stato"] == "SOPRA" and s20 < -1:
        flag.append("MM200 ancora in discesa (attenzione)")
    if u["stato"] == "SOPRA" and not u["mm50_sopra_mm200"]:
        flag.append("MM50 sotto MM200 (struttura debole)")
    if u["stato"] == "IN_TRANSIZIONE":
        flag.append("zona di indecisione ±%.1f%%" % cfg["buffer_stato_pct"])
    if np.isfinite(u["dd_252"]):
        if u["dd_252"] < -20:
            flag.append("★ deep recovery: il filtro con evidenza specifica")
        elif u["dd_252"] > -15:
            flag.append("vicino ai massimi a 12 mesi (contesto debole nella ricerca)")
    if u["n_incroci_3a"] >= 6:
        flag.append("storia di whipsaw")

    # ---------------- selezione -------------------------------------------
    RIALZISTE = ("ROTTURA CONFERMATA", "ROTTURA DA CONFERMARE", "IN PROSSIMITÀ (sotto)",
                 "IN PROSSIMITÀ (sopra)", "IN AVVICINAMENTO (sotto)")
    vicino = dist <= cfg["buffer_stato_pct"] and dist >= -cfg["distanza_prontezza_pct"]
    rottura_fresca = g_su is not None and g_su <= 5
    critico = bool(
        punteggio >= cfg["soglia_punteggio"]
        and (vicino or rottura_fresca)
        and etichetta in RIALZISTE
        and float(c.iloc[-1]) > 0.2
    )

    return {
        "etichetta": etichetta,
        "punteggio": punteggio,
        "dettagli_punteggio": "; ".join(dettagli),
        "flag_significativita": "; ".join(flag),
        "setup_settimanale": setup_settimanale,
        "settimanale_ok": settimanale_ok,
        "candidato": critico,
    }
