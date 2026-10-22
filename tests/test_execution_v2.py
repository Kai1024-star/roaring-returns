import importlib.util
import unittest
from dataclasses import replace
import numpy as np
import pandas as pd
from roaring_returns.risk import forecast_risk, execution_scenarios, qlike
from roaring_returns.optimization import OptimizerSettings, finite_cvar, buffered_minimum_sale
from roaring_returns.policies import min_sales_band
from roaring_returns.engine import BacktestConfig, backtest, execute_dollar_plan
from roaring_returns.execution_research import ResearchConfig, backtest_execution, RESEARCH_STRATEGIES
from roaring_returns.synthetic import synthetic_prices

HAS_SOLVER = importlib.util.find_spec("cvxpy") is not None


class RiskModelTests(unittest.TestCase):
    def setUp(self):
        self.r = np.random.default_rng(55).normal(0, [.02, .01, .005], (750, 3))

    def test_ridge_uses_only_matured_labels_and_positive_covariance(self):
        forecast = forecast_risk(self.r, "ridge_vol")
        self.assertEqual(forecast.used_model, "ridge_vol")
        self.assertEqual(forecast.training_samples, 504)
        self.assertGreater(np.linalg.eigvalsh(forecast.covariance).min(), 0)
        # The current-origin feature vector is prediction-only; this validates
        # the coefficient fit against an augmented least-squares implementation.
        x = self.r[-527:]
        sq = x*x
        feature = np.stack([np.log(np.maximum(pd.DataFrame(sq).rolling(w).mean().to_numpy(), 1e-10)) for w in (1, 5, 22)], axis=2)
        valid = np.isfinite(feature[:-1]).all(axis=(1, 2))
        tx, ty = feature[:-1][valid][-504:, 0], sq[1:][valid][-504:, 0]
        design = np.column_stack([np.ones(len(tx)), (tx-tx.mean(0))/np.maximum(tx.std(0), 1e-6)])
        augmented = np.vstack([design, np.diag([0, np.sqrt(10), np.sqrt(10), np.sqrt(10)])])
        beta = np.linalg.lstsq(augmented, np.r_[ty/ty.mean(), np.zeros(4)], rcond=None)[0]
        np.testing.assert_allclose(forecast.coefficients[0], beta, atol=2e-9)

    def test_fallback_is_explicit_and_scenarios_reproducible(self):
        f = forecast_risk(self.r[:50], "ridge_vol")
        self.assertEqual(f.used_model, "ewma_fallback")
        s = execution_scenarios(self.r[:50], f, seed=2)
        np.testing.assert_array_equal(s, execution_scenarios(self.r[:50], f, seed=2))
        self.assertTrue((s > -1).all())
        np.testing.assert_allclose(s.mean(0), 0, atol=1e-12)

    def test_all_history_scenarios_are_seed_invariant(self):
        forecast = forecast_risk(self.r, "ewma")
        np.testing.assert_array_equal(execution_scenarios(self.r, forecast, seed=1),
                                      execution_scenarios(self.r, forecast, seed=999))

    def test_qlike_and_fractional_tail_mass(self):
        np.testing.assert_allclose(qlike(np.array([.1]), np.array([.01])), np.log(.01)+1)
        self.assertAlmostEqual(finite_cvar([0, 1, 2, 3], .625), (3+.5*2)/1.5)
        self.assertAlmostEqual(finite_cvar([0, 1, 2, 3], 0), 1.5)

    def test_buffer_zero_variance_recovers_static_rule_and_jacobian(self):
        h, a = np.array([450., 250., 300.]), np.array([.4, .3, .3])
        trades, delta = buffered_minimum_sale(h, 0, 100, a, .05, np.zeros((3, 3)))
        np.testing.assert_allclose(trades+h, min_sales_band(h, 100, a, .05), atol=1e-9)
        np.testing.assert_array_equal(delta, 0)
        total = h.sum()+100
        t = total*a-h
        jac = np.diag(h/total)-np.outer(a, h/total)
        for j in range(3):
            shock = np.zeros(3); shock[j] = 1e-7
            final = h*(1+shock)+t
            np.testing.assert_allclose((final/final.sum()-a)/1e-7, jac[:, j], atol=1e-8)


@unittest.skipUnless(HAS_SOLVER, "Install .[research] for v0.2 optimization checks")
class OptimizationTests(unittest.TestCase):
    def test_cvar_lp_matches_explicit_highs_epigraph_on_random_instances(self):
        from scipy.optimize import linprog
        from roaring_returns.optimization import optimize_minimum_sale
        rng = np.random.default_rng(876)
        for _ in range(12):
            h = rng.dirichlet([3., 3., 3.])*10000
            flow = float(rng.uniform(0, 400))
            a = np.repeat(1/3, 3)
            shocks = rng.normal(0, [.03, .02, .01], (8, 3))
            settings = OptimizerSettings(tail_budget=.0005, cost_bps=10)
            got = optimize_minimum_sale(h, 0, flow, a, shocks, settings)
            # Variables: b[3], s[3], slack, eta, u[8]. Encode CVaR directly:
            # u_j >= +/-deviation_ij - band*wealth_j - eta, u_j>=0.
            m, n = shocks.shape
            size = 2*n+2+m
            objective = np.zeros(size)
            objective[n:2*n] = 1
            objective[2*n] = settings.tail_slack_penalty
            total = h.sum()+flow
            marked = (1+shocks)*h/total
            aub, bub = [], []
            for j in range(m):
                for i in range(n):
                    for sign in (-1, 1):
                        row = np.zeros(size)
                        coeff = sign*(np.eye(n)[i]-a[i])-settings.band
                        row[:n], row[n:2*n] = coeff, -coeff
                        row[2*n+1], row[2*n+2+j] = -1, -1
                        const = sign*(marked[j, i]-a[i]*marked[j].sum())-settings.band*marked[j].sum()
                        aub.append(row); bub.append(-const)
                row = np.zeros(size)
                row[:n], row[n:2*n] = -1, 1
                aub.append(row); bub.append(marked[j].sum()-1e-6)
            row = np.zeros(size)
            row[2*n], row[2*n+1], row[2*n+2:] = -1, 1, 1/((1-settings.tail_level)*m)
            aub.append(row); bub.append(settings.tail_budget)
            eq = np.zeros((1, size))
            rate = settings.cost_bps/10000
            eq[0, :n], eq[0, n:2*n] = 1+rate, -(1-rate)
            caps = np.minimum(h/total, marked.min(0))
            bounds = [(0, None)]*n+[(0, float(cap)) for cap in caps]+[(0, None)]*(2+m)
            independent = linprog(objective, A_ub=np.asarray(aub), b_ub=bub,
                A_eq=eq, b_eq=[flow/total], bounds=bounds, method="highs")
            self.assertTrue(independent.success, independent.message)
            self.assertAlmostEqual(got.objective, independent.fun, delta=5e-6)

    def test_buy_only_feasible_means_no_micro_sales_and_centered_jensen_bound(self):
        from roaring_returns.optimization import optimize_minimum_sale
        h = np.array([3600., 3300., 3100.])
        a = np.repeat(1/3, 3)
        r = np.array([[.01, -.005, .002], [-.01, .005, -.002]])
        for budget in (0., .0005, .01):
            got = optimize_minimum_sale(h, 0, 100, a, r, OptimizerSettings(tail_budget=budget))
            self.assertGreaterEqual(got.trades.min(), 0.)
            self.assertAlmostEqual(got.budget_residual, 0., places=8)
            signal = h+got.trades
            excess = max(0., np.max(np.abs(signal-a*signal.sum()))-.05*signal.sum())/10100
            self.assertLessEqual(excess, got.tail_loss+1e-8)

    def test_hard_risk_budget_relaxation_cannot_require_more_sales(self):
        from roaring_returns.optimization import optimize_minimum_sale
        h = np.array([6000., 2000., 2000.])
        a = np.repeat(1/3, 3)
        r = np.array([[.01, -.005, .002], [-.01, .005, -.002]])
        sales = [np.maximum(-optimize_minimum_sale(h, 0, 100, a, r,
                    OptimizerSettings(tail_budget=b), hard_risk=True).trades, 0).sum()
                 for b in (0., .0005, .005)]
        self.assertTrue(np.all(np.diff(sales) <= .001), sales)

    def test_tie_break_failure_preserves_verified_lp_and_is_disclosed(self):
        import cvxpy as cp
        from unittest.mock import patch
        from roaring_returns.optimization import optimize_minimum_sale
        original = cp.Problem.solve
        calls = []
        def fail_tie_only(problem, *args, **kwargs):
            calls.append(kwargs.get("solver"))
            if len(calls) == 1:
                return original(problem, *args, **kwargs)
            problem._status = cp.INFEASIBLE
            return None
        with patch.object(cp.Problem, "solve", fail_tie_only):
            got = optimize_minimum_sale(np.array([6000., 2000., 2000.]), 0, 100,
                                       np.repeat(1/3, 3), np.zeros((3, 3)))
        self.assertEqual(got.status, "optimal_lp_only")
        self.assertFalse(got.tie_break_completed)
        self.assertIn("LP-only fallback", got.solver_trace)
        self.assertLess(abs(got.budget_residual), .001)
        self.assertGreaterEqual(got.scenario_weights.min(), 0)
        self.assertEqual(calls, ["CLARABEL", "CLARABEL", "OSQP"])

    def test_hard_zero_risk_budget_recovers_static_minimum_sale(self):
        from roaring_returns.optimization import optimize_minimum_sale
        for holdings, flow in (([450, 250, 300], 0), ([600, 100, 300], 50), ([900, 50, 50], 0)):
            h, a = np.array(holdings, float), np.array([.4, .3, .3])
            result = optimize_minimum_sale(h, 0, flow, a, np.zeros((1, 3)),
                         OptimizerSettings(cost_bps=0, tail_budget=0), hard_risk=True)
            expected = min_sales_band(h, flow, a, .05)
            self.assertAlmostEqual(np.maximum(-result.trades, 0).sum(), np.maximum(h-expected, 0).sum(), delta=.002)
            np.testing.assert_allclose(result.trades+h, expected, atol=.005)

    def test_cvar_minimum_sale_fee_budget_and_soft_infeasibility_visible(self):
        from roaring_returns.optimization import optimize_minimum_sale
        h = np.array([1000., 0., 0.])
        scenarios = np.array([[0., 0., 0.], [-.8, .1, .1]])
        p = optimize_minimum_sale(h, 0, 100, [1/3]*3, scenarios,
                                 OptimizerSettings(cost_bps=10, tail_budget=.0005))
        self.assertGreater(p.risk_slack, 0)
        self.assertLess(abs(p.budget_residual), .002)
        self.assertTrue(((1+scenarios)*h+p.trades >= -.001).all())
    def test_zero_shocks_flat_market_and_scale_invariance(self):
        from roaring_returns.optimization import optimize_execution
        h, a = np.array([400., 300., 300.]), [.4, .3, .3]
        settings = OptimizerSettings(cost_bps=10)
        p = optimize_execution(h, 0, 100, a, np.zeros((3, 3)), settings)
        q = optimize_execution(h*100, 0, 10000, a, np.zeros((3, 3)), settings)
        np.testing.assert_allclose(q.trades/100, p.trades, atol=2e-5)
        self.assertLess(abs(p.budget_residual), .001)
        final, cash, _, _, fees = execute_dollar_plan(h, 100, p.trades, .001)
        self.assertAlmostEqual(final.sum()+cash, 1100-fees, places=8)
        self.assertGreaterEqual(cash, 0)

    def test_extreme_scenarios_caps_sales_without_short_positions(self):
        from roaring_returns.optimization import optimize_execution
        h = np.array([900., 50., 50.])
        s = np.array([[0, 0, 0], [-.5, .3, .2], [.2, -.2, -.1]])
        p = optimize_execution(h, 0, 0, [1/3]*3, s)
        self.assertTrue(((1+s)*h+p.trades >= -1e-4).all())
        self.assertLessEqual(np.maximum(-p.trades, 0)[0], 450+.001)

    def test_qp_matches_independent_slsqp_without_tail_or_cost(self):
        from scipy.optimize import minimize
        from roaring_returns.optimization import optimize_execution
        h, a, flow = np.array([550., 150., 300.]), np.array([.4, .3, .3]), 80.
        s = np.array([[0., 0, 0], [.01, -.02, .005], [-.03, .01, .01]])
        settings = OptimizerSettings(cost_bps=0, tail_weight=0, turnover_penalty=.002)
        got = optimize_execution(h, 0, flow, a, s, settings)
        total = h.sum()+flow
        def objective(t):
            final = (1+s)*h+t
            diff = final-final.sum(1)[:, None]*a
            return np.mean(np.sum((diff/total)**2, axis=1))+.002*np.abs(t).sum()/total
        independent = minimize(objective, got.trades, method="SLSQP",
            bounds=[(-float(v), total) for v in np.min((1+s)*h, axis=0)],
            constraints={"type": "eq", "fun": lambda t: t.sum()-flow},
            options={"ftol": 1e-13, "maxiter": 300})
        self.assertTrue(independent.success, independent.message)
        self.assertAlmostEqual(objective(got.trades), independent.fun, places=9)

    def test_legacy_strategies_preserve_v01_accounting(self):
        p = synthetic_prices("2019-01-01", "2020-12-31")
        for name in ("proportional", "annual", "threshold_center", "cashflow_only", "min_sales_band"):
            old = backtest(p, BacktestConfig(name, cost_bps=10))
            new = backtest_execution(p, ResearchConfig(name, cost_bps=10))
            for column in ("wealth", "nav", "cash", "sales", "fees"):
                np.testing.assert_allclose(new.daily[column], old.daily[column], atol=1e-7)

    def test_future_poisoning_preserves_forecasts_scenarios_and_asset_orders(self):
        p = synthetic_prices("2017-01-01", "2020-06-30")
        cutoff = pd.Timestamp("2020-03-31")
        other = p.copy()
        rng = np.random.default_rng(909)
        mask = other.index > cutoff
        other.loc[mask] *= np.exp(rng.normal(0, .2, (mask.sum(), 3)))
        columns = [f"planned_trade_{s}" for s in p.columns]+[f"variance_{m}_{s}" for m in ("historical", "ewma", "ridge_vol") for s in p.columns]
        for name in ("buffered_band", "cost_aware", "scenario_historical", "scenario_ewma", "scenario_ridge", "cvar_sales_ewma", "cvar_sales_ridge"):
            cfg = ResearchConfig(name, scenario_count=16)
            b = backtest_execution(p, cfg, start="2020-01-01")
            c = backtest_execution(other, cfg, start="2020-01-01")
            prefix = b.events.signal_date <= cutoff
            np.testing.assert_array_equal(b.events.loc[prefix, columns], c.events.loc[prefix, columns])
            pd.testing.assert_frame_equal(b.daily.loc[:cutoff], c.daily.loc[:cutoff])

    def test_all_strategies_flow_neutral_in_flat_market(self):
        p = pd.DataFrame(100., index=pd.bdate_range("2020-01-31", "2020-05-01", name="date"), columns=["QQQ", "GLD", "IEF"])
        for name in RESEARCH_STRATEGIES:
            result = backtest_execution(p, ResearchConfig(name, cost_bps=0, scenario_count=8))
            np.testing.assert_allclose(result.daily.nav, 1, atol=1e-10)
            self.assertAlmostEqual(result.daily.wealth.iloc[-1], 10400, places=5)


if __name__ == "__main__":
    unittest.main()
