import unittest
import numpy as np
import pandas as pd
import selezione_oggi as so
import momentum as mm
import momentum_core as mc
import titoli_italiani as tu


def daily_frame(n=420):
    idx = pd.bdate_range("2025-01-01", periods=n)
    close = pd.Series(100 * (1.0005 ** np.arange(n)), index=idx)
    vol = pd.Series(1_000_000, index=idx)
    return pd.DataFrame({"Close": close, "Volume": vol})


class LiveBacktestParityTests(unittest.TestCase):
    def test_metriche_live_allineate_al_pannello(self):
        tu.imposta_mercato("IT")
        df = daily_frame()
        oggi = mc.ultima_sessione_utile(pd.Timestamp("2026-10-30 18:00"), "IT")
        live = so.metriche_titolo(df, oggi, "IT")
        panel = mm.pannello_mensile(df, "IT")
        pos = len(panel) - 1
        mom, _, _ = mc.finestra_momentum(panel["close"])
        self.assertIsNotNone(live)
        self.assertAlmostEqual(live["mom_%"], mom * 100, places=8)
        self.assertAlmostEqual(live["turnover_mediano"], mc.liquidita_storica(panel["turnover"], pos), places=4)
        self.assertEqual(bool(live["sopra_mm200"]), bool(panel["sopra_mm200"].iloc[-1]))

    def test_selezione_non_allenta_filtri(self):
        tab = pd.DataFrame({"mom_%": [30.0, 20.0], "sopra_mm200": [False, False],
                            "turnover_mediano": [1e7, 1e7]}, index=["A.MI", "B.MI"])
        scelti, sel = so.seleziona(tab, [], 2, 5, 2e6)
        self.assertEqual(scelti, [])
        self.assertTrue(sel.empty)
        self.assertIn("liquidità", sel.attrs["nota"])


if __name__ == "__main__":
    unittest.main()
