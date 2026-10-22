"""English multi-asset simulation workspace; budgets never enter global caches."""
from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import altair as alt
import streamlit as st
from .market_data import UNIVERSE, market_or_synthetic
from .market_models import CORE, MODELS, calibrate, simulate, minimum_variance, feasible_reference, balanced_example, path_summary, scenario_groups, scenario_min_cvar
from .planner import Budget

ROOT=Path(__file__).resolve().parents[2]
PALETTE=['#44b8ac','#6592ee','#a689dc','#daa963','#61acda','#d37b8d','#86b294','#afb1e0']


@st.cache_data(show_spinner=False)
def _market(stamp):
    return market_or_synthetic(ROOT)


def _run(cal,budget,weights,model,paths,seed,block,premium,cash_rate,cost):
    numerical_hash=hashlib.sha256(Path(__file__).with_name('market_models.py').read_bytes()).hexdigest()
    key=hashlib.sha256(json.dumps([numerical_hash,cal.symbols,cal.first_date,cal.last_date,
        hashlib.sha256(cal.excess.tobytes()+cal.covariance.tobytes()).hexdigest(),asdict(budget),
        list(weights),model,paths,seed,block,premium,cash_rate,cost],sort_keys=True).encode()).hexdigest()
    cache=st.session_state.setdefault('market_results',{})
    if key not in cache:
        # Bound per-session memory; no entered financial data in shared caches.
        if len(cache)>=5: cache.pop(next(iter(cache)))
        cache[key]=simulate(cal,budget,weights,model,paths,seed,block,premium,cash_rate,cost)
    return cache[key]


def _dollars(v):
    return ('−$' if v<0 else '$')+f'{abs(v):,.0f}'


def trajectory(result,cal,name,model,shown,groups,selected_group):
    days=result.wealth.shape[1]-1
    measures={'return':np.where(result.valid,(result.nav-1)*100,np.nan),
              'pnl':result.wealth-result.deposits,'balance':result.wealth}
    ids=list(range(min(shown,len(result.wealth))))
    ids+= [g['representative'] for g in groups if g['representative'] not in ids]
    payload=dict(days=days,shown=len(ids),total=len(result.wealth),ids=[i+1 for i in ids],
                 representatives=[ids.index(g['representative']) for g in groups],
                 highlight=ids.index(groups[selected_group]['representative']),
                 name=name,model=model,first=cal.first_date,last=cal.last_date,assets=len(cal.symbols),
                 deposits=result.deposits.round(4).tolist(),dd=result.drawdown[ids].round(5).tolist())
    for key,values in measures.items():
        q=np.full((3,days+1),np.nan)
        active=np.isfinite(values).any(0)
        if active.any():q[:,active]=np.nanquantile(values[:,active],[.05,.5,.95],axis=0)
        payload[key]={'paths':np.where(np.isfinite(values[ids]),np.round(values[ids],4),None).tolist(),
                      'q':np.where(np.isfinite(q),np.round(q,4),None).tolist()}
    raw=json.dumps(payload,allow_nan=False,separators=(',',':')).replace('<','\\u003c')
    html=(Path(__file__).parent/'assets/market_paths.html').read_text().replace('__PAYLOAD__',raw)
    st.iframe(html,height='content',tab_index=0)


def _risk_charts(result):
    frame=pd.DataFrame({'Ending balance ($)':result.wealth[:,-1],
        'Return drawdown (%)':result.max_drawdown*100})
    c=st.columns(2)
    c[0].altair_chart(alt.Chart(frame).mark_bar(color='#418eaa').encode(
        x=alt.X('Ending balance ($):Q',bin=alt.Bin(maxbins=28)),y=alt.Y('count()',title='Conditional scenario count'),tooltip=['count()']).properties(height=185),width='stretch')
    if result.valid[:,-1].any():
        c[1].altair_chart(alt.Chart(frame).mark_bar(color='#b76d65').encode(
            x=alt.X('Return drawdown (%):Q',bin=alt.Bin(maxbins=28)),y=alt.Y('count()',title='Conditional scenario count'),tooltip=['count()']).properties(height=185),width='stretch')


def _historical(adjusted,quotes,meta,synthetic):
    st.subheader('Observed markets, before simulating the future')
    symbols=st.multiselect('Markets to inspect',list(UNIVERSE),default=['SPY','GLD','USO','IEF','TLT'],key='market_inspect')
    years=st.select_slider('Visible history (years)',options=[1,3,5,10,20],value=10,key='market_history_years')
    view=st.radio('Historical chart units',['Total-return index · start = 100','Split-adjusted close ($)','Daily return (%)'],horizontal=True)
    if not symbols:return
    data=adjusted.loc[adjusted.index[-1]-pd.DateOffset(years=years):,symbols]
    if view.startswith('Total'):
        plotted=data/data.iloc[0]*100; title='Reinvested-distribution return proxy'
    elif view.startswith('Split'):
        plotted=quotes.loc[data.index,symbols]; title='Vendor split-adjusted close · not a live quote'
    else:
        plotted=data.pct_change(fill_method=None).iloc[1:]*100; title='Daily total-return proxy (%)'
    long=plotted.rename_axis('Date').reset_index().melt('Date',var_name='Fund',value_name='Value')
    st.altair_chart(alt.Chart(long).mark_line(strokeWidth=1.7).encode(x='Date:T',y=alt.Y('Value:Q',title=title,scale=alt.Scale(zero=False)),
        color=alt.Color('Fund:N',scale=alt.Scale(range=PALETTE)),tooltip=['Date:T','Fund',alt.Tooltip('Value:Q',format=',.2f')]).properties(height=350).interactive(),width='stretch')
    st.caption('Different dollar prices are not comparable returns. Total-return indices include the vendor’s reinvested-distribution convention. USO holds oil futures: roll yield, expenses and changing exposures make it different from spot crude. No futures contracts or leverage are traded here.')
    rows=[]
    for symbol in UNIVERSE:
        x=adjusted[symbol]; r=x.pct_change(fill_method=None).dropna(); one=x.iloc[-1]/x.iloc[max(0,len(x)-253)]-1
        rows.append({'Fund':symbol,'Exposure':UNIVERSE[symbol][0],
                     'Latest cached close ($)':quotes[symbol].iloc[-1],'Approx. 1y total return':one,
                     'Daily volatility · annualized':r.tail(252).std()*np.sqrt(252),
                     'Largest daily fall in common sample':r.min()})
    st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch',column_config={
        'Latest cached close ($)':st.column_config.NumberColumn(format='$%.2f'),
        **{n:st.column_config.NumberColumn(format='percent') for n in ['Approx. 1y total return','Daily volatility · annualized','Largest daily fall in common sample']}})
    st.caption(('Synthetic levels only.' if synthetic else f"Snapshot ending {meta['last_date']}; no automatic refresh and no independent second-provider validation. Common 13-fund calendar: {meta['common_rows']:,} sessions. Per-fund histories and raw hashes are recorded locally.")+' Raw provider time series are excluded from GitHub.')
    weeks=data.resample('W-FRI').last(); weeks=weeks.loc[weeks.index<=data.index[-1]]
    corr=weeks.pct_change(fill_method=None).dropna().corr().rename_axis('Fund').reset_index().melt('Fund',var_name='Other',value_name='Correlation')
    st.markdown('**Weekly co-movement**')
    st.altair_chart(alt.Chart(corr).mark_rect().encode(x='Fund:N',y='Other:N',color=alt.Color('Correlation:Q',scale=alt.Scale(domain=[-1,1],scheme='redblue')),
        tooltip=['Fund','Other',alt.Tooltip('Correlation:Q',format='.2f')]).properties(height=280),width='stretch')
    st.caption('Weekly estimates reduce some daily timing mismatches between markets; they do not remove all asynchronous-trading or regime risk.')


def render():
    st.markdown('''<style>.block-container{max-width:1250px;padding-top:3rem}h1{letter-spacing:-1.5px!important;font-size:2.7rem!important} [data-testid="stMetric"]{border:1px solid #dce4ea;border-radius:12px;padding:13px 16px;background:#fff}[data-testid="stMetricValue"] div{font-size:24px!important}</style>''',unsafe_allow_html=True)
    st.caption('ROARING RETURNS / MULTI-ASSET MARKET SIMULATOR · v0.5')
    st.title('One budget. Many possible markets.')
    st.write('Explore daily market paths, inspect the real data behind them, and see how allocation constraints change estimated risk.')
    pointer=ROOT/'data/raw/market_v5/latest.json'
    adjusted,quotes,meta,synthetic=_market(pointer.stat().st_mtime_ns if pointer.exists() else 0)
    if synthetic:
        st.warning('SYNTHETIC OFFLINE DEMO · No observed market prices are loaded. Fetch a market snapshot to calibrate on real ETFs.')
    else:
        st.caption(f"REAL DAILY SNAPSHOT · {len(UNIVERSE)} ETF proxies · {meta['first_date']}–{meta['last_date']} · {meta['common_rows']:,} shared sessions · educational scenarios, not a live trading forecast")
    page=st.radio('Explore',['Simulation','Real markets','Optimize','Model audit'],horizontal=True,key='market_view')
    with st.expander('Budget and simulation settings',expanded=False):
        with st.form('market_budget'):
            c=st.columns(4)
            initial=c[0].number_input('Investable now ($)',0.,1e7,1000.,100.,help='Money remaining after your protected cash and near-term needs.')
            monthly=c[1].number_input('Monthly addition ($)',0.,1e5,100.,25.)
            months=c[2].selectbox('Horizon (months)',[12,24,36,60,120],index=2)
            paths=c[3].selectbox('Simulated paths',[500,1000,2000],index=1)
            c=st.columns(4)
            years=c[0].selectbox('Calibration window (years)',[3,5,10,20],index=3)
            cash_rate=c[1].number_input('Cash assumption (%/year)',-5.,20.,3.,.25)/100
            premium=c[2].selectbox('Retain historical excess log mean',[0.,.25,.5,1.],index=1,format_func=lambda x:f'{x:.0%}')
            cost=c[3].number_input('Cost per buy/sale (bps)',0.,100.,2.,1.)
            st.caption('Dollar inputs are session-only. Cash is an assumption, not a quoted deposit rate. Retained mean controls log growth over cash; 0% means zero expected excess log return, not zero arithmetic excess return.')
            st.form_submit_button('Apply settings',type='primary',width='stretch')
    st.caption(f'Model budget: {_dollars(initial)} investable now + {_dollars(monthly)}/month · {months} months · {paths:,} paths · {years}y requested calibration'.replace('$',r'\$'))
    with st.expander('Asset universe and allocation constraints',expanded=page=='Optimize'):
        advanced=st.checkbox('Enable oil futures, silver, Nasdaq-100 and small-cap funds',key='market_advanced')
        allowed=list(UNIVERSE)[1:] if advanced else [s for s in CORE if s!='BIL']
        chosen=st.multiselect('Risky funds to include',allowed,default=allowed,key='market_universe_'+str(advanced))
        c=st.columns(4)
        cash=c[0].slider('Fixed cash share (%)',0,80,10,5)/100
        equity=c[1].slider('Minimum equity share (%)',0,80,40,5)/100
        asset_cap=c[2].slider('Single risky fund cap (%)',10,100,45,5)/100
        commodity_cap=c[3].slider('Combined gold / silver / oil cap (%)',0,50,20,5)/100
        st.caption('These constraints are examples you control, not a suitability assessment. Oil is additionally capped at 10% in constrained allocations; the class example does not enforce optimization caps.')
    if len(chosen)<2:
        st.info('Select at least two risky funds.');return
    symbols=('BIL',)+tuple(chosen)
    cal=calibrate(adjusted,symbols,years=years)
    c=st.columns([2,1])
    model=c[0].selectbox('Path generator',MODELS,key='market_generator')
    block=c[1].selectbox('Historical block (sessions)',[5,21,63],index=1,key='market_block')
    try:
        optimized=minimum_variance(cal,cash,equity,asset_cap,commodity_cap)
        reference=feasible_reference(cal,cash,equity,asset_cap,commodity_cap)
        tail_weights,tail_audit=scenario_min_cvar(cal,cash,equity,asset_cap,commodity_cap,
                                               premium=premium,cash_rate=cash_rate)
    except ValueError as exc:
        st.error(str(exc));return
    candidates={'Illustrative class mix':balanced_example(symbols,cash),
                'Constrained minimum variance':optimized,'Scenario downside optimizer':tail_weights,
                'Feasible equal-weight control':reference}
    allocation=st.selectbox('Allocation to explore',list(candidates),help='The optimizer and feasible control obey identical constraints. The illustrative class mix is a fixed class-weight example.')
    weights=candidates[allocation]
    if page=='Real markets':
        _historical(adjusted,quotes,meta,synthetic);return
    if page=='Optimize':
        _optimization(adjusted,cal,candidates,cash,equity,asset_cap,commodity_cap,tail_audit);return
    if page=='Model audit':
        _audit(cal,meta,synthetic,premium,cash_rate);return
    c=st.columns([2,1])
    shown=c[0].select_slider('Visible thin path IDs',options=[30,60,100,150],value=100)
    if c[1].button('Generate another random batch'):
        st.session_state.market_seed=st.session_state.get('market_seed',20261022)+1
    seed=st.session_state.get('market_seed',20261022)
    focus=st.selectbox('Simulate the portfolio or inspect one fund',['Portfolio']+list(symbols),format_func=lambda x:x if x=='Portfolio' else x+' · '+UNIVERSE[x][0])
    actual_weights=weights if focus=='Portfolio' else np.eye(len(symbols))[symbols.index(focus)]
    budget=Budget(savings=initial,emergency_reserve=0,near_term=0,monthly=monthly,months=months,goal_today=0)
    with st.spinner('Simulating correlated daily returns, cash flows and fees…'):
        result=_run(cal,budget,actual_weights,model,paths,seed,block,premium,cash_rate,cost)
    summary=path_summary(result); c=st.columns(4)
    c[0].metric('P5 ending balance',_dollars(summary['ending_p05']))
    c[1].metric('Median ending balance',_dollars(summary['ending_median']))
    c[2].metric('P95 ending balance',_dollars(summary['ending_p95']))
    c[3].metric('P95 return drawdown',f"{summary['p95_drawdown']:.1%}" if summary['p95_drawdown'] is not None else 'Not funded')
    groups,labels=scenario_groups(result)
    st.markdown('**From many paths to representative scenarios**')
    group_rows=[]
    for g in groups:
        i=g['representative']
        group_rows.append({'Scenario group':f"Group {g['group']}",'Simulations':g['count'],
            'Model-internal share (%)':100*g['share'],'Representative path ID':i+1,
            'Representative ending ($)':result.wealth[i,-1],
            'Representative cumulative return':result.nav[i,-1]-1 if result.valid[i,-1] else None,
            'Representative drawdown':result.max_drawdown[i] if result.valid[i,-1] else None})
    selected_group=st.selectbox('Highlight a representative scenario',list(range(len(groups))),
        format_func=lambda i:f"Group {i+1} · approximately {groups[i]['share']:.0%} of simulated paths"+(' · largest group' if i==0 else ''))
    trajectory(result,cal,allocation if focus=='Portfolio' else focus+' fund scenario',model,shown,groups,selected_group)
    st.caption('The bold representative is an actual simulation nearest its group’s center. Group 1 contains the most simulations under this model. Group shares depend on the model, horizon and grouping rule; they are not calibrated real-world probabilities or a uniquely most-likely future path.')
    st.caption('Shape grouping uses log returns at 20/40/60/80/100% of the horizon plus maximum drawdown, standardized across simulations. Four-group k-means uses the best of 12 fixed initializations; shares are rounded, and changing the grouping rule can change the largest group.')
    st.caption(f'Simulation seed {seed}. Different random batches can shift group shares by several percentage points. Single-fund inspection ignores portfolio caps to isolate that fund’s risk; it is not a proposed allocation.')
    with st.expander('Scenario group counts and representative outcomes'):
        st.dataframe(pd.DataFrame(group_rows),hide_index=True,width='stretch',column_config={
            'Model-internal share (%)':st.column_config.NumberColumn(format='%.0f%%'),
            **{n:st.column_config.NumberColumn(format='percent') for n in ['Representative cumulative return','Representative drawdown']}})
    st.caption('Conditional quantiles describe this model only. GBM has normal log shocks, constant covariance and no volatility clustering. Historical blocks preserve some observed joint tails and clustering, but cannot generate an unseen type of crisis. Cash paths are deterministic by assumption.')
    _risk_charts(result)
    st.markdown('**Allocation behind these paths**')
    allocation_frame=pd.DataFrame({'Fund':symbols,'Weight':actual_weights,'Exposure':[UNIVERSE[s][0] for s in symbols]})
    st.altair_chart(alt.Chart(allocation_frame).mark_bar(color='#439d99').encode(x='Fund:N',y=alt.Y('Weight:Q',axis=alt.Axis(format='%')),tooltip=['Fund','Exposure',alt.Tooltip('Weight:Q',format='.1%')]).properties(height=160),width='stretch')
    with st.expander('Compare models and the same-constraint control'):
        if st.button('Run model comparison',key='market_compare'):
            rows=[]
            with st.spinner('Replaying common random paths within each model…'):
                for generator in MODELS:
                    for label,a in [('Selected allocation',actual_weights),('Feasible equal-weight control',reference)]:
                        r=_run(cal,budget,a,generator,paths,seed,block,premium,cash_rate,cost)
                        rows.append({'Model':generator,'Allocation':label,**path_summary(r)})
            st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
            st.caption('Within each model, allocations use the identical asset-return draws and deposits. Different generators represent different assumptions, not competing calibrated probabilities. If inspecting a single fund, the control has different exposure.')
    st.download_button('Download my local model summary',json.dumps(dict(budget=asdict(budget),
        snapshot=meta.get('cutoff',meta['last_date']),model=model,calibration=dict(first=cal.first_date,last=cal.last_date,observations=cal.observations),
        assumptions=dict(retained_excess_log_mean=premium,cash_rate=cash_rate,block=block,paths=paths,seed=seed,cost_bps=cost),
        weights=dict(zip(symbols,map(float,actual_weights))),summary=summary,scenario_groups=group_rows),indent=2),file_name='my-market-scenarios.json',mime='application/json')
    st.caption('Educational research prototype · nominal USD · fractional holdings · monthly net rebalancing · no taxes, intraday liquidity, broker fills or investment guarantee. More curves do not mean more independent data.')


def _optimization(prices,cal,candidates,cash,equity,cap,commodity,tail_audit):
    st.subheader('Allocate across real market exposures')
    frame=pd.DataFrame({'Fund':cal.symbols,**{n:a for n,a in candidates.items()}})
    long=frame.melt('Fund',var_name='Allocation',value_name='Weight')
    st.altair_chart(alt.Chart(long).mark_bar().encode(x='Fund:N',xOffset='Allocation:N',y=alt.Y('Weight:Q',axis=alt.Axis(format='%')),
        color=alt.Color('Allocation:N',scale=alt.Scale(range=PALETTE)),tooltip=['Fund','Allocation',alt.Tooltip('Weight:Q',format='.1%')]).properties(height=260),width='stretch')
    st.dataframe(frame,hide_index=True,width='stretch',column_config={n:st.column_config.NumberColumn(format='percent') for n in candidates})
    optimized=candidates['Constrained minimum variance']
    active=[]
    if abs(sum(w for s,w in zip(cal.symbols,optimized) if UNIVERSE[s][1]=='Equities')-equity)<1e-5:
        active.append('equity minimum')
    active += [s+' at fund cap' for s,w in zip(cal.symbols[1:],optimized[1:]) if abs(w-cap)<1e-5]
    active += [s+' at zero bound' for s,w in zip(cal.symbols[1:],optimized[1:]) if w<1e-6]
    st.caption('Binding minimum-variance constraints: '+(', '.join(active) or 'cash equality only')+'.')
    vols=[{'Allocation':n,'Estimated annual volatility':np.sqrt(a[1:]@cal.covariance@a[1:])} for n,a in candidates.items()]
    st.dataframe(pd.DataFrame(vols),hide_index=True,width='stretch',column_config={'Estimated annual volatility':st.column_config.NumberColumn(format='percent')})
    st.caption('The minimum-variance objective uses completed-week sample covariance, with only a minimal eigenvalue floor if needed for numerical conditioning. It does not mechanically reduce off-diagonal correlations. Cash is fixed and treated as deterministic. No expected return is maximized; the feasible control is the closest equal-risky-capital mix under the very same constraints.')
    st.write(f"The scenario downside optimizer minimizes average loss in the worst 5% of all {tail_audit['scenario_count']:,} overlapping 21-session historical windows, shifted to the stated cash/log-growth assumptions. There is no random training-window selection. It considers many outcomes rather than betting on one representative line. These overlapping windows and the plotted simulations still rely on the same historical calibration; they are not independent evidence.")
    with st.expander('Scenario optimizer audit'):
        st.latex(r'\min_{w,\eta,u}\ \eta+\frac{1}{0.05N}\sum_s u_s,\quad u_s\ge -R_s^Tw-\eta,\ u_s\ge0')
        st.json(tail_audit)
    curve=[]
    for floor in np.linspace(0,min(.85,1-cash),13):
        try:
            a=minimum_variance(cal,cash,float(floor),cap,commodity)
            curve.append({'Minimum equity share':floor,'Estimated annual volatility':np.sqrt(a[1:]@cal.covariance@a[1:])})
        except ValueError:pass
    st.markdown('**Equity exposure versus minimum estimated risk · cash held fixed**')
    if curve:
        st.altair_chart(alt.Chart(pd.DataFrame(curve)).mark_line(point=True,color='#258c99').encode(x=alt.X('Minimum equity share:Q',axis=alt.Axis(format='%')),y=alt.Y('Estimated annual volatility:Q',axis=alt.Axis(format='%')),tooltip=[alt.Tooltip('Minimum equity share:Q',format='.0%'),alt.Tooltip('Estimated annual volatility:Q',format='.1%')]).properties(height=220),width='stretch')
    st.caption(f'{len(curve)}/13 exposure settings are feasible under the selected caps; infeasible points are not plotted. This is a constraint/risk curve, not a forecast return frontier.')
    st.markdown('**Weight stability across estimation windows**')
    rows=[]
    for years in [3,5,10,20]:
        fitted=calibrate(prices,cal.symbols,years=years)
        a=minimum_variance(fitted,cash,equity,cap,commodity)
        rows.extend({'Window':f'{years}y requested','Fund':s,'Weight':float(w)} for s,w in zip(cal.symbols,a))
    st.altair_chart(alt.Chart(pd.DataFrame(rows)).mark_bar().encode(x='Window:N',y=alt.Y('Weight:Q',axis=alt.Axis(format='%')),
        color=alt.Color('Fund:N',scale=alt.Scale(range=PALETTE)),tooltip=['Window','Fund',alt.Tooltip('Weight:Q',format='.1%')]).properties(height=240),width='stretch')
    st.caption('A 20-year request uses only available common history. These overlapping windows illustrate estimation sensitivity, not independent tests. A low estimated variance does not establish a suitable portfolio or bound a loss.')
    with st.expander('Optimization formula and constraints'):
        st.latex(r'\min_w\ w_{risk}^{T}\widehat\Sigma_{weekly}\,w_{risk}\quad\mathrm{s.t.}\quad\mathbf1^Tw=1,\ w\ge0')
        st.json(dict(cash_fixed=cash,equity_minimum=equity,single_risky_cap=cap,commodity_cap=commodity,oil_cap=.1,
                     covariance_observations=cal.weekly_observations,covariance_through=cal.weekly_last,eigenvalue_floor=cal.eigenvalue_floor,solver='Clarabel'))


def _audit(cal,meta,synthetic,premium,cash_rate):
    st.subheader('What the model learns — and what it assumes')
    st.write(f'Daily calibration: {cal.first_date}–{cal.last_date}, {cal.observations:,} return observations. Covariance: {cal.weekly_observations} completed weekly returns through {cal.weekly_last}.')
    st.latex(r'\log(S_{t+\Delta}/S_t)=m\Delta+L\sqrt{\Delta}Z,\quad LL^T=\widehat\Sigma,\ Z\sim N(0,I)')
    st.caption('Here m is an annual log-growth rate, not an arithmetic expected return. For GBM, arithmetic drift is m + diagonal(Σ)/2; subtracting half the variance a second time would be wrong. Retained excess log means anchor all assets to the same cash assumption.')
    annual_mean=np.log1p(cash_rate)+premium*cal.daily_mean*252
    rows=[]
    for i,s in enumerate(cal.symbols[1:]):
        x=cal.excess[:,i]
        rows.append({'Fund':s,'Assumed annual log growth':annual_mean[i],
            'Weekly-based annual volatility':np.sqrt(cal.covariance[i,i]),
            'Observed daily excess kurtosis':float(pd.Series(x).kurt()),
            'Observed daily 1% quantile':float(np.quantile(x,.01)),
            'Gaussian daily 1% quantile':float(x.mean()-2.326347874*np.sqrt(cal.covariance[i,i]/252))})
    st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
    def correlation(cov):
        sd=np.sqrt(np.diag(cov));return cov/np.outer(sd,sd)
    raw_corr=correlation(cal.raw_covariance);model_corr=correlation(cal.covariance)
    differences=[]
    for i in range(len(cal.symbols)-1):
        for j in range(i):
            differences.append({'Pair':cal.symbols[i+1]+' / '+cal.symbols[j+1],
                'Raw weekly correlation':raw_corr[i,j],'Model correlation':model_corr[i,j],
                'Absolute conditioning change':abs(raw_corr[i,j]-model_corr[i,j])})
    st.markdown('**Raw versus conditioned model correlations**')
    st.dataframe(pd.DataFrame(differences),hide_index=True,width='stretch')
    st.write('The normal model has no volatility clustering or structural breaks. Joint blocks preserve some historical serial dependence and tail co-movement. Weekly covariance reduces some asynchronous-price effects but is not identical to the covariance of daily resampling. These differences are intentional model assumptions, not predictive improvements.')
    st.write('The 13 assets are selected retrospectively, and the common inception date limits crisis diversity. Additional assets do not create additional independent historical dates. There is no untouched holdout, fitted alpha model, parameter search or probability-calibration claim. Window-dependent log-growth estimates may put some bond funds below the assumed cash growth; that is an assumption inherited from that window, not a forecast that bonds must underperform cash.')
    st.write('Future grid: exactly 21 sessions per modeled month, 252 per year; actual holidays vary. Monthly contributions arrive after that month’s return, followed by a fee-aware net trade. Performance excludes external deposits. BIL uncertainty is replaced by a deterministic future cash-rate assumption; observed-market charts retain actual BIL returns.')
    st.markdown('Sources: [USCF oil-fund disclosures](https://www.uscfinvestments.com/disclosures), [CVX risk models](https://www.cvxgrp.org/cvxrisk/models/), [multi-period convex trading](https://web.stanford.edu/~boyd/papers/cvx_portfolio.html). Implementations here are original and simplified; they are not reproductions of those papers or libraries.')
    with st.expander('Snapshot provenance'):
        st.json(meta)
