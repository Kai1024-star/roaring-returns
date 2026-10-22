"""Export made-up budget aggregates only; never provider series or user entries."""
from pathlib import Path
from hashlib import sha256
import json
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from roaring_returns.market_data import load_market,UNIVERSE
from roaring_returns.market_models import (CORE,MODELS,calibrate,simulate,minimum_variance,
    feasible_reference,balanced_example,scenario_min_cvar,scenario_groups,path_summary)
from roaring_returns.planner import Budget

destination=ROOT/'results/market_v5'
if destination.exists():raise SystemExit('Export exists; explicitly archive it before a new numerical run.')
prices,_,data=load_market(ROOT)
rows=[];groups=[];weight_rows=[];fits=[]
for universe,symbols in [('Core',CORE),('Extended',tuple(UNIVERSE))]:
    cal=calibrate(prices,symbols,years=20)
    fits.append(dict(universe=universe,symbols=symbols,first_date=cal.first_date,last_date=cal.last_date,
        daily_observations=cal.observations,weekly_observations=cal.weekly_observations,
        covariance_through=cal.weekly_last,minimum_eigenvalue=float(np.linalg.eigvalsh(cal.covariance).min())))
    for model in MODELS:
        tail,audit=scenario_min_cvar(cal)
        candidates={'Class example':balanced_example(symbols),'Minimum variance':minimum_variance(cal),
                    'Scenario downside':tail,'Feasible equal-weight control':feasible_reference(cal)}
        for label,weights in candidates.items():
            weight_rows.extend(dict(universe=universe,model=model,allocation=label,fund=s,weight=float(w)) for s,w in zip(symbols,weights))
            for months in [12,36]:
                budget=Budget(savings=1000,emergency_reserve=0,near_term=0,monthly=100,months=months,goal_today=0)
                result=simulate(cal,budget,weights,model,paths=1000)
                key=dict(case_id=len(rows)+1,universe=universe,model=model,allocation=label,months=months)
                rows.append(dict(**key,**path_summary(result),
                    pnl_reconciliation_error=float(abs(result.wealth[:,-1]-result.deposits[-1]-result.market_pnl+result.fees).max()),
                    one_month_training_cvar=audit['monthly_model_cvar'] if label=='Scenario downside' else None))
                gs,labels=scenario_groups(result)
                for group in gs:
                    i=group['representative']
                    assert labels[i]==group['group']-1
                    groups.append(dict(**key,**group,representative_ending=float(result.wealth[i,-1]),
                        representative_return=float(result.nav[i,-1]-1),representative_drawdown=float(result.max_drawdown[i])))
destination.mkdir(parents=True)
pd.DataFrame(rows).to_csv(destination/'summary.csv',index=False)
pd.DataFrame(groups).to_csv(destination/'scenario_groups.csv',index=False)
pd.DataFrame(weight_rows).to_csv(destination/'weights.csv',index=False)
(destination/'calibration.json').write_text(json.dumps(fits,indent=2)+'\n')
metadata={k:v for k,v in data.items() if k!='files'}
metadata['files']=[{k:v for k,v in entry.items() if k!='last_close'} for entry in data['files']]
(destination/'data_manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
modules=['market_models.py','market_data.py','planner.py','data.py','synthetic.py']
manifest=dict(schema=1,numerical_module_hashes={name:sha256((ROOT/'src/roaring_returns'/name).read_bytes()).hexdigest() for name in modules},
    artifact_hashes={p.name:sha256(p.read_bytes()).hexdigest() for p in destination.iterdir()},
    case_count=len(rows),paths_per_case=1000,seed=20261022,optimization='All overlapping historical 21-session windows; no training seed',
    parameters=dict(cash=.1,equity_minimum=.4,single_risky_cap=.45,commodity_cap=.2,oil_cap=.1,
        retained_excess_log_mean=.25,cash_rate=.03,cost_bps=2,block_sessions=21,requested_calibration_years=20),
    budget='Made-up $1000 investable now + $100/month; no user financial data',
    interpretation='Conditional model checks, not posterior path probabilities or prospective evidence')
(destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(cases=len(rows),groups=len(groups),maximum_pnl_error=max(r['pnl_reconciliation_error'] for r in rows)),indent=2))
