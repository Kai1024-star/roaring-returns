import importlib.util
import unittest
from dataclasses import replace
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from roaring_returns.planner import Budget,PlanningSettings,EXAMPLES,monthly_returns,simulate_mix,replay_daily
from roaring_returns.planning_models import risk_balance,money_weighted_return,performance_frame,dollar_units
from roaring_returns.planning_scenarios import month_library,sampled_months,anchored_month,simulate_daily_scenarios,SCENARIOS,zero_premium_center


class PlanningV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng=np.random.default_rng(119)
        dates=pd.bdate_range('2018-12-31','2023-12-29',name='date')
        r=rng.normal([.0003,.0002,.00008,.00004],[.012,.013,.004,.00003],(len(dates)-1,4))
        cls.prices=pd.DataFrame(np.vstack([np.ones(4),np.exp(np.cumsum(r,axis=0))])*100,index=dates,columns=['SPY','GLD','IEF','BIL'])
        cls.library=month_library(cls.prices)

    def test_big_contributions_do_not_create_investment_return(self):
        dates=pd.bdate_range('2019-12-31','2020-02-28',name='date')
        p=pd.DataFrame(100.,index=dates,columns=['SPY','GLD','IEF'])
        p.loc['2020-01-15':,'SPY']=80
        b=Budget(savings=200,emergency_reserve=0,near_term=0,monthly=200,months=2)
        cfg=PlanningSettings(cash_rate=0,cost_bps=0)
        r=replay_daily(p,b,(0,1,0,0),cfg,'2020-01-01','2020-02-28')
        self.assertGreater(r.wealth[0,-1],r.wealth[0,0])
        self.assertAlmostEqual(r.wealth[0,-1]-r.contributed[-1],-40)
        self.assertAlmostEqual(r.nav[0,-1]-1,-.2)
        self.assertAlmostEqual(r.max_drawdown[0],.2)

    def test_unit_issuance_independently_reconciles_nav(self):
        b=Budget(months=18); cfg=PlanningSettings(paths=4,cost_bps=25)
        draws=np.random.default_rng(4).normal(0,.08,(4,18,3))
        r=simulate_mix(draws,b,EXAMPLES['Mixed example'],cfg)
        for path in range(4):
            units=b.initial
            for step in range(1,19):
                flow=r.contributed[step]-r.contributed[step-1]
                paid=r.fee_path[path,step]-r.fee_path[path,step-1]
                marked=r.wealth[path,step]-flow+paid
                pre_nav=marked/units
                units += flow/pre_nav
                self.assertAlmostEqual(r.wealth[path,step]/units,r.nav[path,step],places=10)

    def test_pnl_and_asset_attribution_reconcile_every_daily_close(self):
        b=Budget(months=12); cfg=PlanningSettings(cost_bps=25)
        r=replay_daily(self.prices,b,EXAMPLES['More stocks'],cfg,'2022-01-01','2022-12-31')
        np.testing.assert_allclose(r.sample_asset_pnl.sum(1)-r.fee_path[0],r.wealth[0]-r.contributed,atol=1e-7)
        f=performance_frame(r)
        np.testing.assert_allclose(f['Gross market P&L']-f['Fees'],f['Net investment P&L'])
        self.assertAlmostEqual(-f.Drawdown.min(),r.max_drawdown[0],places=12)

    def test_never_funded_returns_are_missing_not_zero_performance(self):
        b=Budget(savings=0,emergency_reserve=10000,near_term=0,monthly=1,months=6)
        cfg=PlanningSettings(paths=4)
        r=simulate_daily_scenarios(self.library,b,EXAMPLES['Mixed example'],cfg)
        self.assertFalse(r.return_valid.any())
        self.assertTrue(performance_frame(r)['Return index'].isna().all())
        self.assertIsNone(money_weighted_return(r))

    def test_cash_irr_matches_independent_annuity_and_short_timing_case(self):
        b=Budget(savings=1000,emergency_reserve=0,near_term=0,monthly=100,months=60)
        cfg=PlanningSettings(cash_rate=.03,cost_bps=0)
        r=simulate_mix(np.zeros((1,60,3)),b,EXAMPLES['Savings reference'],cfg)
        self.assertAlmostEqual(money_weighted_return(r),.03,places=10)
        b=replace(b,savings=0,months=1)
        r=simulate_mix(np.zeros((1,1,3)),b,EXAMPLES['Savings reference'],cfg)
        self.assertIsNone(money_weighted_return(r))

    def test_purchasing_power_discounts_deposits_when_paid(self):
        b=Budget(savings=1000,emergency_reserve=0,near_term=0,monthly=100,months=12)
        cfg=PlanningSettings(cash_rate=.01,inflation=.03,cost_bps=0)
        r=simulate_mix(np.zeros((1,12,3)),b,EXAMPLES['Savings reference'],cfg)
        nominal=dollar_units(r,cfg.inflation,False)
        real=dollar_units(r,cfg.inflation,True)
        expected=1000+sum(100/(1.03**(m/12)) for m in range(1,13))
        self.assertAlmostEqual(real['deposits'][-1],expected,places=10)
        self.assertGreater(nominal['pnl'][0,-1],0)
        self.assertLess(real['pnl'][0,-1],0)
        np.testing.assert_allclose(real['wealth']-real['deposits'],real['pnl'])

    def test_cash_anchor_reconciles_months_with_different_session_counts(self):
        lib=self.library; ids=np.arange(len(lib.counts))
        self.assertGreater(len(set(lib.counts)),1)
        cfg=PlanningSettings(cash_rate=.045)
        for mode in SCENARIOS:
            logs,n=anchored_month(lib,ids,cfg,mode)
            np.testing.assert_allclose(logs[:,:,3].sum(1),np.log1p(.045)/12,atol=1e-15)
        base,_=anchored_month(lib,ids,cfg,SCENARIOS[0]); lower,_=anchored_month(lib,ids,cfg,SCENARIOS[1])
        np.testing.assert_allclose((base[:,:,:3]-lower[:,:,:3]).sum(1),.02/12,atol=1e-15)
        zero,_=anchored_month(lib,ids,cfg,SCENARIOS[2])
        np.testing.assert_allclose((zero[:,:,:3].sum(1)-zero[:,:,3].sum(1)[:,None]).mean(0),0,atol=1e-15)

    def test_zero_premium_centers_actual_non_wrapping_block_distribution(self):
        lib=self.library
        for block in [3,6,12]:
            starts=len(lib.counts)-block+1
            for position in range(block):
                eligible=np.arange(position,position+starts)
                center=zero_premium_center(lib,block,position)
                logs,_=anchored_month(lib,eligible,PlanningSettings(),SCENARIOS[2],center)
                premium=logs[:,:,:3].sum(1)-logs[:,:,3].sum(1)[:,None]
                np.testing.assert_allclose(premium.mean(0),0,atol=1e-15)
        cfg=PlanningSettings(paths=5,block_months=12)
        short=simulate_daily_scenarios(lib,Budget(months=6),EXAMPLES['Mixed example'],cfg,SCENARIOS[2])
        long=simulate_daily_scenarios(lib,Budget(months=12),EXAMPLES['Mixed example'],cfg,SCENARIOS[2])
        np.testing.assert_array_equal(short.wealth,long.wealth[:,:7])

    def test_non_wrapping_joint_blocks_and_stable_horizon_prefix(self):
        cfg=PlanningSettings(paths=20,block_months=6)
        a=sampled_months(self.library,24,cfg); b=sampled_months(self.library,60,cfg)
        np.testing.assert_array_equal(a,b[:,:24])
        self.assertTrue((a>=0).all() and (a<len(self.library.counts)).all())
        for start in range(0,24,6):
            np.testing.assert_array_equal(np.diff(a[:,start:start+6],axis=1),np.ones((20,5),int))

    def test_daily_scenarios_match_monthly_endpoints_but_expose_more_risk(self):
        b=Budget(months=12); cfg=PlanningSettings(paths=12,cost_bps=25)
        ids=sampled_months(self.library,b.months,cfg)
        monthly=[]
        for month in range(b.months):
            logs,_=anchored_month(self.library,ids[:,month],cfg,SCENARIOS[0])
            monthly.append(np.expm1(logs[:,:,:3].sum(1)))
        draws=np.stack(monthly,axis=1)
        a=simulate_daily_scenarios(self.library,b,EXAMPLES['Mixed example'],cfg,indexes=ids)
        m=simulate_mix(draws,b,EXAMPLES['Mixed example'],cfg)
        np.testing.assert_allclose(a.wealth,m.wealth,atol=1e-7)
        np.testing.assert_allclose(a.nav,m.nav,atol=1e-10)
        self.assertTrue((a.max_drawdown+1e-10>=m.max_drawdown).all())
        self.assertTrue((a.maximum_dip+1e-8>=m.maximum_dip).all())
        sample=a.sample_path
        np.testing.assert_allclose(sample.sample_asset_pnl.sum(1)-sample.fee_path[0],sample.wealth[0]-sample.contributed,atol=1e-7)
        self.assertEqual(sample.elapsed_months[-1],12)
        self.assertAlmostEqual(sample.drawdown_path.max(),sample.max_drawdown[0],places=12)
        np.testing.assert_allclose(sample.contributed[-1],a.contributed[-1])
        self.assertAlmostEqual(sample.wealth[0,-1],a.wealth[0,-1],places=8)

    def test_scaling_money_changes_dollars_not_nav_or_weights(self):
        cfg=PlanningSettings(paths=6,cost_bps=25)
        b=Budget(savings=200,emergency_reserve=0,near_term=0,monthly=100,months=6)
        a=simulate_daily_scenarios(self.library,b,EXAMPLES['More stocks'],cfg)
        big=replace(b,savings=b.savings*100,monthly=b.monthly*100)
        z=simulate_daily_scenarios(self.library,big,EXAMPLES['More stocks'],cfg)
        np.testing.assert_allclose(a.wealth*100,z.wealth,atol=1e-6)
        np.testing.assert_allclose(a.nav,z.nav,atol=1e-10)
        np.testing.assert_allclose(a.max_drawdown,z.max_drawdown,atol=1e-10)

    @unittest.skipUnless(importlib.util.find_spec('cvxpy'),'Install demo extra')
    def test_erc_solver_cross_checks_scipy_and_equal_variance_contributions(self):
        for seed in range(6):
            model=risk_balance(self.prices,'2023-12-29',cash_weight=.1*seed,lookback=252+100*seed)
            sigma=model.covariance/np.trace(model.covariance)*3
            opt=minimize(lambda x:.5*x@sigma@x-np.log(x).sum()/3,np.ones(3),
                         jac=lambda x:sigma@x-1/(3*x),bounds=[(1e-8,None)]*3,
                         method='L-BFGS-B',options={'ftol':1e-15,'gtol':1e-12})
            self.assertTrue(opt.success)
            np.testing.assert_allclose(model.risky_weights,opt.x/opt.x.sum(),atol=2e-5)
            np.testing.assert_allclose(model.risk_contributions,1/3,atol=2e-5)
            self.assertGreater(np.linalg.eigvalsh(model.covariance).min(),0)
            self.assertLess(model.kkt_error,2e-5)
            self.assertAlmostEqual(model.weights.sum(),1)
            self.assertTrue((model.weights>=0).all())

    @unittest.skipUnless(importlib.util.find_spec('cvxpy'),'Install demo extra')
    def test_covariance_and_solver_ignore_all_post_decision_prices(self):
        asof='2021-12-31'
        changed=self.prices.copy(); after=changed.index>asof
        changed.loc[after] *= np.random.default_rng(66).uniform(.2,4,(after.sum(),4))
        a=risk_balance(self.prices,asof); b=risk_balance(changed,asof)
        np.testing.assert_array_equal(a.covariance,b.covariance)
        np.testing.assert_array_equal(a.weights,b.weights)
        self.assertLessEqual(pd.Timestamp(a.last_date),pd.Timestamp(asof))
        with self.assertRaises(ValueError):
            risk_balance(self.prices,'2019-01-10')
        with self.assertRaises(ValueError):
            risk_balance(self.prices,'2023-12-29',cash_weight=1.1)


if __name__=='__main__':unittest.main()
