import unittest
from dataclasses import replace
import numpy as np
import pandas as pd
from roaring_returns.policies import (buy_only, min_sales_band, minimum_sale_bound,
                                     exact_target_cash_required, project_box_simplex)
from roaring_returns.engine import BacktestConfig, backtest, execute_dollar_plan, summarize
from roaring_returns.data import parse_chart


def prices(dates, rows):
    return pd.DataFrame(rows, index=pd.DatetimeIndex(dates, name="date"), columns=["QQQ", "GLD", "IEF"])


class MechanismTests(unittest.TestCase):
    def test_exact_cash_threshold_and_insufficient_cash_allocation(self):
        h, a = [450, 250, 300], [.4, .3, .3]
        self.assertAlmostEqual(exact_target_cash_required(h, a), 125)
        np.testing.assert_allclose(buy_only(h, 100, a), [450, 325, 325], atol=1e-9)
        np.testing.assert_allclose(buy_only(h, 125, a), [450, 337.5, 337.5], atol=1e-9)

    def test_lower_band_floor_can_force_sale_without_upper_violation(self):
        h, a = [.7, .3, 0], [.6, .2, .2]
        result = min_sales_band(h, 0, a, .15)
        self.assertAlmostEqual(np.maximum(np.array(h)-result, 0).sum(), .05)
        self.assertGreaterEqual(result[2], .05-1e-12)

    def test_random_minimum_sales_against_independent_linear_program(self):
        try:
            from scipy.optimize import linprog
        except ImportError:
            self.skipTest("Install .[validation] for the independent LP check.")
        rng = np.random.default_rng(20261022)
        for _ in range(150):
            h = rng.dirichlet(np.ones(3))
            a = rng.dirichlet(np.ones(3))
            cash, band = rng.random()*.5, rng.random()*.15
            total = h.sum()+cash
            lo, hi = np.maximum(a-band, 0), np.minimum(a+band, 1)
            result = min_sales_band(h, cash, a, band)
            matrix = np.c_[np.eye(3), -np.eye(3)]
            lp = linprog([0]*3+[1]*3, A_ub=np.r_[matrix, -matrix],
                         b_ub=np.r_[hi*total-h, h-lo*total],
                         A_eq=[[1]*3+[-1]*3], b_eq=[cash],
                         bounds=[(0, None)]*3+[(0, float(v)) for v in h], method="highs")
            self.assertTrue(lp.success)
            self.assertAlmostEqual(np.maximum(h-result, 0).sum(), lp.fun, places=9)
            self.assertAlmostEqual(result.sum(), total, places=10)
            self.assertTrue(np.all(result >= lo*total-1e-10))
            self.assertTrue(np.all(result <= hi*total+1e-10))

    def test_no_cash_inside_band_does_not_create_trade(self):
        h, a = [360, 320, 320], [1/3]*3
        np.testing.assert_allclose(min_sales_band(h, 0, a, .05), h, atol=1e-9)

    def test_tie_break_and_buy_only_against_independent_quadratic_programs(self):
        try:
            from scipy.optimize import minimize, Bounds, LinearConstraint
        except ImportError:
            self.skipTest("Install .[validation] for independent QP validation.")
        rng = np.random.default_rng(77)
        for _ in range(35):
            h, a = rng.dirichlet(np.ones(3)), rng.dirichlet(np.ones(3))
            cash, band = .01+rng.random()*.4, .01+rng.random()*.1
            total = 1+cash
            lo, hi = np.maximum(a-band, 0)*total, np.minimum(a+band, 1)*total
            bound = minimum_sale_bound(h, cash, lo/total, hi/total)
            # sum(max(h-x,0)) <= bound is equivalent to all subset inequalities.
            subsets = np.array([[float(mask & (1 << i) != 0) for i in range(3)] for mask in range(1, 8)])
            constraints = [LinearConstraint(np.ones((1, 3)), total, total),
                           LinearConstraint(subsets, subsets@h-bound, np.inf)]
            candidate = min_sales_band(h, cash, a, band)
            qp = minimize(lambda x: np.sum((x-a*total)**2), candidate,
                          jac=lambda x: 2*(x-a*total), bounds=Bounds(lo, hi),
                          constraints=constraints, method="SLSQP", options={"ftol": 1e-12, "maxiter": 200})
            self.assertTrue(qp.success, qp.message)
            self.assertAlmostEqual(np.sum((candidate-a*total)**2), qp.fun, places=9)
            only = buy_only(h, cash, a)
            qp_only = minimize(lambda x: np.sum((x-a*total)**2), h+cash/3,
                               jac=lambda x: 2*(x-a*total), bounds=Bounds(h, np.full(3, total)),
                               constraints=[constraints[0]], method="SLSQP",
                               options={"ftol": 1e-12, "maxiter": 200})
            self.assertTrue(qp_only.success, qp_only.message)
            # SLSQP's objective tolerance bounds squared error, not component error.
            self.assertAlmostEqual(np.sum((only-a*total)**2), qp_only.fun, places=9)
            np.testing.assert_allclose(only, qp_only.x, atol=2e-6)

    def test_exact_target_limit_of_band_formula(self):
        h, a = np.array([450, 250, 300]), np.array([.4, .3, .3])
        self.assertAlmostEqual(minimum_sale_bound(h, 100, a, a), 10)
        np.testing.assert_allclose(min_sales_band(h, 100, a, 0), a*1100, atol=1e-9)

    def test_infeasible_projection_rejected(self):
        with self.assertRaises(ValueError):
            project_box_simplex([.5, .5], [.7, .7], [1, 1])


class AccountingTests(unittest.TestCase):
    def test_flat_market_deposits_are_not_returns_or_drawdown(self):
        p = prices(["2020-01-31", "2020-02-03", "2020-02-28", "2020-03-02"], [[100]*3]*4)
        for strategy in ["proportional", "annual", "threshold_center", "cashflow_only", "min_sales_band"]:
            result = backtest(p, BacktestConfig(strategy, initial_wealth=1000, monthly_contribution=100))
            self.assertAlmostEqual(result.daily.wealth.iloc[-1], 1200)
            np.testing.assert_allclose(result.daily.nav, 1, atol=1e-12)
            self.assertEqual(summarize(result)["max_drawdown"], 0)

    def test_end_of_day_flow_excluded_with_correct_intraday_order(self):
        p = prices(["2020-01-31", "2020-02-03"], [[100]*3, [110]*3])
        result = backtest(p, BacktestConfig("proportional", initial_wealth=1000, monthly_contribution=100))
        self.assertAlmostEqual(result.daily.wealth.iloc[-1], 1200)
        self.assertAlmostEqual(result.daily.nav.iloc[-1], 1.1)
        self.assertAlmostEqual(result.daily.portfolio_return.iloc[-1], .1)

    def test_initial_and_recurring_costs_reduce_actual_wealth(self):
        p = prices(["2020-01-31", "2020-02-03"], [[100]*3]*2)
        result = backtest(p, BacktestConfig("proportional", initial_wealth=1000, monthly_contribution=100, cost_bps=10))
        expected = 1100/1.001
        self.assertAlmostEqual(result.daily.wealth.iloc[-1], expected)
        self.assertAlmostEqual(result.daily.fees.sum(), 1100-expected)
        self.assertLess(result.daily.nav.iloc[-1], 1)

    def test_sales_capped_and_costly_buys_scaled_without_borrowing(self):
        h, cash, buys, sales, fee = execute_dollar_plan([1., 0, 0], 1., [-2., 3., 0], .01)
        self.assertEqual(sales, 1)
        self.assertGreaterEqual(cash, 0)
        self.assertAlmostEqual(h.sum()+cash, 2-fee)
        self.assertAlmostEqual(buys, 1.99/1.01)

    def test_future_execution_prices_cannot_change_frozen_plan(self):
        dates = ["2020-01-30", "2020-01-31", "2020-02-03"]
        base = prices(dates, [[100]*3, [150, 100, 100], [150, 100, 100]])
        changed = base.copy(); changed.iloc[-1] = [20, 500, 10]
        cfg = BacktestConfig("min_sales_band", initial_wealth=1000, monthly_contribution=100)
        e1, e2 = backtest(base, cfg).events, backtest(changed, cfg).events
        np.testing.assert_allclose(e1.planned_sales, e2.planned_sales, atol=1e-9)
        np.testing.assert_allclose(e1.planned_min_sales, e2.planned_min_sales, atol=1e-9)
        np.testing.assert_allclose(e1.external_flow, e2.external_flow, atol=1e-9)

    def test_multi_month_future_poisoning_preserves_each_asset_order(self):
        dates = pd.bdate_range("2020-01-31", "2020-12-31")
        rng = np.random.default_rng(901)
        p = pd.DataFrame(100*np.exp(np.cumsum(rng.normal(0, .02, (len(dates), 3)), axis=0)),
                         index=dates, columns=["QQQ", "GLD", "IEF"])
        cutoff = pd.Timestamp("2020-06-30")
        changed = p.copy()
        future = changed.index > cutoff
        changed.loc[future] = rng.uniform(20, 300, (future.sum(), 3))
        columns = ["planned_trade_QQQ", "planned_trade_GLD", "planned_trade_IEF", "external_flow"]
        for strategy in ["proportional", "annual", "threshold_center", "cashflow_only", "min_sales_band"]:
            cfg = BacktestConfig(strategy)
            baseline, poisoned = backtest(p, cfg), backtest(changed, cfg)
            pd.testing.assert_frame_equal(baseline.daily.loc[:cutoff], poisoned.daily.loc[:cutoff])
            left = baseline.events.loc[baseline.events.signal_date <= cutoff, columns]
            right = poisoned.events.loc[poisoned.events.signal_date <= cutoff, columns]
            pd.testing.assert_frame_equal(left, right)

    def test_no_flow_buy_hold_matches_asset_total_return_identity(self):
        p = prices(["2020-01-31", "2020-02-03", "2020-03-02"],
                   [[100, 100, 100], [130, 80, 105], [90, 125, 108]])
        result = backtest(p, BacktestConfig("proportional", initial_wealth=1000, monthly_contribution=0))
        expected = (90+125+108)/300
        self.assertAlmostEqual(result.daily.nav.iloc[-1], expected)

    def test_unit_issuance_with_return_then_flow_then_fee(self):
        p = prices(["2020-01-31", "2020-02-03"], [[100]*3, [110]*3])
        result = backtest(p, BacktestConfig("proportional", initial_wealth=1000, monthly_contribution=100, cost_bps=10))
        initial = 1000/1.001
        before = initial*1.1
        after = before+100/1.001
        expected_nav = initial/1000*1.1*after/(before+100)
        self.assertAlmostEqual(result.daily.nav.iloc[-1], expected_nav)
        self.assertAlmostEqual(result.events.contribution_ratio_signal.iloc[0], 100/initial)
        self.assertAlmostEqual(result.events.contribution_ratio_execution.iloc[0], 100/before)

    def test_buy_only_remains_buy_only_after_price_changes_and_fees(self):
        dates = pd.bdate_range("2020-01-31", "2021-03-01")
        rng = np.random.default_rng(9)
        p = pd.DataFrame(np.exp(np.cumsum(rng.normal(0, .03, (len(dates), 3)), axis=0))*100,
                         index=dates, columns=["QQQ", "GLD", "IEF"])
        result = backtest(p, BacktestConfig("cashflow_only", cost_bps=10))
        np.testing.assert_allclose(result.daily.sales, 0, atol=1e-8)
        self.assertTrue((result.daily.cash >= 0).all())

    def test_scale_invariance_with_proportional_costs(self):
        dates = pd.bdate_range("2020-01-31", "2021-02-01")
        rng = np.random.default_rng(3)
        p = pd.DataFrame(np.exp(np.cumsum(rng.normal(0, .02, (len(dates), 3)), axis=0))*100,
                         index=dates, columns=["QQQ", "GLD", "IEF"])
        for strategy in ["cashflow_only", "min_sales_band", "threshold_center"]:
            cfg = BacktestConfig(strategy, initial_wealth=1000, monthly_contribution=100, cost_bps=10)
            small = backtest(p, cfg)
            large = backtest(p, replace(cfg, initial_wealth=100000, monthly_contribution=10000))
            np.testing.assert_allclose(small.daily.nav, large.daily.nav, atol=1e-10)
            np.testing.assert_allclose(small.daily.wealth*100, large.daily.wealth, rtol=1e-10)

    def test_total_return_proxy_income_counted_once(self):
        p = prices(["2020-01-30", "2020-01-31"], [[100]*3, [102]*3])
        result = backtest(p, BacktestConfig("proportional", initial_wealth=1000, monthly_contribution=0))
        self.assertAlmostEqual(result.daily.wealth.iloc[-1], 1020)
        self.assertAlmostEqual(result.daily.nav.iloc[-1], 1.02)
        self.assertEqual(result.daily.external_flow.sum(), 0)

    def test_missing_prices_and_duplicate_sessions_fail(self):
        p = prices(["2020-01-30", "2020-01-31"], [[100]*3, [np.nan, 100, 100]])
        with self.assertRaises(ValueError): backtest(p, BacktestConfig("proportional"))
        p.iloc[1] = 100; p.index = [p.index[0], p.index[0]]
        with self.assertRaises(ValueError): backtest(p, BacktestConfig("proportional"))

    def test_proportional_funding_scale_control(self):
        p = prices(["2020-01-31", "2020-02-03"], [[100]*3, [110]*3])
        result = backtest(p, BacktestConfig("cashflow_only", initial_wealth=1000, contribution_rate=.1))
        # Defined from SIGNAL wealth, not unknowable execution-day wealth.
        self.assertAlmostEqual(result.events.external_flow.iloc[0], 100)
        self.assertAlmostEqual(result.daily.nav.iloc[-1], 1.1)


class DataTests(unittest.TestCase):
    def test_unmatched_corporate_action_is_not_silently_dropped(self):
        session = int(pd.Timestamp("2020-01-31 21:00", tz="UTC").timestamp())
        bad_event = int(pd.Timestamp("2020-02-03 14:30", tz="UTC").timestamp())
        payload = {"chart": {"result": [{"meta": {"currency": "USD", "symbol": "QQQ"},
                   "timestamp": [session], "indicators": {"quote": [{"open": [100], "close": [100]}],
                   "adjclose": [{"adjclose": [100]}]},
                   "events": {"dividends": {str(bad_event): {"date": bad_event, "amount": 1.0}}}}],
                   "error": None}}
        with self.assertRaisesRegex(ValueError, "no matching price session"):
            parse_chart(payload, "QQQ")


if __name__ == "__main__":
    unittest.main()
