"""Local interactive showcase using the same Python planners as the research CLI."""

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
from .data import load_prices
from .synthetic import synthetic_prices
from .policies import plan
from .engine import execute_dollar_plan
from .risk import forecast_risk, execution_scenarios
from .optimization import OptimizerSettings, optimize_execution, optimize_minimum_sale, buffered_minimum_sale
from .execution_research import LABELS

ROOT = Path(__file__).resolve().parents[2]
COLORS = {"Signal minimum sale": "#aab3be", "Analytic lag buffer": "#445c79",
          "Cost-aware QP": "#7e73a3", "Scenario / historical": "#688d67",
          "Scenario / EWMA": "#168a94", "Scenario / ridge volatility": "#b78b32",
          "Risk-budget sales / EWMA": "#317b75", "Risk-budget sales / ridge": "#d39a26",
          "Proportional contributions": "#d4a1a1", "Annual reset": "#bd7f50",
          "Threshold to center": "#597caa", "Buy only": "#a789a4"}


@st.cache_data(show_spinner=False)
def _prices(source):
    if source == "Cached ETF history":
        p, manifest = load_prices(ROOT)
        return p, manifest["processed_sha256"]
    p = synthetic_prices()
    return p, sha256(p.to_csv(float_format="%.12g").encode()).hexdigest()


@st.cache_data(show_spinner=False)
def _lab(history, holdings, contribution, target, band, cost, penalty, tail_weight, level):
    h, a = np.asarray(holdings), np.asarray(target)
    forecasts = {m: forecast_risk(history, m) for m in ("historical", "ewma", "ridge_vol")}
    orders, diagnostics = {}, {}
    orders["min_sales_band"] = plan("min_sales_band", h, contribution, a, band, 1)
    orders["buffered_band"], delta = buffered_minimum_sale(h, 0, contribution, a, band, forecasts["ewma"].covariance)
    settings = OptimizerSettings(band, cost, penalty, tail_weight, level)
    scenario_sets = {}
    for name, model in (("cost_aware", None), ("scenario_ewma", "ewma"), ("scenario_ridge", "ridge_vol"),
                        ("cvar_sales_ewma", "ewma"), ("cvar_sales_ridge", "ridge_vol")):
        shocks = np.zeros((1, len(a))) if model is None else execution_scenarios(history, forecasts[model])
        optimizer = optimize_minimum_sale if name.startswith("cvar_sales") else optimize_execution
        result = optimizer(h, 0, contribution, a, shocks, settings)
        orders[name] = result.trades
        diagnostics[name] = {"objective": result.objective, "tail_loss": result.tail_loss,
                             "tracking_loss": result.tracking_loss, "solver": result.status,
                             "objective_name": result.objective_name, "risk_slack": result.risk_slack,
                             "solve_seconds": result.solve_seconds, "budget_residual": result.budget_residual,
                             "solver_trace": result.solver_trace, "tie_break_completed": result.tie_break_completed}
        scenario_sets[name] = shocks
    return orders, diagnostics, forecasts, delta, scenario_sets


def _study(source):
    folder = ROOT/"results"/("execution_v2" if source == "Cached ETF history" else "execution_v2_synthetic")
    if not (folder/"summary.csv").exists():
        return None
    return {name: pd.read_csv(folder/f"{name}.csv") for name in
            ("summary", "monthly_metrics", "monthly_curves", "paired_intervals", "risk_diagnostics")} | {
            "manifest": json.loads((folder/"manifest.json").read_text()),
            "protocol": json.loads((folder/"protocol.json").read_text())}


def _color(methods=None):
    domain = [name for name in COLORS if methods is None or name in methods]
    return alt.Color("Method:N", scale=alt.Scale(domain=domain, range=[COLORS[name] for name in domain]),
                     legend=alt.Legend(orient="bottom", columns=1, labelLimit=220, labelFontSize=10))


def _evidence(study):
    if study is None:
        st.info("This source has no generated study yet. The execution lab works immediately; run the research CLI to populate historical evidence.")
        st.code("python -m roaring_returns research --source synthetic --publish")
        return
    st.caption("EXPLORATORY RETROSPECTIVE STUDY · Fixed settings, no historical parameter search · All 2005–2025 periods were previously inspected.")
    p = study["protocol"]
    st.write(f"USD {p['initial_wealth']:,.0f} + USD {p['monthly_contribution']:,.0f}/month · equal targets · {p['band']*100:g}pp band · {p['cost_bps']:g}bp per side. The lab controls do not change these fixed study results.")
    period = st.selectbox("Retrospective period", list(study["summary"].period.unique()), index=len(study["summary"].period.unique())-1)
    summary = study["summary"].query("period == @period").copy()
    defaults = [LABELS[x] for x in ("min_sales_band", "buffered_band", "cvar_sales_ewma", "cvar_sales_ridge")]
    selected = st.multiselect("Methods to compare", summary.label.tolist(), default=defaults)
    chosen = summary[summary.label.isin(selected)]
    if len(summary):
        st.caption(f"Account initialization: {summary.realized_start.iloc[0]} · last session: {summary.realized_end.iloc[0]}. The first ETF window begins after the common warm-up; it is not a full January-2005 start.")
    left, right = st.columns([1, 1.3], gap="large")
    with left:
        st.subheader("Drift versus selling")
        points = chosen.assign(Method=chosen.label, sales_percent=100*chosen.annual_sales_over_mean_wealth)
        chart = alt.Chart(points).mark_circle(size=160, opacity=.9).encode(
            x=alt.X("sales_percent:Q", title="Annual sales / mean wealth (%)", scale=alt.Scale(zero=True)),
            y=alt.Y("posttrade_rms_deviation_pp:Q", title="Post-fill RMS deviation (pp)", scale=alt.Scale(zero=False)),
            color=_color(selected), tooltip=["Method", alt.Tooltip("sales_percent:Q", format=".2f"),
                alt.Tooltip("posttrade_rms_deviation_pp:Q", format=".3f"), "violating_months", "selling_months"])
        st.altair_chart(chart.properties(height=330), width="stretch")
        st.caption("Lower drift may require more trades. Compare both axes, fees and violation counts.")
    with right:
        st.subheader("Time-weighted NAV")
        curves = study["monthly_curves"].query("period == @period").copy()
        curves = curves[curves.label.isin(selected)].assign(Method=lambda d: d.label)
        curves["date"] = pd.to_datetime(curves.date)
        chart = alt.Chart(curves).mark_line(strokeWidth=2.3).encode(
            x=alt.X("date:T", title=None), y=alt.Y("nav:Q", title="NAV, initial funding = 1", scale=alt.Scale(zero=False)),
            color=_color(selected), tooltip=["Method", "date:T", alt.Tooltip("nav:Q", format=".3f")])
        st.altair_chart(chart.properties(height=330).interactive(), width="stretch")
        st.caption("External deposits are excluded from TWR. These are derived monthly portfolio values, not live prices or alpha estimates.")
    table = chosen[["label", "posttrade_rms_deviation_pp", "violating_months", "months", "selling_months",
                    "annual_sales_over_mean_wealth", "total_fees", "max_posttrade_excess_pp",
                    "tie_break_incomplete_months", "risk_slack_months"]].copy()
    months = study["monthly_metrics"].query("period == @period")
    counts = months.assign(material_sale=months.actual_sales_fraction_signal > 1e-6).groupby("strategy").material_sale.sum()
    table["selling_months"] = chosen.strategy.map(counts).to_numpy()
    table["Outside / months"] = table.violating_months.astype(int).astype(str)+" / "+table.months.astype(int).astype(str)
    table = table.rename(columns={"label": "Method", "posttrade_rms_deviation_pp": "RMS (pp)",
        "selling_months": "Selling months", "annual_sales_over_mean_wealth": "Annual sales / wealth",
        "total_fees": "Fees (USD)", "max_posttrade_excess_pp": "Max overshoot (pp)",
        "tie_break_incomplete_months": "LP-only months", "risk_slack_months": "Risk-slack months"})
    st.dataframe(table[["Method", "RMS (pp)", "Outside / months", "Selling months", "Annual sales / wealth", "Fees (USD)", "Max overshoot (pp)", "LP-only months", "Risk-slack months"]],
                 hide_index=True, width="stretch", column_config={"RMS (pp)": st.column_config.NumberColumn(format="%.3f"),
                 "Annual sales / wealth": st.column_config.NumberColumn(format="percent"),
                 "Fees (USD)": st.column_config.NumberColumn(format="$%.2f")})
    st.caption("Selling months exclude sales ≤ 1e-6 of signal wealth (one cent per USD 10,000), uniformly across methods. Raw summary downloads retain the legacy >1e-7 USD count.")
    with st.expander("Paired uncertainty intervals and assumptions"):
        st.write("Candidate minus signal minimum sale. Six-month circular blocks of paired monthly outcomes, 1,000 repetitions. Conditional descriptive intervals: no model refitting, no reconstructed paths, no new out-of-sample evidence.")
        ci = study["paired_intervals"].query("period == @period").copy()
        st.dataframe(ci[ci.strategy.map(LABELS).isin(selected)], hide_index=True, width="stretch")
    st.download_button("Download study summary", study["summary"].to_csv(index=False), "execution_v2_summary.csv", "text/csv")


def main():
    st.set_page_config(page_title="Roaring Returns | Execution Risk Lab", page_icon="◈", layout="wide")
    st.markdown("""<style>
    .block-container {max-width:1440px;padding-top:3.6rem;padding-bottom:3rem}
    [data-testid="stSidebar"] {border-right:1px solid #e1e5e9}
    [data-testid="stSidebar"] .block-container {padding-top:1.6rem}
    h1 {font-weight:650!important;letter-spacing:-1.8px!important;font-size:2.8rem!important;line-height:1.1!important}
    h2,h3 {letter-spacing:-.5px!important}
    .eyebrow {font-size:11px;letter-spacing:2px;color:#6a7888;font-weight:700;margin-bottom:14px}
    .brand {font-size:20px;font-weight:700;letter-spacing:-.4px;margin-bottom:3px}
    .brandmark {color:#b78b32;margin-right:9px}
    .lead {font-size:17px;line-height:1.65;color:#6a7888;max-width:800px;margin-bottom:24px}
    .pill {display:inline-block;padding:6px 11px;border:1px solid #ddd4bd;background:#faf6ed;color:#876923;border-radius:20px;font-size:11px;letter-spacing:1px}
    [data-testid="stMetric"] {background:white;border:1px solid #e4e8ed;border-radius:12px;padding:17px 19px}
    [data-testid="stMetricLabel"] {color:#6a7888;font-size:12px}
    [data-testid="stMetricValue"] {font-size:22px;font-weight:600}
    @media (max-width:1100px) {
      [data-testid="stMetric"] {padding:14px 10px}
      [data-testid="stMetricValue"] div {font-size:20px!important}
    }
    [data-baseweb="tab-list"] {gap:30px;border-bottom:1px solid #dce2e8;margin-bottom:22px}
    [data-baseweb="tab"] {font-weight:600;padding:12px 0;font-size:14px}
    [data-testid="stDataFrame"] {border-radius:10px}
    </style>""", unsafe_allow_html=True)
    cached = (ROOT/"data/raw/manifest.json").exists()
    with st.sidebar:
        st.markdown('<div class="brand"><span class="brandmark">◈</span>Roaring Returns</div>', unsafe_allow_html=True)
        st.caption("EXECUTION RISK LAB · v0.2")
        st.divider()
        sources = ["Cached ETF history", "Synthetic market"] if cached else ["Synthetic market"]
        source = st.selectbox("Lab data source", sources)
        prices, data_hash = _prices(source)
        with st.form("portfolio_controls"):
            signal = st.date_input("Signal close", prices.index[-1].date(), min_value=prices.index[min(150, len(prices)-1)].date(), max_value=prices.index[-1].date())
            wealth = st.number_input("Current portfolio (USD)", min_value=100., max_value=100000000., value=10000., step=1000.)
            contribution = st.number_input("Next contribution (USD)", min_value=0., max_value=100000., value=100., step=50.)
            st.caption("CURRENT INVESTED WEIGHTS")
            stock = st.slider("QQQ (%)", 0, 100, 45)
            gold = st.slider("GLD (%)", 0, 100, 25)
            st.caption(f"IEF: {max(0, 100-stock-gold)}% · Target: equal thirds")
            band = st.slider("Allowed deviation (pp)", 1., 10., 5., .5)/100
            cost = st.slider("Cost per side (bp)", 0., 25., 2., 1.)
            st.caption("TRACKING-QP COMPARATORS ONLY")
            penalty = st.select_slider("Trading penalty", options=[.001, .002, .005, .01, .02, .05], value=.002)
            tail_weight = st.select_slider("Tail-risk penalty", options=[0., .1, .5, 1., 2.], value=.5)
            st.form_submit_button("Build frozen trade plans", type="primary", width="stretch")
        st.caption("Lab controls change the hypothetical trade. The historical study uses its own fixed protocol.")
        st.divider()
        st.caption("Python · CVXPY · Clarabel\n\nNo brokerage connection. No credentials needed for the synthetic demo.")
    if stock+gold > 100:
        st.error("QQQ and GLD weights must sum to at most 100%.")
        st.stop()
    date = prices.index[prices.index <= pd.Timestamp(signal)][-1]
    history = prices.loc[:date].pct_change().iloc[1:].to_numpy()
    h = wealth*np.array([stock, gold, 100-stock-gold])/100
    a = np.repeat(1/3, 3)
    with st.spinner("Solving causal execution-risk plans…"):
        orders, model_diagnostics, forecasts, buffer, scenario_sets = _lab(history, tuple(h), contribution, tuple(a), band, cost, penalty, tail_weight, .9)
    study = _study(source)
    st.markdown('<div class="eyebrow">PERSONAL QUANTITATIVE RESEARCH / PORTFOLIO IMPLEMENTATION</div>', unsafe_allow_html=True)
    title, badge = st.columns([4, 1])
    with title:
        st.title("Decisions under execution risk.")
        st.markdown('<div class="lead">A fixed target. A new cash contribution. One uncertain session before your trade fills. Inspect what each method buys, sells and risks.</div>', unsafe_allow_html=True)
    with badge:
        st.markdown('<span class="pill">INTERACTIVE RESEARCH</span>', unsafe_allow_html=True)
    if source == "Synthetic market":
        st.info(f"SYNTHETIC DATA · Artificial regime-switching paths, not observed ETF prices. Signal snapshot: {date.date()}.")
    else:
        st.caption(f"CACHED HISTORICAL SNAPSHOT · QQQ / GLD / IEF total-return proxies · Signal: {date.date()} · Historical, not live market data")
    tabs = st.tabs(["Execution lab", "Historical evidence", "Model diagnostics", "Methods & reproducibility"])
    with tabs[0]:
        selected = st.selectbox("Inspect a plan", list(orders), index=6, format_func=lambda x: LABELS[x])
        trade = orders[selected]
        # These shocks are deliberately AFTER the frozen-order cache call.
        # They can alter fills and outcomes, never the plan itself.
        st.subheader("What happens between signal and fill?")
        controls = st.columns(3)
        shocks = np.array([controls[i].slider(f"{ticker} next-session shock (%)", -10., 10., value, .5)
                           for i, (ticker, value) in enumerate(zip(prices.columns, [3., -1., 0.]))])/100
        marked = h*(1+shocks)
        outcome_rows, weight_rows = [], []
        for name, order in orders.items():
            final, cash, buys, sales, fees = execute_dollar_plan(marked, contribution, order, cost/10000)
            w = final/(final.sum()+cash)
            deviation = float(np.max(np.abs(w-a))*100)
            outcome_rows.append({"Method": LABELS[name], "strategy": name, "Sales": sales, "Fees": fees,
                                 "Max deviation (pp)": deviation})
            for ticker, value in zip(prices.columns, w):
                weight_rows.append(dict(Method=LABELS[name], Asset=ticker, Weight=value))
        outcomes = pd.DataFrame(outcome_rows)
        active = outcomes[outcomes.strategy == selected].iloc[0]
        metric = st.columns(4)
        metric[0].metric("Plan sales", f"${np.maximum(-trade, 0).sum():,.0f}")
        metric[1].metric("Stress drift", f"{active['Max deviation (pp)']:.2f} pp")
        metric[2].metric("Stress band", "WITHIN" if active['Max deviation (pp)'] <= band*100+1e-8 else "OUTSIDE")
        metric[3].metric("Stress fees", f"${active.Fees:.2f}")
        left, right = st.columns([1.05, 1], gap="large")
        with left:
            st.subheader("The frozen dollar order")
            trades = pd.DataFrame({"Asset": prices.columns, "Order (USD)": trade, "Side": np.where(trade >= 0, "Buy", "Sell")})
            chart = alt.Chart(trades).mark_bar(cornerRadiusEnd=4).encode(
                y=alt.Y("Asset:N", sort=list(prices.columns), title=None),
                x=alt.X("Order (USD):Q", title="Sell ← frozen dollars → Buy"),
                color=alt.Color("Side:N", scale=alt.Scale(domain=["Buy", "Sell"], range=["#168a94", "#b78b32"]), legend=None),
                tooltip=["Asset", "Side", alt.Tooltip("Order (USD):Q", format=".2f")])
            st.altair_chart(chart.properties(height=220), width="stretch")
            order_id = sha256(np.asarray(trade, dtype="<f8").tobytes()).hexdigest()[:12]
            st.caption(f"Frozen order ID {order_id} · Changing the next-session shock does not re-plan this order.")
            st.download_button("Download this trade plan", trades.to_csv(index=False), "frozen_trade_plan.csv", "text/csv")
        with right:
            st.subheader("Compare the same price shock")
            view = outcomes.drop(columns=["strategy"]).copy()
            st.dataframe(view, hide_index=True, width="stretch", column_config={
                "Sales": st.column_config.NumberColumn(format="$%.2f"), "Fees": st.column_config.NumberColumn(format="$%.2f"),
                "Max deviation (pp)": st.column_config.NumberColumn(format="%.3f")})
            st.caption("Every plan sees identical holdings, contribution, fees and realized shock. Less deviation can cost more selling.")
            weights = pd.DataFrame(weight_rows)
            weights = weights[weights.Method == LABELS[selected]]
            st.altair_chart(alt.Chart(weights).mark_bar(color="#445c79", cornerRadiusEnd=3).encode(
                x=alt.X("Asset:N", title=None), y=alt.Y("Weight:Q", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
                tooltip=["Asset", alt.Tooltip("Weight:Q", format=".1%")]).properties(height=150), width="stretch")
        if selected in model_diagnostics:
            with st.expander("Solver diagnostics"):
                st.json(model_diagnostics[selected])
                st.caption("Tail loss is normalized dollar excess over filtered historical scenarios. It is not a calibrated market probability or exact percentage-weight CVaR.")
    with tabs[1]:
        available = [label for label, folder in (("Cached ETF history", "execution_v2"),
                     ("Synthetic market", "execution_v2_synthetic"))
                     if (ROOT/"results"/folder/"summary.csv").exists()]
        evidence_source = st.selectbox("Evidence dataset", available,
            index=available.index(source) if source in available else 0) if available else source
        st.caption("Evidence dataset is independent of the hypothetical lab inputs. Published ETF aggregates work without downloading raw prices.")
        _evidence(_study(evidence_source))
    with tabs[2]:
        st.subheader("What is learned?")
        st.write("Ridge predicts next-session variance from lagged 1-, 5- and 22-session realized variance. It estimates execution uncertainty, without predicting expected returns. Only matured labels enter training. Variance is clipped to 0.1–10× EWMA variance; the correlation structure also comes from shrunk EWMA.")
        risk_rows = []
        for model, forecast in forecasts.items():
            for asset, vol in zip(prices.columns, forecast.volatility):
                risk_rows.append(dict(Model=model, Asset=asset, annualized_volatility=vol*np.sqrt(252)))
        risk_table = pd.DataFrame(risk_rows)
        chart = alt.Chart(risk_table).mark_bar(cornerRadiusEnd=3).encode(
            x=alt.X("Asset:N", title=None), xOffset="Model:N",
            y=alt.Y("annualized_volatility:Q", title="Annualized forecast volatility", axis=alt.Axis(format="%")),
            color=alt.Color("Model:N", scale=alt.Scale(range=["#445c79", "#168a94", "#b78b32"])),
            tooltip=["Model", "Asset", alt.Tooltip("annualized_volatility:Q", format=".2%")])
        st.altair_chart(chart.properties(height=270), width="stretch")
        ridge = forecasts["ridge_vol"]
        st.caption(f"Ridge status: {ridge.used_model} · Matured training samples: {ridge.training_samples} · Last usable label date: {date.date()} · Correlation: shrunk EWMA")
        if ridge.coefficients is not None:
            coefficients = pd.DataFrame(ridge.coefficients, index=prices.columns, columns=["Intercept", "log RV(1)", "log RV(5)", "log RV(22)"])
            st.dataframe(coefficients, width="stretch")
            st.caption("Coefficients use standardized features and a mean-scaled variance response. Associations are not causal explanations or SHAP values.")
        if study is not None:
            st.subheader("Prequential variance scores")
            st.dataframe(study["risk_diagnostics"], hide_index=True, width="stretch")
            st.caption("Lower variance QLIKE is better. Scores use the next actual execution-session squared return, a noisy variance proxy. ML is retained even when it loses to EWMA; no model is selected by the displayed result.")
        st.write(f"Analytic per-asset buffer for this state: {', '.join(f'{s} {d*100:.3f}pp' for s, d in zip(prices.columns, buffer))}. This first-order buffer is not a joint coverage guarantee.")
    with tabs[3]:
        st.subheader("One decision, three transparent layers")
        st.markdown("**1 · Information:** completed-session returns → shrunk covariance or causal ridge variance.\n\n**2 · Planning:** frozen dollar trades → deterministic cost budget, scenario sale caps, tracking and CVaR penalties.\n\n**3 · Execution:** mark existing holdings → receive contribution → fill the frozen order → measure realized drift, fees and TWR.")
        st.latex(r"X_s=H\odot(1+r_s)+b-s,\qquad (1+\kappa)\mathbf{1}^Tb=(K+C)+(1-\kappa)\mathbf{1}^Ts")
        st.latex(r"\min\ \mathbb{E}_s\| (X_s-aW_s)/S\|_2^2 + \lambda\|b+s\|_1/S+\gamma\operatorname{CVaR}_{\alpha}(\ell_s)")
        st.caption("S is signal wealth plus contribution; the CVaR loss is the largest asset's dollar band excess divided by S. Price uncertainty acts on original holdings before the fill. All sampled bands remain soft.")
        st.markdown("**Risk-budget sales variant:** minimize normalized sales plus 50× risk-budget slack, with modeled 90% CVaR constrained to 0.05pp of signal-plus-flow capital plus that slack. A second QP selects near-target trades on the LP's sales/slack face. A buy-only optimal face is constrained to exactly zero sales. Failed tie-breaks are disclosed as LP-only months.")
        st.latex(r"\min_{b,s,\epsilon\geq0}\ \mathbf{1}^Ts/S+50\epsilon,\qquad\operatorname{CVaR}_{0.9}(\ell)\leq0.0005+\epsilon")
        st.markdown("Inspired by Boyd's self-financing convex construction and CVaR/scenario methods. This implementation does not reproduce OT-DRO geometry learning, end-to-end DFL, reinforcement learning, quantum optimization, taxes or share-level execution.")
        provenance = ROOT/"docs/paper_implementation_map.csv"
        if provenance.exists():
            st.dataframe(pd.read_csv(provenance), hide_index=True, width="stretch")
        with st.expander("Data and solver provenance"):
            st.json({"lab_source": source, "signal_date": str(date.date()), "lab_data_sha256": data_hash,
                     "settings": {"band": band, "cost_bps": cost, "turnover_penalty": penalty,
                                  "tail_weight": tail_weight, "tail_level": .9},
                     "solver": "CVXPY / Clarabel", "forecast_target": "next-session variance, not alpha"})
            if study is not None:
                st.json(study["manifest"])
        st.caption("Historical results are exploratory. Publicly inspected history and bootstrap resampling do not constitute a new untouched holdout. Synthetic demonstrations are mechanism tests.")
    st.divider()
    st.caption("ROARING RETURNS · Research with auditable assumptions · Python source and methods: github.com/Kai1024-star/roaring-returns")
