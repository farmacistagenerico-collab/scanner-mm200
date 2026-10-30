import unittest
import numpy as np
import pandas as pd
import momentum_core as mc


class CalendarTests(unittest.TestCase):
    def test_ultima_sessione_30_ottobre_2026(self):
        cal = mc.calendario_mercato("IT")
        self.assertTrue(cal.is_session(pd.Timestamp("2026-10-30")))
        self.assertEqual(cal.next_session(pd.Timestamp("2026-10-30")), pd.Timestamp("2026-11-02"))
        self.assertEqual(mc.ultima_sessione_utile(pd.Timestamp("2026-10-30 17:59"), "IT"),
                         pd.Timestamp("2026-10-29"))
        self.assertEqual(mc.ultima_sessione_utile(pd.Timestamp("2026-10-30 18:00"), "IT"),
                         pd.Timestamp("2026-10-30"))
        self.assertEqual(mc.ultima_sessione_utile(pd.Timestamp("2026-11-01 12:00"), "IT"),
                         pd.Timestamp("2026-10-30"))

    def test_mese_concluso_richiede_ultima_sessione(self):
        idx = pd.to_datetime(["2026-09-30", "2026-10-29", "2026-10-30"])
        s = pd.Series([100.0, 110.0, 111.0], index=idx)
        self.assertEqual(list(mc.mesi_conclusi(s, pd.Timestamp("2026-10-29"), "IT").index),
                         [pd.Timestamp("2026-09-30")])
        self.assertEqual(list(mc.mesi_conclusi(s, pd.Timestamp("2026-10-30"), "IT").index),
                         [pd.Timestamp("2026-09-30"), pd.Timestamp("2026-10-31")])


class SignalTests(unittest.TestCase):
    def test_finestra_12_1(self):
        idx = pd.date_range("2025-01-31", periods=15, freq="ME")
        prezzi = pd.Series(np.linspace(100, 115, len(idx)), index=idx)
        mom, inizio, fine = mc.finestra_momentum(prezzi)
        self.assertEqual(inizio, idx[-14])
        self.assertEqual(fine, idx[-2])
        self.assertAlmostEqual(mom, prezzi.iloc[-2] / prezzi.iloc[-14] - 1)
        self.assertIsNone(mc.finestra_momentum(prezi := prezzi.iloc[:13]))

    def test_nessun_fallback_sotto_mm200_o_illiquido(self):
        elig = pd.DataFrame({"mom": [0.3, 0.2], "sopra_mm200": [False, False]}, index=["A", "B"])
        self.assertEqual(mc.seleziona_buffer(elig, [], 1, 0), [])
        elig = pd.DataFrame({"mom": [0.3, 0.2], "sopra_mm200": [True, True]}, index=["A", "B"])
        self.assertEqual(mc.seleziona_buffer(elig.iloc[:1], [], 2, 0), ["A"])
        self.assertEqual(mc.pesi_target(["A"], 2), {"A": 0.5})

    def test_buffer_non_mantiene_titoli_fuori_trend(self):
        elig = pd.DataFrame({"mom": [0.5, 0.4, 0.3], "sopra_mm200": [True, False, True]},
                            index=["A", "B", "C"])
        self.assertEqual(mc.seleziona_buffer(elig, ["B"], 1, 5), ["A"])


class AccountingTests(unittest.TestCase):
    def test_costi_su_variazione_esposizione(self):
        prima = {"A": 0.6, "B": 0.4}
        dopo = {"A": 0.18, "B": 0.12}
        self.assertAlmostEqual(mc.variazione_pesi(prima, dopo), 0.7)
        self.assertAlmostEqual(mc.turnover_operativo(prima, dopo), 0.7)
        self.assertAlmostEqual(mc.costo_transizione(prima, dopo, 0.002), 0.0014)

    def test_sostituzione_un_decimo(self):
        prima = {f"T{i}": 0.1 for i in range(10)}
        dopo = dict(prima)
        del dopo["T0"]
        dopo["NEW"] = 0.1
        self.assertAlmostEqual(mc.turnover_operativo(prima, dopo), 0.1)
        self.assertAlmostEqual(mc.costo_transizione(prima, dopo, 0.002), 0.0004)

    def test_pesi_derivano_con_prezzi_e_cash(self):
        pesi = {"A": 0.5}
        dopo = mc.pesi_dopo_rendimenti(pesi, {"A": 0.2})
        self.assertAlmostEqual(dopo["A"], 0.6 / 1.1)
        self.assertAlmostEqual(1 - sum(dopo.values()), 0.5 / 1.1)


if __name__ == "__main__":
    unittest.main()
