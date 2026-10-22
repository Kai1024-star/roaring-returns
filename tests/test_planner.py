import importlib.util
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from dataclasses import replace
from pathlib import Path
import numpy as np
import pandas as pd
from roaring_returns.planner import Budget, PlanningSettings, EXAMPLES, sampled_paths, simulate_mix, describe_result, monthly_returns, replay_daily


class PlannerTests(unittest.TestCase):
    def test_reserves_and_near_term_money_not_double_invested(self):
        budget = Budget(savings=300, emergency_reserve=500, near_term=250, monthly=200, months=4)
        self.assertEqual(budget.initial, 0)
        self.assertEqual(budget.protected_now, 300)
        self.assertEqual(budget.reserve_gap, 450)
        np.testing.assert_array_equal(budget.contributions(), [0, 0, 150, 200])
        np.testing.assert_array_equal(replace(budget, monthly=0).contributions(), np.zeros(4))

    def test_zero_market_zero_fees_contributions_are_not_return(self):
        budget = Budget(months=12)
        cfg = PlanningSettings(paths=3, cash_rate=0, cost_bps=0)
        for weights in EXAMPLES.values():
            result = simulate_mix(np.zeros((3, 12, 3)), budget, weights, cfg)
            np.testing.assert_allclose(result.wealth, np.broadcast_to(result.contributed, result.wealth.shape), atol=1e-6)
            np.testing.assert_allclose(result.maximum_dip, 0, atol=1e-6)
            np.testing.assert_allclose(result.sales, 0, atol=1e-6)

    def test_cash_compounding_matches_end_of_month_annuity(self):
        budget = Budget(savings=2000, emergency_reserve=0, near_term=0, monthly=100, months=12)
        cfg = PlanningSettings(cash_rate=.036, cost_bps=25)
        result = simulate_mix(np.zeros((2, 12, 3)), budget, EXAMPLES['Savings reference'], cfg)
        growth = 1.036**(1/12)
        expected = 2000*growth**12+100*(growth**12-1)/(growth-1)
        np.testing.assert_allclose(result.wealth[:, -1], expected, atol=1e-7)
        np.testing.assert_allclose(result.fees, 0)

    def test_deposits_cannot_hide_a_market_dip(self):
        budget = Budget(savings=100, emergency_reserve=0, near_term=0, monthly=100, months=2)
        r = np.array([[[-.5, 0, 0], [0, 0, 0]]])
        result = simulate_mix(r, budget, (0, 1, 0, 0), PlanningSettings(cash_rate=0, cost_bps=0))
        self.assertAlmostEqual(result.wealth[0, -1], 250, places=6)
        self.assertAlmostEqual(result.maximum_dip[0], 50, places=6)

    def test_cash_first_correction_does_not_sell_when_contribution_restores_mix(self):
        budget = Budget(savings=1000, emergency_reserve=0, near_term=0, monthly=500, months=1)
        result = simulate_mix(np.array([[[.2, 0, 0]]]), budget, (.2, .4, .15, .25),
                              PlanningSettings(cash_rate=0, cost_bps=0))
        self.assertAlmostEqual(result.sales[0], 0)
        self.assertEqual(result.selling_months[0], 0)

    def test_flat_market_total_fees_explain_every_missing_dollar(self):
        budget = Budget(months=24)
        for weights in EXAMPLES.values():
            result = simulate_mix(np.zeros((8, 24, 3)), budget, weights,
                                  PlanningSettings(cash_rate=0, cost_bps=25))
            np.testing.assert_allclose(result.wealth[:, -1]+result.fees, result.contributed[-1], atol=1e-5)
            self.assertTrue((result.wealth >= 0).all())

    def test_resampling_preserves_joint_vectors_and_is_reproducible(self):
        r = np.random.default_rng(2).normal(0, .02, (60, 3))
        cfg = PlanningSettings(paths=40, return_haircut=0)
        draws, index = sampled_paths(r, 24, cfg)
        np.testing.assert_allclose(draws, r[index], atol=1e-15)
        np.testing.assert_array_equal(draws, sampled_paths(r, 24, cfg)[0])
        np.testing.assert_array_equal(draws, sampled_paths(r, 60, cfg)[0][:, :24])
        lowered, same = sampled_paths(r, 24, replace(cfg, return_haircut=.02))
        np.testing.assert_array_equal(index, same)
        self.assertTrue((lowered < draws).all())

    def test_rule_cannot_use_future_months(self):
        rng = np.random.default_rng(9)
        r = rng.normal(0, .06, (10, 18, 3)); other = r.copy(); other[:, 9:] *= 3
        budget = Budget(months=18)
        cfg = PlanningSettings()
        first = simulate_mix(r, budget, EXAMPLES['Mixed example'], cfg)
        second = simulate_mix(other, budget, EXAMPLES['Mixed example'], cfg)
        np.testing.assert_array_equal(first.wealth[:, :10], second.wealth[:, :10])
        np.testing.assert_array_equal(first.sample_holdings[:10], second.sample_holdings[:10])

    def test_cash_anchor_is_shared_by_all_assets_and_proxy_excess(self):
        proxy = np.linspace(-.002, .004, 60)
        history = np.repeat(proxy[:, None], 4, axis=1)
        cfg = PlanningSettings(paths=20, cash_rate=.03)
        draws, index = sampled_paths(history, 24, cfg)
        np.testing.assert_allclose(draws, 1.03**(1/12)-1, atol=1e-15)
        changed, same = sampled_paths(history, 24, replace(cfg, cash_rate=.07))
        np.testing.assert_array_equal(index, same)
        np.testing.assert_allclose(np.log1p(changed)-np.log1p(draws), (np.log1p(.07)-np.log1p(.03))/12)
        history[:, 0] = np.expm1(np.log1p(proxy)+.01)
        premium, _ = sampled_paths(history, 24, cfg)
        np.testing.assert_allclose(np.log1p(premium[:, :, 0])-np.log1p(premium[:, :, 1]), .01)

    def test_sample_matched_cash_anchor_preserves_population_log_means(self):
        proxy = np.linspace(-.002, .004, 60)
        premiums = np.array([.006, .004, .001])
        risky = np.expm1(np.log1p(proxy)[:, None]+premiums)
        history = np.column_stack([risky, proxy])
        matched = float(np.expm1(12*np.log1p(proxy).mean()))
        draws, _ = sampled_paths(history, 24, PlanningSettings(paths=20, cash_rate=matched))
        np.testing.assert_allclose(np.log1p(draws).mean((0, 1)), np.log1p(risky).mean(0), atol=1e-14)

    @staticmethod
    def _daily_prices():
        days = pd.bdate_range('2019-12-31', '2020-02-28', name='date')
        return pd.DataFrame(100., index=days, columns=['SPY', 'GLD', 'IEF'])

    def test_daily_replay_exposes_recovered_intramonth_dip(self):
        prices = self._daily_prices()
        prices.loc['2020-01-15', 'SPY'] = 50.
        budget = Budget(savings=1000, emergency_reserve=0, near_term=0, monthly=100, months=2)
        cfg = PlanningSettings(cash_rate=0, cost_bps=0)
        daily = replay_daily(prices, budget, (0, 1, 0, 0), cfg, '2020-01-01', '2020-02-28')
        monthly = simulate_mix(monthly_returns(prices).to_numpy()[None], budget, (0, 1, 0, 0), cfg)
        self.assertAlmostEqual(daily.maximum_dip[0], 500)
        self.assertAlmostEqual(monthly.maximum_dip[0], 0)
        self.assertAlmostEqual(daily.wealth[0, -1], monthly.wealth[0, -1])
        self.assertEqual(daily.period_unit, 'Session')
        flows = np.diff(daily.contributed)
        flow_dates = np.array(daily.dates[1:])[flows > 0]
        np.testing.assert_array_equal(flow_dates, ['2020-01-31', '2020-02-28'])
        with self.assertRaises(ValueError):
            describe_result(daily, budget, cfg)

    def test_daily_replay_budget_fees_and_no_early_contribution(self):
        prices = self._daily_prices()
        budget = Budget(savings=1200, emergency_reserve=0, near_term=0, monthly=100, months=2)
        cfg = PlanningSettings(cash_rate=0, cost_bps=25)
        for weights in EXAMPLES.values():
            result = replay_daily(prices, budget, weights, cfg, '2020-01-01', '2020-02-28')
            self.assertAlmostEqual(result.wealth[0, -1]+result.fees[0], result.contributed[-1], places=6)
            partial = replay_daily(prices, budget, weights, cfg, '2020-01-01', '2020-01-20')
            self.assertEqual(partial.contributed[-1], budget.initial)
            np.testing.assert_allclose(partial.sample_holdings, np.broadcast_to(partial.sample_holdings[0], partial.sample_holdings.shape))

    def test_daily_replay_future_pollution_leaves_past_states_unchanged(self):
        prices = self._daily_prices()
        other = prices.copy()
        other.loc['2020-02-01':, 'SPY'] *= np.linspace(.4, 1.8, len(other.loc['2020-02-01':]))
        budget, cfg = Budget(months=2), PlanningSettings()
        a = replay_daily(prices, budget, EXAMPLES['Mixed example'], cfg, '2020-01-01', '2020-02-28')
        b = replay_daily(other, budget, EXAMPLES['Mixed example'], cfg, '2020-01-01', '2020-02-28')
        cut = np.searchsorted(a.dates, '2020-02-01')
        np.testing.assert_array_equal(a.wealth[:, :cut], b.wealth[:, :cut])
        np.testing.assert_array_equal(a.sample_holdings[:cut], b.sample_holdings[:cut])

    def test_daily_replay_uses_observed_cash_proxy_not_future_assumption(self):
        prices = self._daily_prices()
        prices['BIL'] = 100*np.linspace(1, 1.01, len(prices))
        budget = Budget(savings=1000, emergency_reserve=0, near_term=0, monthly=0, months=2)
        cfg = PlanningSettings(cash_rate=.15, cost_bps=0)
        result = replay_daily(prices, budget, EXAMPLES['Savings reference'], cfg, '2020-01-01', '2020-02-28')
        self.assertAlmostEqual(result.wealth[0, -1], 1010, places=8)
        other = replay_daily(prices, budget, EXAMPLES['Savings reference'], replace(cfg, cash_rate=0), '2020-01-01', '2020-02-28')
        np.testing.assert_array_equal(result.wealth, other.wealth)

    def test_daily_month_end_wealth_reconciles_with_monthly_engine(self):
        prices = self._daily_prices()
        rng = np.random.default_rng(93)
        prices.iloc[1:] = 100*np.cumprod(1+rng.normal(0, .02, (len(prices)-1, 3)), axis=0)
        budget, cfg = Budget(months=2), PlanningSettings(cash_rate=0, cost_bps=25)
        for weights in EXAMPLES.values():
            daily = replay_daily(prices, budget, weights, cfg, '2020-01-01', '2020-02-28')
            monthly = simulate_mix(monthly_returns(prices).to_numpy()[None], budget, weights, cfg)
            ends = [daily.dates.index(day) for day in ['2019-12-31', '2020-01-31', '2020-02-28']]
            np.testing.assert_allclose(daily.wealth[:, ends], monthly.wealth, atol=1e-7)
            np.testing.assert_allclose(daily.fees, monthly.fees, atol=1e-7)

    def test_zero_budget_goal_opt_out_and_inflation_units(self):
        b = Budget(savings=0, emergency_reserve=0, near_term=0, monthly=0, months=12, goal_today=0)
        cfg = PlanningSettings()
        result = simulate_mix(np.zeros((4, 12, 3)), b, EXAMPLES['Mixed example'], cfg)
        self.assertTrue((result.wealth == 0).all())
        self.assertNotIn('goal_frequency', describe_result(result, b, cfg))
        b = replace(b, savings=1000)
        result = simulate_mix(np.zeros((4, 12, 3)), b, EXAMPLES['Savings reference'], cfg)
        self.assertAlmostEqual(describe_result(result, b, cfg)['ending_middle_today'], 1000*1.03/1.025)

    def test_invalid_inputs_and_missing_month_fail(self):
        with self.assertRaises(ValueError):
            Budget(savings=-1).validate()
        with self.assertRaises(ValueError):
            PlanningSettings(cost_bps=-1).validate()
        prices = pd.DataFrame(100., index=pd.to_datetime(['2020-01-31', '2020-03-31']), columns=['SPY', 'GLD', 'IEF'])
        with self.assertRaises(ValueError):
            monthly_returns(prices)


@unittest.skipUnless(importlib.util.find_spec('streamlit') and importlib.util.find_spec('cvxpy'), 'Install demo extra')
class PlannerUITests(unittest.TestCase):
    def test_clean_checkout_is_explicitly_synthetic_and_usable(self):
        from streamlit.testing.v1 import AppTest
        from roaring_returns import home
        with TemporaryDirectory() as folder, patch.object(home, 'ROOT', Path(folder)):
            home._market.clear()
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'demo_app.py'), default_timeout=40)
            app.session_state['workspace']='Budget planner'
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(any('SYNTHETIC DEMO' in message.value for message in app.info))
            self.assertTrue(any('designed monthly shocks' in message.value.lower() for message in app.caption))
        home._market.clear()

    def test_optimizer_controls_scenario_modes_and_unfunded_state(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'demo_app.py'), default_timeout=40)
        app.session_state['workspace']='Budget planner'
        app.run()
        next(r for r in app.radio if r.label == 'Examples and candidates (choose one)').set_value('Risk-balanced candidate')
        next(s for s in app.slider if s.label == 'Cash share of model candidate (%)').set_value(40)
        next(s for s in app.selectbox if s.label == 'Covariance lookback (sessions)').set_value(252)
        next(s for s in app.selectbox if s.label == 'Excess-return assumption').set_value('Zero average excess returns')
        app.run()
        self.assertFalse(app.exception)
        r = app.session_state.planner_bundle[2]['Risk-balanced candidate']
        self.assertAlmostEqual(r.sample_holdings[0,0]/r.sample_holdings[0].sum(), .4)
        self.assertEqual(app.session_state.planner_assumption, 'Zero average excess returns')
        next(n for n in app.number_input if n.label == 'Savings available now ($)').set_value(0.)
        next(n for n in app.number_input if n.label == 'Monthly amount after bills ($)').set_value(0.)
        next(n for n in app.number_input if n.label.startswith('Goal for this pot')).set_value(0.)
        next(b for b in app.button if b.label == 'Compare my scenarios').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any(m.value == 'Not yet funded' for m in app.metric))
        self.assertTrue(any('No money reaches' in m.value for m in app.info))

    def test_default_home_and_presets_and_zero_budget(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'demo_app.py'), default_timeout=40)
        app.session_state['workspace']='Budget planner'
        app.run()
        self.assertFalse(app.exception)
        self.assertIn('Small budget.', app.title[0].value)
        self.assertEqual(next(r for r in app.radio if r.label == 'Examples and candidates (choose one)').value, 'Savings reference')
        self.assertTrue(any(m.value == '$2,000' for m in app.metric))
        next(b for b in app.button if b.label == 'Student starter').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.budget_monthly, 100.)
        next(b for b in app.button if b.label == 'Money needed soon').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any(m.value == '$0' for m in app.metric))
        self.assertEqual(app.session_state.budget_months, 12)
        next(n for n in app.number_input if n.label == 'Savings available now ($)').set_value(9500.)
        next(n for n in app.number_input if n.label == 'Emergency cash to protect ($)').set_value(3000.)
        next(n for n in app.number_input if n.label == 'Money needed soon ($)').set_value(500.)
        next(b for b in app.button if b.label == 'Compare my scenarios').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any(m.value == '$6,000' for m in app.metric))


if __name__ == '__main__':
    unittest.main()
