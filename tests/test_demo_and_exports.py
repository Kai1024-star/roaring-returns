import importlib.util
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from roaring_returns.research_runner import paired_intervals


class InferenceTests(unittest.TestCase):
    def test_paired_blocks_preserve_zero_difference_and_reject_wrong_dates(self):
        e = pd.DataFrame({"execution_date": pd.date_range("2020-01-01", periods=12, freq="MS"),
            "posttrade_rms_deviation_pp": np.arange(12)/10,
            "posttrade_outside_band": [True, False]*6,
            "actual_sales_fraction_signal": np.arange(12)/1000})
        for row in paired_intervals(e, e.copy(), repetitions=100):
            self.assertEqual((row["difference"], row["lower"], row["upper"]), (0., 0., 0.))
        bad = e.copy()
        bad["execution_date"] += pd.Timedelta(days=1)
        with self.assertRaises(ValueError):
            paired_intervals(e, bad)


@unittest.skipUnless(importlib.util.find_spec("streamlit") and importlib.util.find_spec("cvxpy"),
                     "Install the demo extra for UI integration tests")
class DemoTests(unittest.TestCase):
    def test_shock_changes_outcome_without_replanning_and_invalid_weights_stop(self):
        from streamlit.testing.v1 import AppTest
        root = Path(__file__).resolve().parents[1]
        app = AppTest.from_file(str(root/"demo_app.py"), default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.tabs), 4)
        def order_id():
            return next(c.value for c in app.caption if c.value.startswith("Frozen order ID"))
        before = order_id()
        outcome = app.metric[1].value
        next(s for s in app.slider if s.label == "QQQ next-session shock (%)").set_value(-8.).run()
        self.assertFalse(app.exception)
        self.assertEqual(order_id(), before)
        self.assertNotEqual(app.metric[1].value, outcome)
        next(s for s in app.slider if s.label == "QQQ (%)").set_value(90)
        next(s for s in app.slider if s.label == "GLD (%)").set_value(50)
        next(b for b in app.button if b.label == "Build frozen trade plans").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("at most 100%" in e.value for e in app.error))


if __name__ == "__main__":
    unittest.main()
