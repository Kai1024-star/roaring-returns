"""Export derived v0.4 checks for an explicitly made-up budget. No price data."""
import argparse
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
import pandas as pd
from roaring_returns.planner import Budget,PlanningSettings,EXAMPLES,describe_result,replay_daily
from roaring_returns.planner_data import load_planner_data,planner_risky_history
from roaring_returns.planning_models import risk_balance,money_weighted_return
from roaring_returns.planning_scenarios import month_library,simulate_daily_scenarios,SCENARIOS


def digest(path):return sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('results/planner_v4'))
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    output=args.output
    if output.exists():raise FileExistsError('Audit output already exists; choose a new directory.')
    prices,meta=load_planner_data(root); risky=planner_risky_history(root)
    baseline=prices.resample('ME').last().pct_change(fill_method=None).iloc[1:]
    cash=float(np.expm1(12*np.log1p(baseline.BIL).mean()))
    budget=Budget(savings=3000,emergency_reserve=1500,near_term=500,monthly=100,months=60,goal_today=0,comfortable_dip=300)
    cfg=PlanningSettings(cash_rate=cash)
    model=risk_balance(risky,prices.index[-1],.2,756)
    mixes={**EXAMPLES,'Risk-balanced candidate':tuple(model.weights),'Same cash / equal risky weights':(.2,.8/3,.8/3,.8/3)}
    library=month_library(prices)
    future=[]
    for name,weights in mixes.items():
        for mode in SCENARIOS:
            result=simulate_daily_scenarios(library,budget,weights,cfg,mode)
            future.append({'candidate':name,'assumption':mode,**describe_result(result,budget,cfg)})
    sensitivity=[]
    for window,limit in [('Full sample',None),('Last 10 years',120)]:
        lib=month_library(prices,limit)
        for block in [3,6,12]:
            settings=replace(cfg,block_months=block)
            r=simulate_daily_scenarios(lib,budget,model.weights,settings)
            sensitivity.append({'candidate':'Risk-balanced candidate','window':window,'block_months':block,**describe_result(r,budget,settings)})
    historical=[]; fitted=[]
    for event,start,end in [('2008–09','2008-09-01','2009-03-31'),('2020','2020-02-01','2020-04-30'),('2022','2022-01-01','2022-12-31')]:
        signal=prices.index[prices.index<pd.Timestamp(start)][-1]
        event_model=risk_balance(risky,signal,.2,756)
        fitted.append({'event':event,'estimated_from':event_model.first_date,'estimated_through':event_model.last_date,'observations':event_model.observations,
            'weights':event_model.weights.tolist(),'risk_shares':event_model.risk_contributions.tolist(),'kkt_error':event_model.kkt_error})
        event_mixes={**mixes,'Risk-balanced candidate':tuple(event_model.weights)}
        for name,weights in event_mixes.items():
            r=replay_daily(prices,budget,weights,cfg,start,end)
            reconciliation=float(np.max(np.abs(r.sample_asset_pnl.sum(1)-r.fee_path[0]-(r.wealth[0]-r.contributed))))
            historical.append({'event':event,'candidate':name,'ending_value':r.wealth[0,-1],'deposits':r.contributed[-1],
                'net_investment_pnl':r.wealth[0,-1]-r.contributed[-1],'cumulative_twr':r.nav[0,-1]-1,
                'maximum_drawdown':r.max_drawdown[0],'maximum_dollar_dip':r.maximum_dip[0],'fees':r.fees[0],
                'annualized_xirr_audit_only':money_weighted_return(r),'pnl_reconciliation_error':reconciliation})
    output.mkdir(parents=True)
    pd.DataFrame(future).to_csv(output/'scenario_comparison.csv',index=False)
    pd.DataFrame(sensitivity).to_csv(output/'sensitivity.csv',index=False)
    pd.DataFrame(historical).to_csv(output/'historical_replays.csv',index=False)
    (output/'causal_model_fits.json').write_text(json.dumps(fitted,indent=2)+'\n')
    modules=['planner.py','planner_data.py','planning_models.py','planning_scenarios.py']
    manifest={'purpose':'Derived demonstration checks; fabricated student profile, not user financial data',
        'budget':asdict(budget),'settings':asdict(cfg),'data_sha256':meta['processed_sha256'],
        'numerical_module_hashes':{n:digest(root/'src/roaring_returns'/n) for n in modules},
        'artifact_hashes':{p.name:digest(p) for p in sorted(output.iterdir())},
        'limitations':['historical source already inspected','covariance fit overlaps future resampling input','conditional scenarios, not forecast probabilities','no taxes or whole-share execution']}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    report='''# Planner v0.4 derived audit

This audit uses a **made-up** student profile: $3,000 total savings, $2,000
protected outside the pot, $1,000 initially invested, and $100/month for 60 months.
These numbers do not represent the user. All monetary results exclude taxes.

- 18 future cases: six allocations × three excess-return assumptions.
- Six sensitivity cases for the risk-balanced candidate: 3/6/12-month blocks,
  full input sample versus the last ten years.
- 18 daily historical replays: six candidates × three stress episodes.
- Every event-specific ERC fit uses 756 earlier observations; dates and
  first-order errors are in `causal_model_fits.json`.
- `historical_replays.csv` reports cumulative TWR and dollar P&L separately.
  Its annualized XIRR column is explicitly an audit field; the app converts it
  to the replay's own total period for comparison with cumulative TWR.

Non-wrapping blocks underweight sample boundary months. The zero-premium case
centers the **conditional eligible-month distribution at each block position**,
not the realized simulated paths. Expected excess log return is zero at every
position; finite draws need not average exactly zero. All allocations within a
case use identical sampled months and external cash flows. Historical covariance
uses longer SPY/GLD/IEF history; the four-asset performance sample still starts
in 2007. Future covariance fits overlap the resampling input. This is descriptive
model checking, not new independent validation or a prospective trading record.

The risk-balanced candidate is a convex equal-risk-contribution solve on a
positive definite, diagonally shrunk covariance. The cash share is fixed by the
example, and a same-cash/equal-risky-capital control is included. This objective
does not maximize returns or establish suitability, and does not claim to beat
the controls. Inspect the CSVs rather than interpreting one scenario as a forecast.

See [the implementation contract](../../docs/BUDGET_PLANNER.md). The manifest
hashes numeric source, input snapshot and exported tables. No daily prices or
paper PDFs are redistributed.
'''
    (output/'README.md').write_text(report)
    # README is explanatory; numerical tables and model fits are hashed above.
    print(f'Exported {len(future)} future + {len(sensitivity)} sensitivity + {len(historical)} historical cases to {output}')


if __name__=='__main__':main()
