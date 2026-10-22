import unittest
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from dataclasses import replace
import numpy as np
from scipy.optimize import minimize, linprog
from roaring_returns.market_data import market_or_synthetic, completed_date, load_market
from roaring_returns.market_models import (CORE,MODELS,calibrate,shocks,simulate,
    minimum_variance,feasible_reference,balanced_example,scenario_groups,scenario_min_cvar,one_month_scenarios,empirical_cvar)
from roaring_returns.planner import Budget


class MarketModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with TemporaryDirectory() as directory:
            cls.prices,_,_,_=market_or_synthetic(directory)
        cls.symbols=('BIL','SPY','GLD','IEF','USO')
        cls.cal=calibrate(cls.prices,cls.symbols,years=10)

    def test_calibration_cannot_read_future(self):
        cutoff=self.prices.index[-400]
        original=calibrate(self.prices,self.symbols,cutoff)
        contaminated=self.prices.copy()
        contaminated.loc[contaminated.index>cutoff]*=np.linspace(3,9,len(self.prices.loc[self.prices.index>cutoff]))[:,None]
        other=calibrate(contaminated,self.symbols,cutoff)
        np.testing.assert_array_equal(original.excess,other.excess)
        np.testing.assert_array_equal(original.covariance,other.covariance)
        self.assertLessEqual(original.weekly_last,str(cutoff.date()))

    def test_gbm_log_moments_and_cross_asset_correlation(self):
        cal=self.cal
        draws=np.stack(list(shocks(cal,2000,30,MODELS[1],premium=.25)),axis=0)
        log=np.log1p(draws[:,:,1:]).reshape(-1,len(cal.symbols)-1)
        expected=np.log1p(.03)/252+.25*cal.daily_mean
        se=np.sqrt(np.diag(cal.covariance)/252/len(log))
        self.assertTrue((np.abs(log.mean(0)-expected)<5*se).all())
        np.testing.assert_allclose(np.cov(log,rowvar=False),cal.covariance/252,rtol=.06,atol=2e-6)
        np.testing.assert_allclose(draws[:,:,0],1.03**(1/252)-1,atol=1e-15)

    def test_default_covariance_does_not_erase_observed_correlations(self):
        cal=self.cal
        self.assertEqual(cal.shrinkage,0)
        np.testing.assert_allclose(cal.covariance,cal.raw_covariance,rtol=1e-9,atol=1e-12)

    def test_fractional_tail_mass_and_deterministic_window_population(self):
        # 5% of 23 observations = 1.15 observations: full maximum and 0.15 of next.
        losses=np.arange(23.)
        self.assertAlmostEqual(empirical_cvar(losses),(22+.15*21)/1.15)
        first=one_month_scenarios(self.cal,premium=0)
        np.testing.assert_array_equal(first,one_month_scenarios(self.cal,premium=0))
        np.testing.assert_allclose(np.log1p(first).mean(0),np.log1p(.03)/12,atol=1e-15)

    def test_processed_snapshot_hash_is_enforced(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);raw=root/'data/raw/market_v5/2020-01-01';processed=root/'data/processed/market_v5/2020-01-01'
            raw.mkdir(parents=True);processed.mkdir(parents=True)
            meta={'assets':list(self.symbols),'files':[],'processed':{}}
            for name in ['adjusted.csv','quotes.csv']:
                f=processed/name
                self.prices[list(self.symbols)].rename_axis('date').to_csv(f)
                meta['processed'][name]=sha256(f.read_bytes()).hexdigest()
            (raw/'manifest.json').write_text(json.dumps(meta))
            load_market(root,'2020-01-01')
            (processed/'adjusted.csv').write_text('corrupted')
            with self.assertRaises(ValueError):load_market(root,'2020-01-01')

    def test_prefix_stability_for_both_models(self):
        for mode in MODELS:
            short=np.array(list(shocks(self.cal,13,17,mode,seed=9)))
            long=np.array(list(shocks(self.cal,13,42,mode,seed=9)))
            np.testing.assert_array_equal(short,long[:17])

    def test_nonwrapping_block_conditional_center_exact(self):
        x=self.cal.excess
        for block in [5,21,63]:
            for offset in range(block):
                eligible=x[offset:offset+len(x)-block+1]
                np.testing.assert_allclose((eligible-eligible.mean(0)).mean(0),0,atol=1e-15)

    def test_cash_annuity_and_flow_neutral_returns(self):
        budget=Budget(savings=1000,emergency_reserve=0,near_term=0,monthly=100,months=12)
        weights=np.r_[1.,np.zeros(len(self.symbols)-1)]
        for mode in MODELS:
            r=simulate(self.cal,budget,weights,mode,paths=10,cash_rate=.04,cost_bps=25)
            g=1.04**(1/12)
            np.testing.assert_allclose(r.wealth[:,-1],1000*g**12+100*(g**12-1)/(g-1),atol=1e-7)
            np.testing.assert_allclose(r.nav[:,-1],1.04,atol=1e-12)
            np.testing.assert_allclose(r.fees,0)

    def test_multifund_budget_fees_and_drawdown_reconcile(self):
        budget=Budget(savings=1000,emergency_reserve=0,near_term=0,monthly=300,months=8)
        for mode in MODELS:
            r=simulate(self.cal,budget,balanced_example(self.symbols),mode,paths=15,cost_bps=25)
            np.testing.assert_allclose(r.wealth[:,-1]-r.deposits[-1],r.market_pnl-r.fees,atol=1e-8)
            np.testing.assert_allclose(r.max_drawdown,r.drawdown.max(1),atol=0)
            self.assertTrue((r.wealth>=0).all())
            np.testing.assert_array_equal(np.flatnonzero(np.diff(r.deposits)>0)+1,np.arange(21,169,21))
            scaled=simulate(self.cal,replace(budget,savings=2000,monthly=600),balanced_example(self.symbols),mode,paths=15,cost_bps=25)
            np.testing.assert_allclose(scaled.wealth,r.wealth*2,rtol=1e-10,atol=1e-7)
            np.testing.assert_allclose(scaled.nav,r.nav,atol=1e-10)

    def test_unfunded_and_late_funding_not_fabricated_returns(self):
        budget=Budget(savings=0,emergency_reserve=300,near_term=0,monthly=100,months=6)
        r=simulate(self.cal,budget,balanced_example(self.symbols),paths=4)
        self.assertFalse(r.valid[:,:84].any())
        self.assertTrue(r.valid[:,84:].all())
        r=simulate(self.cal,replace(budget,monthly=0),balanced_example(self.symbols),paths=4)
        self.assertFalse(r.valid.any());self.assertEqual(scenario_groups(r)[0][0]['share'],1)

    def test_minimum_variance_cross_solved_and_caps_shared(self):
        cal=calibrate(self.prices,CORE)
        a=minimum_variance(cal)
        ref=feasible_reference(cal)
        eq=[i for i,s in enumerate(CORE) if s in ['SPY','VEA','VWO']]
        com=[CORE.index('GLD')]
        cons=[{'type':'eq','fun':lambda w:w.sum()-1},
              {'type':'eq','fun':lambda w:w[0]-.1},
              {'type':'ineq','fun':lambda w:w[eq].sum()-.4},
              {'type':'ineq','fun':lambda w:.2-w[com].sum()}]
        def obj(w):return w[1:]@cal.covariance@w[1:]/np.trace(cal.covariance)
        cross=minimize(obj,ref,method='SLSQP',bounds=[(0,1)]+[(0,.45)]*(len(CORE)-1),constraints=cons,
                       options={'ftol':1e-12,'maxiter':500})
        self.assertTrue(cross.success)
        self.assertAlmostEqual(obj(a),cross.fun,places=8)
        self.assertLessEqual(obj(a),obj(ref)+1e-9)
        self.assertAlmostEqual(a[0],.1,places=7)
        with self.assertRaises(ValueError):minimum_variance(cal,cash=.8,equity=.5)

    def test_cvar_independent_highs_linear_program(self):
        cal=calibrate(self.prices,CORE,years=3)
        weights,audit=scenario_min_cvar(cal)
        returns=one_month_scenarios(cal);n,p=returns.shape
        # Independent variable layout: weights, VaR threshold, positive excesses.
        objective=np.r_[np.zeros(p),1.,np.full(n,1/(.05*n))]
        upper=np.c_[-returns,-np.ones(n),-np.eye(n)]
        equity=np.array([1 if s in ['SPY','VEA','VWO'] else 0 for s in CORE])
        commodities=np.array([1 if s=='GLD' else 0 for s in CORE])
        upper=np.vstack([upper,np.r_[-equity,np.zeros(n+1)],np.r_[commodities,np.zeros(n+1)]])
        beq=np.array([1.,.1]);aeq=np.zeros((2,p+n+1));aeq[0,:p]=1;aeq[1,0]=1
        high=linprog(objective,A_ub=upper,b_ub=np.r_[np.zeros(n),-.4,.2],A_eq=aeq,b_eq=beq,
            bounds=[(0,1)]+[(0,.45)]*(p-1)+[(None,None)]+[(0,None)]*n,method='highs')
        self.assertTrue(high.success)
        self.assertAlmostEqual(audit['monthly_model_cvar'],high.fun,places=7)
        self.assertAlmostEqual(empirical_cvar(-returns@weights),high.fun,places=7)
        self.assertEqual(n,len(cal.excess)-20)

    def test_groups_are_partition_and_representatives_are_actual_members(self):
        budget=Budget(savings=1000,emergency_reserve=0,near_term=0,monthly=100,months=12)
        r=simulate(self.cal,budget,balanced_example(self.symbols),paths=120)
        groups,labels=scenario_groups(r)
        self.assertEqual(sum(g['count'] for g in groups),120)
        self.assertAlmostEqual(sum(g['share'] for g in groups),1)
        self.assertEqual(groups[0]['count'],max(g['count'] for g in groups))
        for group in groups:self.assertEqual(labels[group['representative']],group['group']-1)
        self.assertEqual(groups,scenario_groups(r)[0])


class MarketUITests(unittest.TestCase):
    def test_offline_workspace_and_all_views_and_generator(self):
        from streamlit.testing.v1 import AppTest
        from roaring_returns import market_ui
        with TemporaryDirectory() as folder,patch.object(market_ui,'ROOT',Path(folder)):
            market_ui._market.clear()
            app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'demo_app.py'),default_timeout=45).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('SYNTHETIC OFFLINE' in w.value for w in app.warning))
            self.assertTrue(any(s.label=='Highlight a representative scenario' for s in app.selectbox))
            next(s for s in app.selectbox if s.label=='Path generator').set_value(MODELS[1]).run()
            self.assertFalse(app.exception)
            next(b for b in app.button if b.label=='Generate another random batch').click().run()
            self.assertEqual(app.session_state.market_seed,20261023)
            next(c for c in app.checkbox if c.label.startswith('Enable oil')).set_value(True).run()
            next(s for s in app.selectbox if s.label=='Simulate the portfolio or inspect one fund').set_value('USO').run()
            self.assertFalse(app.exception)
            next(n for n in app.number_input if n.label=='Investable now ($)').set_value(1700.)
            next(b for b in app.button if b.label=='Apply settings').click().run()
            for name in ['Optimize','Real markets','Model audit','Simulation']:
                next(r for r in app.radio if r.label=='Explore').set_value(name).run()
                self.assertFalse(app.exception)
                self.assertEqual(next(n for n in app.number_input if n.label=='Investable now ($)').value,1700.)
        market_ui._market.clear()


if __name__=='__main__':unittest.main()
