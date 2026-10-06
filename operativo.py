# -*- coding: utf-8 -*-
"""
Genera output/operativo.html — la visuale operativa del sito:
cosa fare, cosa aspettare per entrare, cosa non fare mai.

Le date (prossime verifiche di fine mese, primo giorno utile per gli ordini) sono
calcolate; i numeri di rendimento vengono dai riepiloghi del backtest, con valori
di riserva se i file non ci sono (per esempio in un ambiente senza dati).

Uso:
    python3 operativo.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import titoli_italiani as tu      # noqa: E402
import sito                        # noqa: E402

OUT_DIR = os.path.join(BASE_DIR, "output")

# valori di riserva (backtest 2010-2026), usati se i riepiloghi non sono leggibili
RISERVA = {
    "IT": {"cagr": 18.73, "sharpe": 0.96, "dd": -33.7, "universo": 11.7, "casuali": 6.3},
    "DE": {"cagr": 16.63, "sharpe": 0.91, "dd": -33.8, "universo": 13.4, "casuali": 6.2},
    "FR": {"cagr": 10.76, "sharpe": 0.74, "dd": -24.7, "universo": 11.1, "casuali": 4.3},
}
NOMI_VARIANTE = {
    "IT": "② + buffer di rank 5",
    "DE": "② + buffer di rank 5",
    "FR": "① Base MOM 12-1 top10 + MM200 (mensile)",
}


def numeri(cod: str) -> dict:
    """Rendimento della regola, dell'universo e dei titoli a caso, dal backtest."""
    d = dict(RISERVA[cod])
    nome = "momentum_risk_riepilogo.json" if cod == "IT" else f"momentum_risk_riepilogo_{cod}.json"
    try:
        with open(os.path.join(OUT_DIR, nome), encoding="utf-8") as f:
            dati = json.load(f)
        for v in dati.get("varianti", []):
            if v["variante"] == NOMI_VARIANTE[cod]:
                d["cagr"] = round(v["CAGR_%"], 1)
                d["sharpe"] = round(v["Sharpe"], 2)
                d["dd"] = round(v["max_drawdown_%"], 1)
            elif "Universo" in v["variante"]:
                d["universo"] = round(v["CAGR_%"], 1)
            elif "casuali" in v["variante"]:
                d["casuali"] = round(v["CAGR_%"], 1)
    except Exception:
        pass
    return d


def date_operative(oggi: pd.Timestamp | None = None) -> dict:
    """Prossime verifiche (ultima seduta del mese) e primo giorno utile per gli ordini."""
    oggi = pd.Timestamp.now().normalize() if oggi is None else oggi
    verifiche = [d for d in pd.date_range(oggi, periods=13, freq="BME")][:6]
    prima = verifiche[0]
    ordini = prima + pd.offsets.BDay(1)
    return {
        "verifiche": [f"{d.day:02d}/{d.month:02d}/{d.year}" for d in verifiche],
        "prima": f"{prima.day:02d}/{prima.month:02d}/{prima.year}",
        "ordini": f"{ordini.day:02d}/{ordini.month:02d}/{ordini.year}",
    }


def _n(x, dec=1):
    return f"{x:,.{dec}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def costruisci() -> str:
    d = date_operative()
    it, de, fr = numeri("IT"), numeri("DE"), numeri("FR")
    adesso = datetime.now().strftime("%d/%m/%Y")

    def riga_tentazione(testo, esito):
        return (f'<tr><td style="border:0;padding:6px 0">{testo}</td>'
                f'<td style="border:0;padding:6px 0;color:#b91c1c;font-weight:700">{esito}</td></tr>')

    html = f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Operativo — cosa fare, cosa aspettare</title>
<style>
  body {{ margin:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a }}
  .cont {{ max-width:860px;margin:0 auto;padding:16px 12px 40px }}
  .box {{ background:#fff;border-radius:14px;padding:18px 20px;box-shadow:0 1px 3px rgba(15,23,42,.08);margin-top:14px }}
  h2 {{ font-size:13px;letter-spacing:1.1px;text-transform:uppercase;color:#64748b;margin:0 0 12px;font-weight:800 }}
  .passo {{ display:flex;gap:12px;align-items:flex-start;padding:9px 0;border-top:1px solid #eef2f7 }}
  .num {{ flex:0 0 26px;height:26px;border-radius:50%;background:#0f172a;color:#fff;font-size:13.5px;
          font-weight:800;display:flex;align-items:center;justify-content:center;margin-top:1px }}
  table {{ width:100%;border-collapse:collapse;font-size:13.5px }}
  th {{ text-align:left;font-size:11.5px;text-transform:uppercase;letter-spacing:.6px;color:#64748b;padding:6px 8px }}
  td {{ padding:8px;border-top:1px solid #eef2f7;vertical-align:top }}
  .pill {{ display:inline-block;border-radius:999px;padding:4px 11px;font-size:12.5px;font-weight:700;margin:2px 4px 2px 0 }}
</style></head>
<body><div class="cont">
  {sito.nav_html('operativo.html')}

  <div style="background:#0f172a;color:#fff;border-radius:16px;padding:22px">
    <div style="font-size:12px;letter-spacing:1.2px;text-transform:uppercase;color:#94a3b8">
      Visuale operativa · aggiornata al {adesso}</div>
    <div style="font-size:24px;font-weight:900;margin:9px 0 8px;line-height:1.25">
      Cosa fare, cosa aspettare, cosa non fare mai</div>
    <div style="color:#cbd5e1;font-size:13.5px;line-height:1.6">
      Il metodo è semplice e ha un solo momento in cui si fa qualcosa: l'ultima seduta del mese.
      Tutto il resto è astensione: è lì che si guadagna.</div>
  </div>

  <div class="box">
    <h2>La regola in una riga</h2>
    <div style="font-size:19px;line-height:1.55;font-weight:700">
      Una volta al mese tieni i titoli che restano fra i <b>migliori 15</b> per momentum 12-1 <b>e</b>
      sopra la <b>MM200</b>; sostituisci gli altri con i migliori che mancano; quote uguali; niente altro.</div>
    <div style="font-size:13.5px;color:#475569;line-height:1.65;margin-top:10px">
      Il cuscinetto dei 5 posti (15 invece di 10) serve a non fare trading inutile: si cambia un titolo
      solo quando esce davvero. Costo in operazioni: <b>14,5% al mese</b> con il cuscinetto, 24,3% senza.
      Misurato 2010-2026: <b>+{_n(it['cagr'])}% annuo in Italia</b> e <b>+{_n(de['cagr'])}% in Germania</b>
      (Sharpe {_n(it['sharpe'], 2)} e {_n(de['sharpe'], 2)}).</div>
  </div>

  <div class="box">
    <h2>Cosa fare a fine mese · 10 minuti</h2>
    <div class="passo"><div class="num">1</div><div>Apri la pagina del mercato e leggi il <b>verdetto</b> in alto.</div></div>
    <div class="passo"><div class="num">2</div><div>Se dice <b>"Oggi non devi fare nulla"</b> → hai finito. È il caso più frequente.</div></div>
    <div class="passo"><div class="num">3</div><div>Se segnala titoli <b>fuori regola</b> (sotto la MM200 oppure oltre il <b>15º posto</b> nel ranking), questi escono.</div></div>
    <div class="passo"><div class="num">4</div><div>Al loro posto entrano i <b>primi titoli liberi</b> del ranking che sono sopra la MM200. Se non cambia nessuno, non si tocca nulla.</div></div>
    <div class="passo"><div class="num">5</div><div><b>Ordini la prima seduta del mese nuovo</b>, a mercato, con quote uguali (capitale ÷ 10).</div></div>
    <div class="passo"><div class="num">6</div><div>Poi silenzio fino al mese successivo: non si guarda, non si decide, non si anticipa.</div></div>
  </div>

  <div class="box" style="border-left:5px solid #0a7d3c">
    <h2>Cosa aspettare per entrare · la risposta è una data</h2>
    <div style="font-size:15px;line-height:1.7">
      <b>Si aspetta una data, non un prezzo.</b> Non c'è nessun "buon momento" da riconoscere guardando i grafici.</div>
    <table style="margin-top:10px">
      <tr><td style="border:0;padding-left:0;color:#b91c1c;font-weight:700">✗ aspettare il ritracciamento</td>
          <td style="border:0">non è mai stato misurato come vantaggio</td></tr>
      <tr><td style="border:0;padding-left:0;color:#b91c1c;font-weight:700">✗ aspettare la rottura della MM200</td>
          <td style="border:0">testato: <b>nessun edge</b> (11,59% contro 12,81% della base)</td></tr>
      <tr><td style="border:0;padding-left:0;color:#b91c1c;font-weight:700">✗ entrare a metà mese "perché sale"</td>
          <td style="border:0">si compra fuori regola, senza cuscinetto</td></tr>
      <tr><td style="border:0;padding-left:0;color:#0a7d3c;font-weight:700">✓ entrare alla prossima verifica</td>
          <td style="border:0">decidi il <b>{d['prima']}</b>, ordini il <b>{d['ordini']}</b></td></tr>
    </table>
    <div style="font-size:13.5px;color:#475569;line-height:1.65;margin-top:10px">
      <b>Quanto:</b> la somma divisa in 10 parti uguali (20.000 € → 2.000 € per titolo). Sotto i
      10-15.000 € totali meglio 3-5 titoli che dieci quote minuscole: le commissioni mangerebbero il vantaggio.
      <b>Mai leva, mai margine.</b></div>
  </div>

  <div class="box">
    <h2>Cosa non fare mai · tutto già testato</h2>
    <table>
      <thead><tr><th>Tentazione</th><th>Risultato nei dati</th></tr></thead>
      <tbody>
        {riga_tentazione("Stop loss, uscite &quot;di protezione&quot;", "ogni overlay peggiora: 2,65% · 3,95% · 14,19% annuo contro 18,73%")}
        {riga_tentazione("Inseguire le rotture della MM200", "nessun vantaggio: 11,59% vs 12,81%")}
        {riga_tentazione("Vendere perché è salito tanto, o a target", "si esce per regola, mai a target")}
        {riga_tentazione("Aggiungere un titolo che ti piace", f"i titoli a caso rendono {_n(it['casuali'])}% (Italia) e {_n(de['casuali'])}% (Germania)")}
        {riga_tentazione("Cambiare regola dopo un mese brutto", "la storia contiene anni a −17% e −21%: sono parte del contratto")}
        {riga_tentazione("Guardare i prezzi ogni giorno", "il metodo vive su orizzonti mensili")}
        {riga_tentazione("Operare in Francia", f"selezione {_n(fr['cagr'])}% contro {_n(fr['universo'])}% dell'insieme: nessun edge")}
      </tbody>
    </table>
  </div>

  <div class="box">
    <h2>Aspettative · cosa è normale che accada</h2>
    <div style="display:flex;gap:14px;flex-wrap:wrap">
      <div style="flex:1 1 300px">
        <div style="font-size:12.5px;color:#64748b;font-weight:700;margin-bottom:6px">VENTAGLIO A 12 MESI</div>
        <div style="font-size:13.5px;line-height:1.7">
          <b>Italia</b> mediana +18,2% · 90% dei casi −9,5% … +49,3% · 69% positivi<br>
          <b>Germania</b> mediana +18,6% · 90% dei casi −7,5% … +55,6% · 84% positivi
        </div>
        <div style="font-size:13px;color:#475569;line-height:1.6;margin-top:8px">
          Un anno su tre è finito <b>in perdita</b> anche partendo da un regime favorevole. La fascia è
          larga ~59 punti: serve a non spaventarsi, non a fissare un obiettivo.
          <a href="previsione.html" style="color:#0a7d3c;font-weight:700">Vedi i ventagli →</a></div>
      </div>
      <div style="flex:1 1 240px">
        <div style="font-size:12.5px;color:#64748b;font-weight:700;margin-bottom:6px">IL NUMERO CHE DEVI REGGERE</div>
        <div style="font-size:15px;line-height:1.65">
          Drawdown storico <b>{_n(it['dd'])}%</b> (Italia) e <b>{_n(de['dd'])}%</b> (Germania).<br>
          Su 100.000 € investiti: <b>vedere 66.000 €</b> in un periodo brutto senza che nulla sia rotto.</div>
        <div style="font-size:13px;color:#475569;line-height:1.6;margin-top:8px">
          Se non lo reggi, riduci il capitale investito. <b>Non</b> cambiare la regola.</div>
      </div>
    </div>
  </div>

  <div class="box">
    <h2>I tre mercati · dove si opera</h2>
    <div>
      <span class="pill" style="background:#dcfce7;color:#166534">🇮🇹 Italia · operativo · +{_n(it['cagr'])}% annuo</span>
      <span class="pill" style="background:#dcfce7;color:#166534">🇩🇪 Germania · operativo · +{_n(de['cagr'])}% annuo</span>
      <span class="pill" style="background:#fef3c7;color:#92400e">🇫🇷 Francia · solo monitor · nessun edge</span>
    </div>
    <div style="font-size:13.5px;color:#475569;line-height:1.65;margin-top:10px">
      Due portafogli separati, capitali separati, stesso calendario. La ripartizione fra Italia e Germania
      è una tua scelta, non un risultato ottimizzato: decidi una volta e non la cambi più. Attenzione ai
      <b>doppioni</b>: una società quotata su due listini si conta una volta sola.</div>
  </div>

  <div class="box">
    <h2>Gli strumenti della pagina · come usarli</h2>
    <table>
      <thead><tr><th>Strumento</th><th>Cosa dice</th><th>Come si usa</th></tr></thead>
      <tbody>
        <tr><td><b>Verdetto del giorno</b></td><td>cosa fare oggi (quasi sempre: nulla)</td><td>è l'unico input operativo</td></tr>
        <tr><td><b>Punteggio 0-100</b></td><td>frequenza storica di esito positivo (alto 71,1% · basso 60,6%)</td><td>verde ≥72 attese alte · rosso &lt;62 = posizione fragile. <b>Non</b> è un filtro e <b>non</b> dice quanto comprare</td></tr>
        <tr><td><b>Affidabilità</b></td><td>quanti casi storici sostengono il numero</td><td>se è bassa, ignora il punteggio e segui solo la regola</td></tr>
        <tr><td><b>Ventaglio</b></td><td>dove sono finite le situazioni simili del passato</td><td>calibrare l'attesa, mai come target di prezzo</td></tr>
      </tbody>
    </table>
  </div>

  <div class="box" style="background:#0f172a;color:#fff">
    <h2 style="color:#94a3b8">Il calendario</h2>
    <div style="font-size:14.5px;line-height:1.9">
      <b>Ogni ultima seduta del mese</b> — verifica (10 minuti)<br>
      <b>Prossime date:</b> {' · '.join(d['verifiche'])}<br>
      <b>Tutti gli altri giorni</b> — non si fa nulla</div>
    <div style="margin-top:14px;padding-top:14px;border-top:1px solid #1e293b;font-size:13.5px;color:#cbd5e1;line-height:1.6">
      <b>Domanda di controllo</b>, quando sei tentato di fare qualcosa fuori calendario:<br>
      <i>«Questa azione è prevista dalla regola o è una mia idea?»</i> — Se è una tua idea, non si fa.</div>
  </div>

  <div style="font-size:12px;color:#94a3b8;line-height:1.7;margin-top:14px;text-align:center">
    Punteggi e ventagli sono frequenze storiche, non previsioni. Dati dal feed gratuito Yahoo Finance
    (ritardo tipico 15 minuti). Non è consulenza finanziaria.</div>
</div></body></html>"""
    return html


def genera() -> str:
    """Scrive output/operativo.html. Richiamabile da dashboard.py senza argparse."""
    html = costruisci()
    os.makedirs(OUT_DIR, exist_ok=True)
    percorso = os.path.join(OUT_DIR, "operativo.html")
    with open(percorso, "w", encoding="utf-8") as f:
        f.write(html)
    return percorso


def main() -> int:
    print(f"Pagina operativa: {genera()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
