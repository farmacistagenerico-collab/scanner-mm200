import unittest
from types import SimpleNamespace
import numpy as np
import pandas as pd
import momentum as mm
import momentum_risk as mr
import momentum_core as mc


def cfg(**kw):
    base = dict(n=2, n_minimo=1, liquidita=0.0, capitale=100.0, costo_lato=0.002,
                freq=1, buffer=0, vol_target=None, overlay="none", filtro_mm200=True,
                casuale=False)
    base.update(kw)
    return SimpleNamespace(**base)


def pannello(prezzi, turnover=1e7, sopra=True, exec_shift=1.0):
    idx = pd.date_range("2024-01-31", periods=len(prezzi), freq="ME")
    close = pd.Series(prezzi, index=idx, dtype=float)
    return pd.DataFrame({"close": close, "turnover": turnover, "sopra_mm200": sopra,
                         "exec_close": close * exec_shift, "exec_date": idx})


class SimulatoreTests(unittest.TestCase):
    def test_cambio_esposizione_paga_costi_anche_senza_cambio_titoli(self):
        # Un solo titolo, due mesi: il secondo mese riduce l'esposizione al 30%.
        # Rendimenti alternati: la volatilità realizzata è positiva, quindi il
        # target molto basso deve ridurre l'esposizione al minimo (30%).
        prezzi = [100.0]
        for i in range(29):
            prezzi.append(prezzi[-1] * (1.02 if i % 2 == 0 else 0.99))
        p = {"A": pannello(prezzi)}
        mesi = list(p["A"].index)
        eq, info = mr.simula_risk(p, mesi, cfg(n=1, vol_target=0.01), "test")
        # Dopo 6 rendimenti storici il volatility target molto basso limita
        # l'esposizione al 30%: la transizione deve pagare il 70% venduto.
        costi = [d["costo"] for d in info["dettagli"]]
        self.assertGreater(max(costi[6:]), 0.0)
        self.assertTrue(info["validabile"])

    def test_eleggibilita_non_dipende_dal_mese_successivo(self):
        # B ha dati solo fino al mese segnale: non deve essere escluso a priori,
        # ma senza prezzo di ingresso resta cash e viene marcato come gap.
        a = pannello([100 + i for i in range(18)])
        b = pannello([100 + i for i in range(18)])
        b.loc[b.index[-1], "exec_close"] = np.nan
        p = {"A": a, "B": b}
        mesi = list(a.index)
        eq, info = mr.simula_risk(p, mesi, cfg(n=2), "test")
        self.assertTrue(any("B" in g["titoli"] for g in info["gaps_dati"]))
        self.assertFalse(info["validabile"])

    def test_paniere_comparabile_stessi_costi(self):
        p = {"A": pannello([100 * (1.01 ** i) for i in range(18)]),
             "B": pannello([100 * (0.99 ** i) for i in range(18)])}
        mesi = list(p["A"].index)
        eq, info = mr.simula_paniere(p, mesi, cfg(), filtro_mm200=False)
        # Il simulatore parte dopo 13 mesi di formazione: 18 punti -> 5 punti equity.
        self.assertEqual(len(eq), len(mesi) - 13)
        self.assertTrue(info["validabile"])
        self.assertGreater(info["turnover"], 0)


class StatisticheTests(unittest.TestCase):
    def test_cagr_usa_rendimenti_non_punti(self):
        idx = pd.date_range("2020-01-31", periods=25, freq="ME")
        eq = pd.Series(100 * (1.01 ** np.arange(25)), index=idx)
        st = mm.statistiche(eq)
        atteso = ((eq.iloc[-1] / eq.iloc[0]) ** (12 / 24) - 1) * 100
        self.assertAlmostEqual(st["CAGR_%"], round(atteso, 2))

    def test_sotto_periodo_include_confine(self):
        idx = pd.date_range("2017-11-30", periods=4, freq="ME")
        eq = pd.Series([100, 110, 121, 133.1], index=idx)
        sub = mm.sotto_periodo(eq, 2018, 2018)
        self.assertEqual(sub.index[0], pd.Timestamp("2017-12-31"))
        self.assertAlmostEqual(sub.pct_change().dropna().iloc[0], 0.1)


if __name__ == "__main__":
    unittest.main()
