"""Multi-asset conditional path simulation and constrained risk allocation.

GBM is a lognormal benchmark, not a fitted forecast of future expected returns.
Historical blocks retain joint daily shocks; neither model creates new evidence.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .planner import PlanningSettings, _settle_month, flow_neutral_step
from .market_data import UNIVERSE

MODELS = ('Joint historical blocks', 'Correlated Brownian motion (GBM)')
CORE = ('BIL','SPY','VEA','VWO','GLD','SHY','IEF','TLT','TIP')


@dataclass
class Calibration:
    symbols: tuple
    excess: np.ndarray
    daily_mean: np.ndarray
    covariance: np.ndarray  # annualized, estimated from completed weekly returns
    first_date: str
    last_date: str
    observations: int
    weekly_observations: int
    weekly_last: str
    weekly_returns: np.ndarray
    shrinkage: float
    raw_covariance: np.ndarray
    eigenvalue_floor: float


def calibrate(prices, symbols, asof=None, years=10, shrinkage=0.):
    symbols = tuple(symbols)
    if not symbols or symbols[0] != 'BIL' or len(set(symbols)) != len(symbols) or len(symbols)<3:
        raise ValueError('Select cash BIL followed by at least two distinct risky assets.')
    if any(s not in UNIVERSE for s in symbols) or not 0 <= shrinkage <= 1 or not 1 <= years <= 30:
        raise ValueError('Invalid universe or covariance settings.')
    asof = pd.Timestamp(asof or prices.index[-1])
    past = prices.loc[:asof,list(symbols)].tail(int(years*252)+1)
    if (len(past)<253 or past.index.has_duplicates or not past.index.is_monotonic_increasing
            or not np.isfinite(past.to_numpy()).all() or (past<=0).any().any()):
        raise ValueError('Need a full year of complete, positive, ordered pre-decision prices.')
    logs = np.log(past/past.shift()).iloc[1:]
    excess = logs.iloc[:,1:].to_numpy()-logs.iloc[:,0].to_numpy()[:,None]
    weeks = past.resample('W-FRI').last()
    weeks = weeks.loc[weeks.index <= past.index[-1]]
    weekly = weeks.pct_change(fill_method=None).dropna()
    raw = np.atleast_2d(np.cov(weekly.iloc[:,1:].to_numpy(),rowvar=False))*52
    cov = (1-shrinkage)*raw+shrinkage*np.diag(np.maximum(raw.diagonal(),1e-10))
    eigenvalues,eigenvectors=np.linalg.eigh(cov)
    floor=max(float(eigenvalues.max())*1e-6,1e-10)
    cov=(eigenvectors*np.maximum(eigenvalues,floor))@eigenvectors.T
    if np.linalg.eigvalsh(cov).min() <= 0:
        raise ArithmeticError('Covariance must be positive definite.')
    return Calibration(symbols,excess,excess.mean(0),cov,str(logs.index[0].date()),
        str(logs.index[-1].date()),len(logs),len(weekly),str(weekly.index[-1].date()),
        weekly.to_numpy(),shrinkage,raw,floor)


def shocks(cal, paths, days, model, seed=20261022, block=21, premium=.25, cash_rate=.03):
    """Yield daily gross-return vectors in fixed 252-session model years.

    No storage of a paths × days × assets cube. Horizons share exact prefixes.
    Nonwrapping block shocks are centered at each eligible block offset so both
    models have the requested expected excess *log* return at each position.
    """
    if (model not in MODELS or not 1 <= paths <= 3000 or not 1 <= days <= 2520
            or not 1 <= block <= 126 or block > len(cal.excess) or not 0 <= premium <= 1
            or not -.05 <= cash_rate <= .2):
        raise ValueError('Invalid model, simulation dimensions or assumptions.')
    rng = np.random.default_rng(seed)
    cash = np.log1p(cash_rate)/252
    drift = premium*cal.daily_mean
    root = np.linalg.cholesky(cal.covariance/252)
    centers = [cal.excess[j:j+len(cal.excess)-block+1].mean(0) for j in range(block)]
    starts = None
    for day in range(days):
        if model == MODELS[1]:
            noise = rng.standard_normal((paths,len(drift)))@root.T
        else:
            offset = day%block
            if offset == 0:
                starts = rng.integers(0,len(cal.excess)-block+1,size=paths)
            noise = cal.excess[starts+offset]-centers[offset]
        logs = np.c_[np.full(paths,cash),cash+drift+noise]
        yield np.expm1(logs)


@dataclass
class MarketPaths:
    wealth: np.ndarray
    nav: np.ndarray
    drawdown: np.ndarray
    valid: np.ndarray
    deposits: np.ndarray
    fees: np.ndarray
    sales: np.ndarray
    holdings: np.ndarray  # first path, daily
    max_drawdown: np.ndarray
    market_pnl: np.ndarray  # per path, total across all assets


def simulate(cal, budget, weights, model=MODELS[0], paths=800, seed=20261022,
             block=21, premium=.25, cash_rate=.03, cost_bps=2., rebalancing='cash_first_band'):
    budget.validate()
    a = np.asarray(weights,float)
    if a.shape != (len(cal.symbols),) or not np.isfinite(a).all() or (a<0).any() or not np.isclose(a.sum(),1):
        raise ValueError('Long-only asset weights must sum to one.')
    cfg = PlanningSettings(cost_bps=cost_bps,rebalancing=rebalancing)
    cfg.validate()
    days=budget.months*21
    rate=cost_bps/10000
    start=budget.initial/(1+rate*(1-a[0]))
    h=np.tile(start*a,(paths,1))
    wealth=np.zeros((paths,days+1)); wealth[:,0]=start
    nav=np.ones_like(wealth); nav[:,0]=start/budget.initial if budget.initial else 1.
    valid=np.zeros_like(wealth,dtype=bool); valid[:,0]=budget.initial>0
    fees=np.full(paths,budget.initial-start); sales=np.zeros(paths)
    deposits=np.full(days+1,budget.initial)
    dd=np.zeros_like(wealth); dd[:,0]=1-nav[:,0]
    holdings=np.zeros((days+1,len(a))); holdings[0]=h[0]
    peak=np.ones(paths); asset_pnl=np.zeros(paths)
    for step,r in enumerate(shocks(cal,paths,days,model,seed,block,premium,cash_rate),1):
        before=h.sum(1); gains=h*r
        h+=gains; asset_pnl+=gains.sum(1)
        marked=h.sum(1)
        flow=budget.contributions()[step//21-1] if step%21==0 else 0.
        if step%21==0:
            h,paid,sold=_settle_month(h,flow,a,cfg)
            fees+=paid; sales+=sold
        end=h.sum(1)
        nav[:,step],peak,valid[:,step],dd[:,step]=flow_neutral_step(
            before,marked,end,np.full(paths,flow),nav[:,step-1],peak,valid[:,step-1])
        wealth[:,step]=end; holdings[step]=h[0]; deposits[step]=deposits[step-1]+flow
    if not np.allclose(wealth[:,-1]-deposits[-1],asset_pnl-fees,rtol=1e-9,atol=1e-6):
        raise ArithmeticError('Multi-asset account ledger does not reconcile.')
    return MarketPaths(wealth,nav,dd,valid,deposits,fees,sales,holdings,dd.max(1),asset_pnl)


def allocation_constraints(w, symbols, cash, equity, asset_cap, commodity_cap, oil_cap):
    import cvxpy as cp
    groups={g:[i for i,s in enumerate(symbols) if UNIVERSE[s][1]==g] for g in ['Equities','Commodities']}
    cons=[cp.sum(w)==1,w>=0,w[0]==cash,w[1:]<=asset_cap]
    if groups['Equities']:
        cons += [cp.sum(w[groups['Equities']])>=equity]
    elif equity>0:
        raise ValueError('An equity minimum requires at least one equity asset.')
    if groups['Commodities']:
        cons += [cp.sum(w[groups['Commodities']])<=commodity_cap]
    if 'USO' in symbols:
        cons += [w[symbols.index('USO')]<=oil_cap]
    return cons


def minimum_variance(cal, cash=.1, equity=.4, asset_cap=.45, commodity_cap=.2, oil_cap=.1):
    """One transparent risk optimizer; no estimated return is maximized."""
    import cvxpy as cp
    inputs=np.array([cash,equity,asset_cap,commodity_cap,oil_cap])
    if not np.isfinite(inputs).all() or (inputs<0).any() or (inputs>1).any() or cash+equity>1+1e-10:
        raise ValueError('Invalid allocation constraints.')
    w=cp.Variable(len(cal.symbols))
    constraints=allocation_constraints(w,cal.symbols,cash,equity,asset_cap,commodity_cap,oil_cap)
    cov=cal.covariance/np.trace(cal.covariance)
    problem=cp.Problem(cp.Minimize(cp.quad_form(w[1:],cov)),constraints)
    problem.solve(solver='CLARABEL',tol_gap_abs=1e-10,tol_feas=1e-10,tol_gap_rel=1e-10)
    if problem.status != 'optimal' or w.value is None:
        raise ValueError(f'Allocation constraints are not solvable: {problem.status}. Relax a cap or the equity minimum.')
    weights=np.maximum(np.asarray(w.value),0)
    if abs(weights.sum()-1)>1e-7 or max(float(np.max(np.abs(c.violation()))) for c in constraints)>1e-7:
        raise ArithmeticError('Optimizer constraint audit failed.')
    weights/=weights.sum()
    return weights


def balanced_example(symbols, cash=.1):
    """Fixed asset-class example; no suitability or return ranking."""
    symbols=tuple(symbols); weights=np.zeros(len(symbols)); weights[0]=cash
    proportions={'Equities':.5,'Bonds':.35,'Commodities':.15}
    available={g:[i for i,s in enumerate(symbols) if UNIVERSE[s][1]==g] for g in proportions}
    total=sum(p for g,p in proportions.items() if available[g])
    for group,ids in available.items():
        if ids: weights[ids]=(1-cash)*proportions[group]/total/len(ids)
    return weights


def feasible_reference(cal, cash=.1, equity=.4, asset_cap=.45, commodity_cap=.2, oil_cap=.1):
    """Nearest equal-risky-capital weights under exactly the optimizer's caps."""
    import cvxpy as cp
    w=cp.Variable(len(cal.symbols))
    target=np.r_[cash,np.full(len(cal.symbols)-1,(1-cash)/(len(cal.symbols)-1))]
    cons=allocation_constraints(w,cal.symbols,cash,equity,asset_cap,commodity_cap,oil_cap)
    problem=cp.Problem(cp.Minimize(cp.sum_squares(w-target)),cons)
    problem.solve(solver='CLARABEL',tol_gap_abs=1e-10,tol_gap_rel=1e-10,tol_feas=1e-10)
    if problem.status!='optimal' or w.value is None:
        raise ValueError('The same-constraint reference is infeasible.')
    return np.maximum(w.value,0)/np.maximum(w.value,0).sum()


def path_summary(r):
    active=r.valid[:,-1]
    return dict(ending_p05=float(np.quantile(r.wealth[:,-1],.05)),
                ending_median=float(np.median(r.wealth[:,-1])),ending_p95=float(np.quantile(r.wealth[:,-1],.95)),
                median_net_pnl=float(np.median(r.wealth[:,-1]-r.deposits[-1])),
                median_cumulative_return=float(np.median(r.nav[active,-1]-1)) if active.any() else None,
                p95_drawdown=float(np.quantile(r.max_drawdown[active],.95)) if active.any() else None,
                ends_below_deposits=float(np.mean(r.wealth[:,-1]<r.deposits[-1])),
                median_fees=float(np.median(r.fees)),median_sales=float(np.median(r.sales)))


def one_month_scenarios(cal,premium=.25,cash_rate=.03):
    """All overlapping 21-session historical windows, without training sampling.

    Center the complete window population and add the explicit cash/log-growth
    assumptions. Overlapping windows are not independent market observations.
    """
    if not 0<=premium<=1 or not -.05<=cash_rate<=.2:
        raise ValueError('Invalid scenario log-growth assumptions.')
    cumulative=np.vstack([np.zeros(cal.excess.shape[1]),cal.excess.cumsum(0)])
    windows=cumulative[21:]-cumulative[:-21]
    centered=windows-windows.mean(0)
    cash=np.log1p(cash_rate)/12
    risky=cash+21*premium*cal.daily_mean+centered
    return np.expm1(np.c_[np.full(len(windows),cash),risky])


def empirical_cvar(losses,tail=.05):
    """Exact equal-weight RU tail average, including a fractional boundary mass."""
    values=np.sort(np.asarray(losses))[::-1]
    mass=len(values)*tail
    whole=int(np.floor(mass))
    return float((values[:whole].sum()+(mass-whole)*values[min(whole,len(values)-1)])/mass)


def scenario_min_cvar(cal,cash=.1,equity=.4,asset_cap=.45,
                      commodity_cap=.2,oil_cap=.1,premium=.25,cash_rate=.03):
    """Minimize average loss in the worst 5% of model one-month outcomes.

    An empirical Rockafellar-Uryasev LP on every overlapping 21-session window.
    There is no random training seed to optimize against.
    Gross one-month buy-and-hold objective; path evaluation includes fees.
    """
    import cvxpy as cp
    returns=one_month_scenarios(cal,premium=premium,cash_rate=cash_rate)
    w=cp.Variable(len(cal.symbols)); threshold=cp.Variable(); excess=cp.Variable(len(returns),nonneg=True)
    cons=allocation_constraints(w,cal.symbols,cash,equity,asset_cap,commodity_cap,oil_cap)
    cons += [excess>=-returns@w-threshold]
    objective=threshold+cp.sum(excess)/(len(returns)*.05)
    problem=cp.Problem(cp.Minimize(objective),cons)
    problem.solve(solver='CLARABEL',tol_gap_abs=1e-9,tol_gap_rel=1e-9,tol_feas=1e-9)
    if problem.status!='optimal' or w.value is None:
        raise ValueError(f'Scenario risk optimizer failed: {problem.status}.')
    if max(float(np.max(np.abs(c.violation()))) for c in cons)>1e-7:
        raise ArithmeticError('Scenario optimizer constraint audit failed.')
    weights=np.maximum(w.value,0); weights/=weights.sum()
    realized=empirical_cvar(-returns@weights)
    if abs(realized-problem.value)>2e-7:
        raise ArithmeticError('Scenario tail objective audit failed.')
    return weights,dict(monthly_model_cvar=realized,scenario_count=len(returns),tail_fraction=.05,
                        training='All overlapping historical 21-session windows, no random seed',evaluation_seed=20261022,
                        objective='Gross one-month conditional loss, not a maximum drawdown or future guarantee')


def scenario_groups(result,groups=4):
    """Descriptive shape groups, with actual paths nearest each group center.

    Partitions depend on horizon/features/group count: counts are NOT posterior
    probabilities or a ranking of individual continuous trajectories.
    """
    from scipy.cluster.vq import kmeans2
    if not result.valid[:,-1].any():
        return [{'group':1,'count':len(result.wealth),'share':1.,'representative':0}],np.zeros(len(result.wealth),int)
    points=np.unique(np.maximum(1,(np.linspace(.2,1,5)*(result.nav.shape[1]-1)).astype(int)))
    features=np.c_[np.log(result.nav[:,points]),result.max_drawdown]
    scale=features.std(0); scale[scale<1e-10]=1
    z=(features-features.mean(0))/scale
    k=min(groups,len(np.unique(z.round(10),axis=0)))
    if k==1:
        labels=np.zeros(len(z),int); centers=z.mean(0,keepdims=True)
    else:
        from scipy.cluster.vq import ClusterError
        best=None
        for seed in range(12):
            try:
                c,l=kmeans2(z,k,iter=50,minit='++',seed=seed,missing='raise')
            except ClusterError:
                continue
            inertia=float(((z-c[l])**2).sum())
            if best is None or inertia<best[0]:best=(inertia,c,l)
        if best is None:raise ArithmeticError('Scenario grouping could not find nonempty clusters.')
        _,centers,labels=best
    rows=[]
    for group in np.unique(labels):
        members=np.flatnonzero(labels==group)
        representative=int(members[np.argmin(((z[members]-centers[group])**2).sum(1))])
        rows.append(dict(group=int(group),count=len(members),share=len(members)/len(z),representative=representative))
    rows.sort(key=lambda x:(-x['count'],x['representative']))
    remapped=np.zeros(len(labels),int)
    for i,row in enumerate(rows):
        remapped[labels==row['group']]=i
        row['group']=i+1
    return rows,remapped
