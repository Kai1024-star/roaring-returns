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
from .planner_data import planner_market

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


def _money(value):
    return f"${value:,.0f}"


def _animate(result, settings, real, note):
    scale = ((1+settings.inflation)**(np.arange(result.wealth.shape[1])/12) if real
             else np.ones(result.wealth.shape[1]))
    payload = {"values": (result.wealth[0]/scale).round(2).tolist(),
               "deposits": (result.contributed/scale).round(2).tolist(),
               "holdings": (result.sample_holdings/scale[:, None]).round(2).tolist(), "note": note,
               "unit": result.period_unit, "dates": result.dates}
    template = (Path(__file__).parent/"assets/journey.html").read_text()
    st.iframe(template.replace("__DATA__", json.dumps(payload).replace("</", "<\\/")), height="content", tab_index=0)


def _bundle(prices, meta, budget, settings):
    # Budget-dependent results stay in this user's in-memory session, not a
    # persistent/global cache. Market history is public, budget entries are not.
    key = sha256(json.dumps({"budget": asdict(budget), "settings": asdict(settings),
                            "data": meta["processed_sha256"]}, sort_keys=True).encode()).hexdigest()
    if st.session_state.get("planner_bundle_key") != key:
        history = monthly_returns(prices)
        draws, indexes = sampled_paths(history.to_numpy(), budget.months, settings)
        results = {name: simulate_mix(draws, budget, weights, settings) for name, weights in EXAMPLES.items()}
        st.session_state.planner_bundle = (history, draws, indexes, results)
        st.session_state.planner_bundle_key = key
    return st.session_state.planner_bundle


def _fan(result, budget, settings, real):
    time = np.arange(budget.months+1)
    scale = (1+settings.inflation)**(time/12) if real else np.ones(len(time))
    low, mid, high = np.quantile(result.wealth, [.1, .5, .9], axis=0)/scale
    frame = pd.DataFrame({"Month": time, "Lower scenario": low, "Middle outcome": mid,
        "Upper scenario": high, "Deposits": result.contributed/scale})
    if budget.goal_today > 0:
        frame["Goal"] = np.full(len(time), budget.goal_today) if real else budget.goal_today*(1+settings.inflation)**(time/12)
    chart = alt.Chart(frame).encode(x=alt.X("Month:Q", title="Months from now"))
    band = chart.mark_area(color="#168a94", opacity=.13).encode(
        y=alt.Y("Lower scenario:Q", title="Today's dollars" if real else "Nominal dollars", scale=alt.Scale(zero=True)),
        y2="Upper scenario:Q", tooltip=["Month", alt.Tooltip("Lower scenario:Q", format="$,.0f"), alt.Tooltip("Upper scenario:Q", format="$,.0f")])
    lines = chart.transform_fold(["Middle outcome", "Deposits"]+(["Goal"] if budget.goal_today > 0 else []),
        as_=["Series", "Value"]).mark_line(strokeWidth=2.5).encode(y="Value:Q",
        color=alt.Color("Series:N", scale=alt.Scale(domain=["Middle outcome", "Deposits", "Goal"],
                        range=["#168a94", "#8797a9", "#b78b32"]), legend=alt.Legend(orient="bottom")),
        strokeDash=alt.StrokeDash("Series:N", legend=None), tooltip=["Month", "Series:N", alt.Tooltip("Value:Q", format="$,.0f")])
    st.altair_chart((band+lines).properties(height=315), width="stretch")


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
                a = st.columns(3)
                cash_rate = a[0].number_input("Cash interest assumption (%/year)", min_value=-5., max_value=20., value=round(100*sample_cash_rate, 4), step=.5,
                    help="Starts at the snapshot's annualized geometric BIL return. This constant future assumption is not a current bank rate or guaranteed product. Raising it raises all modeled asset log returns equally, under a constant-premium assumption.")/100
                inflation = a[1].number_input("Inflation assumption (%/year)", min_value=0., max_value=20., value=2.5, step=.5)/100
                haircut = a[2].number_input("Reduce historical excess returns (log pp/year)", min_value=0., max_value=10., value=0., step=.5,
                    help="Subtract this annual log-return amount from asset returns above the BIL cash proxy, then add your cash-rate assumption. Zero is the unadjusted sample; a reduction is a sensitivity, not a forecast.")/100
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
    with st.spinner("Building the same market scenarios for every example…"):
        history, draws, indexes, results = _bundle(prices, meta, budget, settings)
    st.subheader("Choose an example to explore")
    selected = st.radio("Fixed examples, not recommendations", list(EXAMPLES), index=0, horizontal=True)
    result = results[selected]
    weights = EXAMPLES[selected]
    allocation = pd.DataFrame({"Asset": ASSET_NAMES, "Dollars": result.sample_holdings[0], "Order": np.arange(4)})
    st.altair_chart(alt.Chart(allocation).mark_bar(size=28).encode(x=alt.X("Dollars:Q", title=None,
        axis=alt.Axis(labels=False, ticks=False, domain=False, grid=False)),
        color=alt.Color("Asset:N", sort=list(ASSET_NAMES), scale=alt.Scale(domain=list(ASSET_NAMES), range=MIX_COLORS),
                        legend=None), order="Order:Q",
        tooltip=["Asset", alt.Tooltip("Dollars:Q", format="$,.0f")]).properties(height=40), width="stretch")
    legend = "".join(f'<span style="white-space:nowrap"><span style="color:{color}">●</span> {name} <b>{weight:.0%}</b></span>'
                     for name, color, weight in zip(ASSET_NAMES, MIX_COLORS, weights))
    st.markdown(f'<div style="display:flex;gap:12px 22px;flex-wrap:wrap;font-size:12px;margin:0 0 12px">{legend}</div>', unsafe_allow_html=True)
    st.caption("Example allocations are fixed in advance. SPY is a US large-cap proxy; IEF holds 7–10 year Treasuries and has interest-rate risk. Gold and bond funds can lose value. Cash here is inside this pot; your protected cash stays outside.")
    tabs = st.tabs(["Stress first", "Possible paths", "Compare choices", "Inside the model"])
    with tabs[0]:
        st.subheader("What would a difficult market feel like?")
        if not synthetic:
            episodes = {"2022 · rising rates": ("2022-01-01", "2022-12-31"),
                        "2020 · sudden sell-off": ("2020-02-01", "2020-04-30"),
                        "2008–09 · market stress": ("2008-09-01", "2009-03-31")}
            episode = st.selectbox("Replay a historical pattern", list(episodes))
            start, end = episodes[episode]
            stress_results = {name: replay_daily(prices, budget, a, settings, start, end) for name, a in EXAMPLES.items()}
            dates = stress_results[selected].dates
            st.caption(f"Daily-close replay: {dates[0]} to {dates[-1]}. Holdings are marked each session; contributions and net trades occur at month-end. Stock/gold/bond returns and the BIL cash proxy use observed history. Only fees and your budget are hypothetical. Daily closes still miss intraday lows.")
        else:
            episode = "Designed three-month downturn"
            stress = np.array([[[-.20, -.04, -.08], [-.10, -.02, -.04], [.05, .02, .01]]])[:, :budget.months]
            st.caption("Designed shocks for teaching. This sequence did not occur in a real market dataset.")
            stress_results = {name: simulate_mix(stress, budget, a, settings) for name, a in EXAMPLES.items()}
        active = stress_results[selected]
        cols = st.columns(3)
        cols[0].metric("Replay ending value", _money(active.wealth[0, -1]))
        cols[1].metric("Deposited into this pot", _money(active.contributed[-1]))
        cols[2].metric("Largest daily-close dip" if not synthetic else "Largest month-end dip", _money(active.maximum_dip[0]))
        if active.maximum_dip[0] > budget.comfortable_dip+1e-7:
            st.warning(f"This replay crosses your {_money(budget.comfortable_dip)} comfort line. That line is a personal comparison marker, not a loss cap.")
        else:
            st.caption("This replay stays within your comfort marker. More severe losses remain possible.")
        _animate(active, settings, False, f"{episode}: historical replay." if not synthetic else "Designed stress illustration.")
        comparison = pd.DataFrame([{"Example": name, ("Daily-close dip ($)" if not synthetic else "Month-end dip ($)"): r.maximum_dip[0], "Ending value ($)": r.wealth[0, -1]} for name, r in stress_results.items()])
        st.dataframe(comparison, hide_index=True, width="stretch", column_config={
            name: st.column_config.NumberColumn(format="$%.0f") for name in comparison if name != "Example"})
        st.caption("Dip is a dollar fall from a high-water mark adjusted for deposits, not a percentage drawdown. Adding money cannot hide an existing loss. Stress values are nominal dollars; monthly saving enters only at month-end.")
    with tabs[1]:
        st.subheader("A range of possibilities, not a forecast")
        real = st.toggle("Show today's purchasing power", value=True)
        stats = describe_result(result, budget, settings)
        c = st.columns(3)
        c[0].metric("Lower ending scenario · 10th", _money(stats['ending_low_today']))
        c[1].metric("Middle ending scenario", _money(stats['ending_middle_today']))
        c[2].metric("Upper ending scenario · 90th", _money(stats['ending_high_today']))
        st.caption("Ending cards use today's dollars. The chart switch changes chart units only. The lower scenario is not the worst possible outcome.")
        _fan(result, budget, settings, real)
        st.caption(f"Range across {settings.paths:,} illustrative monthly scenarios, not a forecast or guaranteed range. The middle line is not one possible journey. Dips here are measured at month-ends; daily stress replay can reveal deeper falls within a month.")
        with st.expander("Assumptions behind these paths"):
            source_word = "synthetic input" if synthetic else "observed historical"
            st.write(f"{len(history)} {source_word} months, resampled jointly in circular 6-month blocks. Shading is the 10th–90th percentile at each month, not a coverage guarantee. Returns use your cash-rate assumption + sampled excess log returns over BIL − {100*settings.return_haircut:g} log pp/year.")
            st.write(f"Cash assumption: {100*settings.cash_rate:.2f}%/year; sample BIL geometric baseline: {100*sample_cash_rate:.2f}%. Raising the cash assumption raises every modeled asset's log return equally (constant-premium assumption). This does not model a change in the yield curve. Gold/equity performance is sample-specific; historical gold performance is not a representative expected premium.")
            st.write("At a 6-month horizon each path is one block. Repeated draws do not create new independent history, and circular blocks can join the sample's end to its beginning. Unseen crises and structural changes are not represented.")
        with st.expander("Replay one illustrative journey"):
            _animate(result, settings, real, "First scenario from a fixed seed, not a selected winner or the median path.")
        extra = st.slider("What if I could set aside extra each month? ($)", 0, 500, 0, 25,
                          help="A hypothetical comparison, not a recommendation to spend more than your budget allows.")
        if extra:
            alternative = simulate_mix(draws, budget, weights, settings, extra_monthly=extra)
            delta = describe_result(alternative, budget, settings)['ending_middle_today']-stats['ending_middle_today']
            st.write(f"With an extra {_money(extra)}/month available after bills, the middle ending scenario changes by {_money(delta)} in today's dollars, using the same market paths. Any reserve gap is filled first.")
    with tabs[2]:
        st.subheader("Compare trade-offs without a winner badge")
        rows = []
        for name, r in results.items():
            row = {"Example": name, **describe_result(r, budget, settings)}
            rows.append(row)
        table = pd.DataFrame(rows).rename(columns={"ending_low_today": "Lower ending ($ today)",
            "ending_middle_today": "Middle ending ($ today)", "ending_high_today": "Upper ending ($ today)",
            "ending_below_deposits_frequency": "Ends below deposits (nominal)", "dip_exceeds_comfort_frequency": "Month-end dip crosses your line",
            "dip_90_nominal": "90th-percentile month-end dip ($ nominal)", "median_fees": "Median fees ($ nominal)",
            "median_selling_months": "Median selling months", "total_deposits_nominal": "Deposits ($ nominal)", "goal_frequency": "Reaches your goal"})
        st.dataframe(table, hide_index=True, width="stretch", column_config={
            **{name: st.column_config.NumberColumn(format="$%.0f") for name in table if "($" in name},
            **{name: st.column_config.NumberColumn(format="percent") for name in ["Ends below deposits (nominal)", "Month-end dip crosses your line", "Reaches your goal"] if name in table}})
        st.caption("Frequencies count outcomes inside this resampling model, not real-world probabilities. All examples use identical paths, contributions, fees and cash/inflation assumptions. Goals are in today's dollars; the dip marker is in nominal dollars. Protected cash is excluded.")
        st.markdown("**Savings reference** is an assumed constant cash rate, not an insured product or a market quote. **More cash**, **Mixed example** and **More stocks** are teaching examples; none is selected for you.")
    with tabs[3]:
        st.subheader("Understand what the model can — and cannot — show")
        st.markdown("**Budget:** protected cash stays outside the investment pot; a shortfall is funded before investing. Monthly contributions remain fixed in nominal dollars.\n\n**Scenarios:** stock, gold, bond and BIL cash-proxy returns are sampled jointly in circular six-month blocks. Risky log returns are rebased as your cash assumption + historical excess over BIL − the optional premium reduction. This aligns interest-rate assumptions across cash and bonds. It preserves some sample relationships, but cannot create unseen crises or prove future coverage. BIL is a short-term Treasury ETF proxy, not an insured deposit; it is not an investable cash product offered here.\n\n**Rebalancing:** new money is allocated in proportion to positive dollar shortfalls (a different rule from the research lab's L2 projection), then resets to the example mix if a monthly weight is more than 5 percentage points away. This controls allocation drift; it does not cap investment losses.\n\n**Timing:** future scenarios are marked monthly. Historical stress is marked at daily closes, with holdings unchanged between month-end net trades and cash following observed BIL returns. Both add contributions at month-end and use your fee assumption. Monthly future paths use your constant cash-rate assumption. Neither inherits the research lab's next-session execution model.")
        st.markdown("**Where ML fits:** the research lab compares next-session ridge volatility with EWMA. It does not predict which asset will rise, and its one-day estimates are not used to manufacture these multi-year scenarios. The earlier ETF study retained a negative ML result.")
        with st.expander("View the budget and model audit"):
            st.json({"budget": asdict(budget), "model_assumptions": asdict(settings), "example_weights_cash_stocks_gold_bonds": EXAMPLES[selected], "market_snapshot": meta})
        report = {"purpose": "Educational scenario comparison, not an investment recommendation or forecast",
            "budget": asdict(budget), "settings": asdict(settings), "data": meta, "selected_example": selected,
            "allocation": dict(zip(ASSET_NAMES, weights)), "model_summary": describe_result(result, budget, settings),
            "limitations": ["protected cash excluded", "no taxes or share granularity", "cash/inflation are assumptions",
                "historical resampling is not prospective evidence", "no capital or coverage guarantee"]}
        st.download_button("Download my local scenario summary", json.dumps(report, indent=2), "roaring_returns_scenarios.json", "application/json")
        st.markdown("Background: [SEC — asset allocation and diversification](https://www.investor.gov/introduction-investing/getting-started/asset-allocation), [SEC — time horizon and risk](https://www.investor.gov/introduction-investing/investing-basics/save-and-invest/gauge-your-risk-tolerance), [FINRA — investing on a budget](https://syndication.finra.org/content/how-invest-budget).")
    st.divider()
    st.caption("A learning and comparison tool. No investment or tax recommendation, guaranteed return, loss cap or brokerage execution. SPY/GLD/IEF are research proxies. Raw market data and your budget entries are not published to GitHub.")
