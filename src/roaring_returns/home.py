"""Beginner-first, English budget and scenario interface."""
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
import pandas as pd
import altair as alt
import streamlit as st
from .planner import Budget, PlanningSettings, EXAMPLES, ASSET_NAMES, monthly_returns, sampled_paths, simulate_mix, describe_result, replay_daily
from .planner_data import planner_market, planner_risky_history
from .planning_models import risk_balance, performance_frame, dollar_units
from .planning_scenarios import SCENARIOS, month_library, sampled_months, simulate_daily_scenarios
from .planning_views import performance_metrics, attribution, future_charts, scenario_row, show_comparison

ROOT = Path(__file__).resolve().parents[2]
MIX_COLORS = ["#8d9dad", "#168a94", "#bd963f", "#526b94"]
PRESETS = {
    "Student starter": dict(savings=3000., reserve=1500., soon=500., monthly=100., months=36, goal=6000., dip=300.),
    "First paycheck": dict(savings=8000., reserve=4000., soon=1000., monthly=350., months=60, goal=25000., dip=1200.),
    "Money needed soon": dict(savings=3000., reserve=2000., soon=1000., monthly=100., months=12, goal=0., dip=100.),
}


def _set_preset(name):
    for key, value in PRESETS[name].items():
        st.session_state[f"budget_{key}"] = value


@st.cache_data(show_spinner=False)
def _market(signature):
    return planner_market(ROOT)


@st.cache_data(show_spinner=False)
def _risk_history(signature):
    return planner_risky_history(ROOT)


def _money(value):
    return f"${value:,.0f}" if value >= 0 else f"−${abs(value):,.0f}"


def _animate(result, reference, settings, real, note):
    displayed = dollar_units(result,settings.inflation,real)
    reference_display = dollar_units(reference,settings.inflation,real)
    payload = {"values": displayed['wealth'][0].round(4).tolist(),
               "deposits": displayed['deposits'].round(4).tolist(),
               "holdings": displayed['holdings'].round(4).tolist(),
               "fees": displayed['fees'][0].round(6).tolist(), "real":real,
               "drawdowns": [float(v) if ok else None for v, ok in zip(result.drawdown_path[0], result.return_valid[0])],
               "nav": [float(v) if ok else None for v, ok in zip(result.nav[0], result.return_valid[0])],
               "referenceValues": reference_display['wealth'][0].round(4).tolist(),
               "referenceNav": [float(v) if ok else None for v, ok in zip(reference.nav[0], reference.return_valid[0])],
               "note": note, "unit": result.period_unit, "dates": result.dates}
    template = (Path(__file__).parent/"assets/journey.html").read_text()
    st.iframe(template.replace("__DATA__", json.dumps(payload, allow_nan=False).replace("</", "<\\/")), height="content", tab_index=0)


def _bundle(prices, meta, budget, settings, mixes, assumption, recent):
    code_hash = sha256(b''.join((Path(__file__).parent/name).read_bytes() for name in
        ['planner.py','planning_scenarios.py','planning_models.py'])).hexdigest()
    key = sha256(json.dumps({"engine":code_hash, "budget":asdict(budget), "settings":asdict(settings),
        "mixes":{k:list(v) for k,v in mixes.items()}, "assumption":assumption, "recent":recent,
        "data":meta["processed_sha256"]},sort_keys=True).encode()).hexdigest()
    if st.session_state.get('planner_bundle_key') != key:
        library = month_library(prices,recent)
        indexes = sampled_months(library,budget.months,settings)
        results = {name:simulate_daily_scenarios(library,budget,a,settings,assumption,indexes) for name,a in mixes.items()}
        st.session_state.planner_bundle = (library,indexes,results)
        st.session_state.planner_bundle_key = key
    return st.session_state.planner_bundle


def _allocation(weights):
    frame = pd.DataFrame({'Asset':ASSET_NAMES,'Weight':weights,'Order':range(4)})
    st.altair_chart(alt.Chart(frame).mark_bar(size=24).encode(x=alt.X('Weight:Q',axis=None),
        color=alt.Color('Asset:N',scale=alt.Scale(domain=list(ASSET_NAMES),range=MIX_COLORS),legend=None),order='Order:Q',
        tooltip=['Asset',alt.Tooltip('Weight:Q',format='.1%')]).properties(height=30),width='stretch')
    legend=''.join(f'<span style="white-space:nowrap"><span style="color:{c}">●</span> {n} <b>{w:.1%}</b></span>' for n,c,w in zip(ASSET_NAMES,MIX_COLORS,weights))
    st.markdown(f'<div style="display:flex;gap:10px 20px;flex-wrap:wrap;font-size:12px;margin-bottom:12px">{legend}</div>',unsafe_allow_html=True)


def render():
    st.markdown("""<style>
    .block-container{max-width:1180px;padding-top:3.8rem;padding-bottom:3rem}
    h1{font-size:2.7rem!important;line-height:1.1!important;letter-spacing:-1.5px!important;font-weight:650!important}
    h2{font-size:1.75rem!important;letter-spacing:-.5px!important}h3{font-size:1.22rem!important;letter-spacing:-.3px!important}
    .rr-kicker{font-size:10px;letter-spacing:1.8px;color:#64758a;font-weight:700;margin:15px 0}
    .rr-lead{font-size:17px;line-height:1.65;color:#65758a;max-width:760px;margin:15px 0 20px}
    [data-testid="stMetric"]{background:white;border:1px solid #e0e6eb;border-radius:12px;padding:16px 18px}
    [data-testid="stMetricValue"] div{font-size:24px!important}
    [data-baseweb="tab-list"]{gap:25px;border-bottom:1px solid #dce3e9;margin-top:12px;margin-bottom:16px}
    [data-baseweb="tab"]{font-weight:600!important}div[data-testid="stForm"]{background:#fff;border:1px solid #e0e6eb;border-radius:16px;padding:22px}
    @media(max-width:700px){h1{font-size:2.1rem!important}.rr-lead{font-size:15px}[data-testid="stMetric"]{padding:12px}[data-testid="stMetricValue"] div{font-size:20px!important}}
    </style>""", unsafe_allow_html=True)
    st.markdown('<div class="rr-kicker">◈ ROARING RETURNS / START WITH YOUR BUDGET</div>', unsafe_allow_html=True)
    st.title("Small budget. Clearer choices.")
    st.markdown('<div class="rr-lead">Set aside money you need. Compare simple investment examples. See what a difficult market could feel like before deciding.</div>', unsafe_allow_html=True)
    st.caption("Educational scenario explorer · USD · No brokerage connection · Entries stay in this app session, without a saved profile.")
    path = ROOT/"data/raw/planner_v3/manifest.json"
    prices, meta, synthetic = _market(path.stat().st_mtime_ns if path.exists() else 0)
    history_for_defaults = monthly_returns(prices)
    sample_cash_rate = float(np.expm1(12*np.log1p(history_for_defaults.iloc[:, 3]).mean()))
    st.caption("Sample budgets · Made-up numbers, not suggested reserve amounts or investment plans.")
    presets = st.columns(3)
    for col, name in zip(presets, PRESETS):
        col.button(name, key=f"preset_{name}", on_click=_set_preset, args=(name,), width="stretch")
    defaults = dict(savings=5000., reserve=2000., soon=1000., monthly=200., months=60, goal=15000., dip=1000.)
    for key, value in defaults.items():
        st.session_state.setdefault(f"budget_{key}", value)
    st.caption("Start with a sample above, or open the budget editor to enter your own numbers.")
    with st.expander("Edit your budget and assumptions", expanded=False):
        with st.form("beginner_budget"):
            st.subheader("1. Keep everyday money separate")
            c = st.columns(3)
            c[0].number_input("Savings available now ($)", min_value=0., max_value=10000000., step=100., key="budget_savings")
            c[1].number_input("Emergency cash to protect ($)", min_value=0., max_value=10000000., step=100., key="budget_reserve",
                                help="Your chosen cash reserve, not an amount prescribed by this tool.")
            c[2].number_input("Money needed soon ($)", min_value=0., max_value=10000000., step=100., key="budget_soon",
                                help="Additional to the reserve: tuition, rent, moving costs or other near-term spending. Do not count the same money twice.")
            st.caption("The model sets both protected amounts aside. Monthly money first fills any shortfall. Consider debt payments before choosing a sustainable monthly amount.")
            st.subheader("2. Give this investment pot a time frame")
            c = st.columns(3)
            c[0].number_input("Monthly amount after bills ($)", min_value=0., max_value=100000., step=25., key="budget_monthly")
            c[1].selectbox("When might you need this money?", [6, 12, 36, 60, 120], key="budget_months",
                           format_func=lambda x: f"{x} months" if x < 12 else f"{x//12} year"+("s" if x > 12 else ""))
            c[2].number_input("A temporary dip I could tolerate ($)", min_value=0., max_value=10000000., step=100., key="budget_dip",
                              help="Used only to flag examples crossing your own comfort line. It does not set a loss limit or select investments.")
            with st.expander("Optional goal and model assumptions"):
                st.number_input("Goal for this pot, in today's dollars ($; 0 = none)", min_value=0., max_value=100000000., step=500., key="budget_goal")
                st.caption("The goal excludes protected cash. Monthly contributions stay fixed in nominal dollars.")
                a = st.columns(2)
                cash_rate = a[0].number_input("Cash interest assumption (%/year)", min_value=-5., max_value=20., value=round(100*sample_cash_rate, 4), step=.5,
                    help="Starts at the snapshot's annualized geometric BIL return. This constant future assumption is not a current bank rate or guaranteed product. Raising it raises all modeled asset log returns equally, under a constant-premium assumption.")/100
                inflation = a[1].number_input("Inflation assumption (%/year)", min_value=0., max_value=20., value=2.5, step=.5)/100
                haircut = 0.  # Return assumptions are compared explicitly in Possible paths.
                fees = st.slider("Illustrative cost per purchase/sale (basis points)", 0., 25., 2., 1.)
                rule = st.selectbox("Monthly rebalancing illustration", ["Cash first, then 5pp band", "Contributions only"])
            st.form_submit_button("Compare my scenarios", type="primary", width="stretch")
    budget = Budget(st.session_state.budget_savings, st.session_state.budget_reserve, st.session_state.budget_soon,
                    st.session_state.budget_monthly, st.session_state.budget_months, st.session_state.budget_goal, st.session_state.budget_dip)
    settings = PlanningSettings(cash_rate=cash_rate, inflation=inflation, return_haircut=haircut, cost_bps=fees,
                               rebalancing="cash_first_band" if rule.startswith("Cash first") else "contributions_only")
    budget.validate(); settings.validate()
    cols = st.columns(3)
    cols[0].metric("Available to model", _money(budget.initial))
    cols[1].metric("Protected outside this pot", _money(budget.protected_now))
    cols[2].metric("Monthly amount", _money(budget.monthly))
    if budget.reserve_gap > 0:
        st.info(f"Your protected-cash target is short by {_money(budget.reserve_gap)}. In this illustration, monthly money fills that gap before entering the investment pot. Protected cash is excluded from all charts below.")
    if budget.months <= 12:
        st.info("Short time frame: market losses may occur just when you need the money. Start with the stress replay and savings reference.")
    if synthetic:
        st.info("SYNTHETIC DEMO · Artificial market paths, not historical SPY/GLD/IEF data. No historical replay or real-market prediction is shown.")
    else:
        st.caption(f"Historical input: SPY / GLD / IEF + BIL cash proxy · {meta['first_session']}–{meta['last_session']} · cached total-return proxies, not live prices.")
    # Widgets later in the page update these keys before the next script run.
    model_cash = st.session_state.get('planner_model_cash',20)/100
    cov_window = st.session_state.get('planner_cov_window',756)
    block = st.session_state.get('planner_block',6)
    assumption = st.session_state.get('planner_assumption',SCENARIOS[0])
    recent = 120 if st.session_state.get('planner_history','Full sample') == 'Last 10 years' else None
    settings = replace(settings,block_months=block)
    mixes = dict(EXAMPLES)
    model = None
    risk_prices = prices.iloc[:,:3] if synthetic else _risk_history(meta['processed_sha256'])
    try:
        model = risk_balance(risk_prices,prices.index[-1],model_cash,cov_window)
        mixes['Risk-balanced candidate'] = tuple(model.weights)
        mixes['Same cash / equal risky weights'] = tuple(np.r_[model_cash,np.full(3,(1-model_cash)/3)])
    except (ValueError,ArithmeticError) as exc:
        st.error(f'Risk balancing unavailable: {exc}')
    if st.session_state.get('planner_custom',False):
        custom = np.array([st.session_state.get('custom_cash',20),st.session_state.get('custom_stocks',40),st.session_state.get('custom_gold',15)],float)/100
        if custom.sum() <= 1:
            mixes['Your mix'] = tuple(np.r_[custom,1-custom.sum()])
        else:
            st.error('Custom cash + stocks + gold exceed 100%. Reduce a weight in Build & optimize.')
    with st.spinner('Valuing daily scenarios and checking account performance…'):
        library,indexes,results = _bundle(prices,meta,budget,settings,mixes,assumption,recent)
    st.subheader('Choose an example or model candidate')
    selected = st.radio('Examples and candidates (choose one)',list(mixes),index=0,horizontal=True)
    result,weights = results[selected],mixes[selected]
    _allocation(weights)
    st.caption('Cash is inside this pot; protected money stays outside. SPY is a US large-cap proxy; gold and the 7–10y Treasury fund can lose value. Risk-balanced weights above are fitted using data through '+str(prices.index[-1].date())+'.')
    tabs = st.tabs(['Stress first','Possible paths','Build & optimize','Compare choices','Inside the model'])
    with tabs[0]:
        st.subheader('Separate saving money from investment performance')
        historical_mixes = dict(mixes)
        if not synthetic:
            episodes = {'2022 · rising rates':('2022-01-01','2022-12-31'),
                        '2020 · sudden sell-off':('2020-02-01','2020-04-30'),
                        '2008–09 · market stress':('2008-09-01','2009-03-31')}
            episode=st.selectbox('Replay a historical pattern',list(episodes))
            start,end=episodes[episode]
            if model is not None:
                # Estimate this candidate strictly before the event. It is held
                # as a fixed target during the replay, with monthly rebalancing.
                pre_date=prices.index[prices.index < pd.Timestamp(start)][-1]
                event_model=risk_balance(risk_prices,pre_date,model_cash,cov_window)
                historical_mixes['Risk-balanced candidate']=tuple(event_model.weights)
            stress_results={n:replay_daily(prices,budget,a,settings,start,end) for n,a in historical_mixes.items()}
            active=stress_results[selected]
            st.caption(f'Daily-close historical replay: {active.dates[0]} to {active.dates[-1]}. Budget and trades are hypothetical; asset and BIL cash-proxy returns are observed. Intraday lows are omitted.')
            if selected == 'Risk-balanced candidate':
                st.caption(f'Pre-event covariance only: {event_model.first_date}–{event_model.last_date}, {event_model.observations} returns. No post-event prices determine these weights. The target stays fixed during the event.')
                _allocation(historical_mixes[selected])
        else:
            episode='Designed downturn'
            stress=np.array([[[-.20,-.04,-.08],[-.10,-.02,-.04],[.05,.02,.01]]])[:,:budget.months]
            stress_results={n:simulate_mix(stress,budget,a,settings) for n,a in historical_mixes.items()}
            active=stress_results[selected]
            st.caption('Synthetic demonstration: designed monthly shocks, not historical observations or daily risk estimates.')
        reference=stress_results['Savings reference']
        performance_metrics(active,reference)
        _animate(active,reference,settings,False,episode+' · '+selected+'.')
        if active.maximum_dip[0] > budget.comfortable_dip+1e-7:
            st.warning(f'The account fell by {_money(active.maximum_dip[0])} from its deposit-adjusted high-water mark, above your {_money(budget.comfortable_dip)} comparison line.'.replace('$',r'\$'))
        else:
            st.caption(f'Largest deposit-adjusted dollar dip: {_money(active.maximum_dip[0])}. That amount depends on when money was invested; the percentage return drawdown above provides a second view.'.replace('$',r'\$'))
        replay_rows=[]
        for name,r in stress_results.items():
            valid=bool(r.return_valid[0,-1])
            replay_rows.append({'Example':name,'Deposits ($)':r.contributed[-1],'Net P&L ($)':r.wealth[0,-1]-r.contributed[-1],
                'Cumulative return':r.nav[0,-1]-1 if valid else None,'Return drawdown':r.max_drawdown[0] if valid else None,
                'Dollar dip ($)':r.maximum_dip[0],'Fees ($)':r.fees[0]})
        st.dataframe(pd.DataFrame(replay_rows),hide_index=True,width='stretch',column_config={
            **{n:st.column_config.NumberColumn(format='$%.2f') for n in ['Deposits ($)','Net P&L ($)','Dollar dip ($)','Fees ($)']},
            **{n:st.column_config.NumberColumn(format='percent') for n in ['Cumulative return','Return drawdown']}})
        with st.expander('Explain every dollar in this replay'):
            attribution(active)
        if not synthetic:
            with st.expander('Underlying market returns · advanced benchmark'):
                event=prices.loc[active.dates[0]:active.dates[-1]]
                market=(event/event.iloc[0]-1).rename(columns={'BIL':'Cash proxy'})
                frame=market.reset_index().melt(id_vars=market.index.name or 'index',var_name='Asset',value_name='Return')
                date_col=frame.columns[0]
                st.altair_chart(alt.Chart(frame).mark_line().encode(x=alt.X(date_col+':T',title='Date'),y=alt.Y('Return:Q',axis=alt.Axis(format='%')),color='Asset:N').properties(height=220),width='stretch')
                st.caption('These are unlevered asset total-return proxies, with no account deposits. The stock series is context rather than an objective to beat.')
    with tabs[1]:
        st.subheader('How much does the answer depend on the model?')
        c=st.columns(3)
        c[0].selectbox('Excess-return assumption',list(SCENARIOS),key='planner_assumption')
        c[1].selectbox('Contiguous block length (months)',[3,6,12],index=1,key='planner_block')
        c[2].selectbox('Resampling input window',['Full sample','Last 10 years'],key='planner_history')
        real=st.toggle("Show today's purchasing power",value=True)
        stats=describe_result(result,budget,settings)
        c=st.columns(3)
        c[0].metric('Middle ending · today’s dollars',_money(stats['ending_middle_today']))
        c[1].metric('Median net P&L · nominal dollars',_money(stats['median_net_pnl']))
        c[2].metric('90th-percentile return drawdown',f"{stats['drawdown_90']:.1%}" if stats['drawdown_90'] is not None else 'Not yet funded')
        future_charts(result,budget,settings,real)
        if budget.goal_today > 0:
            reached=int(np.sum(result.wealth[:,-1]/(1+settings.inflation)**(budget.months/12)>=budget.goal_today))
            st.caption(f'Your goal for this pot: {_money(budget.goal_today)} in today’s dollars. {reached}/{settings.paths} conditional scenarios ended at or above it. This is a model count, not a real-world success probability.'.replace('$',r'\$'))
        st.caption(f'{settings.paths} paths from {len(library.counts)} months ({library.labels[0]}–{library.labels[-1]}). Whole-month blocks preserve observed daily order within each month; blocks do not wrap across the end of the sample. Cash assumption: {settings.cash_rate:.2%}/year; inflation assumption: {settings.inflation:.2%}/year.')
        st.markdown('**Three return assumptions, same sampled months**')
        scenarios=[]
        for mode in SCENARIOS:
            candidate=result if mode==assumption else simulate_daily_scenarios(library,budget,weights,settings,mode,indexes)
            scenarios.append(scenario_row(mode,candidate,budget,settings))
        show_comparison(scenarios)
        st.caption('Lower excess returns subtracts 2 log percentage points/year. Zero average excess returns removes the expected excess log return at each block position, correcting for the unequal sampling of boundary months. Finite sampled paths need not average exactly zero. These are alternative assumptions, not calibrated likelihoods. Fees can make the zero-premium case lose money.')
        with st.expander('Block length and sample-window sensitivity',expanded=True):
            check_rows=[]
            for window,limit in [('Full sample',None),('Last 10 years',120)]:
                check_library=month_library(prices,limit)
                for length in [3,6,12]:
                    cfg=replace(settings,block_months=length)
                    checked=simulate_daily_scenarios(check_library,budget,weights,cfg,assumption)
                    row=scenario_row(f'{window} / {length}m blocks',checked,budget,cfg)
                    row['Input months']=len(check_library.counts)
                    check_rows.append(row)
            show_comparison(check_rows)
            st.caption('The allocation is held fixed in this check. Different block lengths/sample windows probe model dependence; they do not create a new holdout or determine which setting is true.')
        with st.expander('Inspect one fixed-seed daily path'):
            _animate(result.sample_path,results['Savings reference'].sample_path,settings,real,'First sampled path; not the median or a selected winner. Dollar views follow the purchasing-power switch; return percentages are nominal.')
        extra=st.slider('What if I could set aside extra each month? ($)',0,500,0,25)
        if extra:
            from dataclasses import replace as dc_replace
            # Keep reserve-gap funding exact when the total monthly budget changes.
            changed=dc_replace(budget,monthly=budget.monthly+extra)
            alternative=simulate_daily_scenarios(library,changed,weights,settings,assumption,indexes)
            delta=describe_result(alternative,changed,settings)['ending_middle_today']-stats['ending_middle_today']
            st.write(f'Extra {_money(extra)}/month changes the middle ending scenario by {_money(delta)} in today’s dollars, on the same paths. This includes the additional deposits; it is not extra investment return.'.replace('$',r'\$'))
    with tabs[2]:
        st.subheader('Solve a risk-balanced allocation')
        st.write('Choose the cash share yourself. The solver divides the remaining stock/gold/bond portion so each contributes one third of its estimated variance. It balances a risk estimate; it does not maximize expected wealth or establish suitability.')
        c=st.columns(2)
        c[0].slider('Cash share of model candidate (%)',0,100,20,5,key='planner_model_cash')
        c[1].selectbox('Covariance lookback (sessions)',[252,756,1260],index=1,key='planner_cov_window',format_func=lambda x:f'{x} sessions · about {x//252} {"year" if x==252 else "years"}')
        if model is not None:
            frame=pd.DataFrame({'Risky asset':ASSET_NAMES[1:],'Capital share within risky slice':model.risky_weights,'Share of estimated variance':model.risk_contributions})
            st.dataframe(frame,hide_index=True,width='stretch',column_config={n:st.column_config.NumberColumn(format='percent') for n in frame if n!='Risky asset'})
            equal=np.ones(3)/3
            eq_vol=(1-model_cash)*np.sqrt(equal@model.covariance@equal)
            st.caption(f'Future scenario candidate estimated using {model.observations} pre-decision daily returns: {model.first_date}–{model.last_date}. Covariance is 25% shrunk toward its diagonal. Estimated annual volatility: candidate {model.annual_volatility:.1%}; equal-capital risky slice at the same cash share {eq_vol:.1%}. Neither estimate is a future loss limit.')
            frontier=pd.DataFrame({'Cash share':np.linspace(0,1,21)})
            risky_vol=np.sqrt(model.risky_weights@model.covariance@model.risky_weights)
            frontier['Estimated annual volatility']=(1-frontier['Cash share'])*risky_vol
            st.altair_chart(alt.Chart(frontier).mark_line(point=True,color='#168a94').encode(x=alt.X('Cash share:Q',axis=alt.Axis(format='%')),y=alt.Y('Estimated annual volatility:Q',axis=alt.Axis(format='%')),tooltip=[alt.Tooltip('Cash share:Q',format='.0%'),alt.Tooltip('Estimated annual volatility:Q',format='.1%')]).properties(height=210),width='stretch')
            st.caption('This trade-off varies only cash exposure around a fixed risky mix. Cash is treated as constant for this volatility estimate; the historical cash proxy can fluctuate. No return forecast is optimized. Same cash / equal risky weights is included as the control for how the risky slice is constructed. The covariance-fitting period overlaps the historical resampling input: future scenarios are exploratory, not held-out evidence.')
            with st.expander('Solver and mathematical audit'):
                st.latex(r'\min_{x>0}\;\frac12x^T\Sigma x-\frac13\sum_{i=1}^3\log x_i,\quad w_{risk}=x/(1^Tx)')
                st.json({'solver':model.solver,'maximum_first_order_error':model.kkt_error,'minimum_covariance_eigenvalue':float(np.linalg.eigvalsh(model.covariance).min()),'estimated_risk_shares':model.risk_contributions.tolist()})
        st.checkbox('Include my own allocation',key='planner_custom')
        c=st.columns(3)
        c[0].slider('My cash (%)',0,100,20,5,key='custom_cash')
        c[1].slider('My stocks (%)',0,100,40,5,key='custom_stocks')
        c[2].slider('My gold (%)',0,100,15,5,key='custom_gold')
        remaining=100-sum(st.session_state[k] for k in ['custom_cash','custom_stocks','custom_gold'])
        if remaining>=0:
            st.caption(f'Remaining {remaining}% goes to the 7–10y Treasury fund. Enable the checkbox to add Your mix to the comparison selector.')
        else:
            st.error('Custom shares exceed 100%; this allocation is not included.')
    with tabs[3]:
        st.subheader('Identical cash flows and scenarios for every candidate')
        show_comparison([scenario_row(n,r,budget,settings) for n,r in results.items()])
        st.caption(f'Cumulative returns cover the full {budget.months}-month horizon. Investment P&L excludes deposits and includes trading fees. Percentage returns exclude external cash flows. Dollar dip and return drawdown answer different questions. Frequencies are conditional model counts; no method is ranked as a winner.')
    with tabs[4]:
        st.subheader('What changed, and what is still uncertain')
        st.markdown('**Account accounting:** initial and monthly purchase costs are included. Deposits issue units at the pre-flow NAV; this separates saving from investment performance. Protected money stays outside this pot.\n\n**Simulation:** each chosen whole month is valued at all observed daily closes; contributions and net trades occur at its end. Joint contiguous blocks preserve asset co-movement and some serial dependence. Sample-window, block-length and return-premium assumptions are shown side by side. More simulated paths do not create more independent history.\n\n**Risk model:** 25% diagonal-shrinkage covariance and a convex equal-risk-contribution solve. Future weights use the latest completed cached session; historical stress weights use only pre-event data. The event target then stays fixed. Risk estimates can fail, especially when correlations change.\n\n**Boundaries:** no whole shares, tax lots, intraday liquidity or broker fills. Default return assumptions are historical scenarios, not estimates of a user’s achievable return. ML remains in Research lab, where its negative result against EWMA is retained.')
        with st.expander('View the budget, assumptions and data audit'):
            st.json({'budget':asdict(budget),'settings':asdict(settings),'assumption':assumption,'sample_window':recent,'example_weights':mixes[selected],'data':meta})
        report={'purpose':'Educational conditional scenarios and risk budgeting; no forecast or suitability recommendation',
            'budget':asdict(budget),'settings':asdict(settings),'assumption':assumption,'selected_example':selected,
            'allocation':dict(zip(ASSET_NAMES,weights)),'model_summary':describe_result(result,budget,settings),'data':meta}
        st.download_button('Download my local scenario summary',json.dumps(report,indent=2,allow_nan=False),'roaring_returns_scenarios.json','application/json')
        st.markdown('Methods: [CVX risk-budget allocation](https://www.cvxgrp.org/cvx_short_course/docs/exercises/notebooks/13.20.html). Background: [SEC asset allocation](https://www.investor.gov/introduction-investing/getting-started/asset-allocation).')
    st.divider()
    st.caption('Educational research prototype · USD · No brokerage connection · Scenario outcomes and estimated risk are not guarantees. Budget entries are held in the local app session and excluded from GitHub.')
