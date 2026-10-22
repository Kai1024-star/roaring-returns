"""Exploratory v0.2 backtests; the published v0.1 numerical engine stays intact."""

from dataclasses import dataclass
from hashlib import sha256
import numpy as np
import pandas as pd
from .engine import BacktestConfig, BacktestResult, execute_dollar_plan, validate_prices, summarize
from .policies import STRATEGIES, plan, minimum_sale_bound
from .risk import RISK_MODELS, forecast_risk, execution_scenarios, qlike
from .optimization import OptimizerSettings, optimize_execution, optimize_minimum_sale, buffered_minimum_sale

NEW_STRATEGIES = ("buffered_band", "cost_aware", "scenario_historical", "scenario_ewma", "scenario_ridge", "cvar_sales_ewma", "cvar_sales_ridge")
RESEARCH_STRATEGIES = STRATEGIES+NEW_STRATEGIES
LABELS = {
    "proportional": "Proportional contributions", "annual": "Annual reset",
    "threshold_center": "Threshold to center", "cashflow_only": "Buy only",
    "min_sales_band": "Signal minimum sale", "cost_aware": "Cost-aware QP",
    "buffered_band": "Analytic lag buffer",
    "scenario_historical": "Scenario / historical", "scenario_ewma": "Scenario / EWMA",
    "scenario_ridge": "Scenario / ridge volatility",
    "cvar_sales_ewma": "Risk-budget sales / EWMA", "cvar_sales_ridge": "Risk-budget sales / ridge",
}


@dataclass(frozen=True)
class ResearchConfig(BacktestConfig):
    cost_bps: float = 2.
    turnover_penalty: float = .002
    tail_weight: float = .5
    tail_level: float = .90
    scenario_count: int = 252
    scenario_seed: int = 20261022
    stress_multiplier: float = 1.
    risk_measure: str = "cvar"
    tail_budget: float = .0005
    tail_slack_penalty: float = 50.
    warmup_sessions: int = 0
    covariance_lookback_sessions: int = 252
    ewma_half_life_sessions: float = 21.
    covariance_diagonal_shrinkage: float = .15
    ridge_training_window: int = 504
    ridge_minimum_training_samples: int = 126
    ridge_penalty: float = 10.
    buffer_z: float = 1.65

    def optimizer_settings(self):
        return OptimizerSettings(self.band, self.cost_bps, self.turnover_penalty,
                                 self.tail_weight, self.tail_level, self.risk_measure,
                                 self.tail_budget, self.tail_slack_penalty)


def backtest_execution(prices, config, *, start=None, end=None):
    """Initialize before start, retaining earlier prices for causal risk fitting.

    Existing positions earn execution-day returns BEFORE the contribution and
    frozen-dollar fills. No strategy can re-optimize on that day's return.
    """
    validate_prices(prices)
    settings = config.optimizer_settings()
    settings.validate()
    a = np.asarray(config.target, float)
    if config.strategy not in RESEARCH_STRATEGIES or len(a) != prices.shape[1] or np.any(a <= 0) or not np.isclose(a.sum(), 1):
        raise ValueError("Invalid strategy or target.")
    if (not np.isfinite([config.initial_wealth, config.monthly_contribution]).all()
            or config.initial_wealth <= 0 or config.monthly_contribution < 0):
        raise ValueError("Invalid funding.")
    if config.contribution_rate is not None and (not np.isfinite(config.contribution_rate) or config.contribution_rate < 0):
        raise ValueError("Invalid contribution rate.")
    if config.scenario_count < 1 or not np.isfinite(config.stress_multiplier) or config.stress_multiplier <= 0:
        raise ValueError("Invalid scenarios.")
    if not isinstance(config.warmup_sessions, int) or config.warmup_sessions < 0:
        raise ValueError("Warm-up must be a nonnegative session count.")
    first = max(0, int(prices.index.searchsorted(pd.Timestamp(start)))-1) if start is not None else 0
    first = max(first, config.warmup_sessions)
    last = int(prices.index.searchsorted(pd.Timestamp(end), side="right")) if end is not None else len(prices)
    if last-first < 2:
        raise ValueError("Requested interval needs at least two sessions.")
    values = prices.to_numpy(float)
    returns = values[1:]/values[:-1]-1
    rate = config.cost_bps/10000
    h, cash, _, _, initial_fee = execute_dollar_plan(np.zeros(len(a)), config.initial_wealth,
                                                    config.initial_wealth*a, rate)
    wealth = float(h.sum()+cash)
    nav = wealth/config.initial_wealth
    rows, events = [], []

    def record(date, market_return, flow=0., buys=0., sales=0., fees=0.):
        weights = h/wealth
        max_pp = float(np.max(np.abs(weights-a))*100)
        row = dict(date=date, wealth=wealth, cash=float(cash), external_flow=flow,
                   buys=buys, sales=sales, fees=fees, nav=nav,
                   portfolio_return=market_return,
                   rms_deviation_pp=float(np.sqrt(np.mean((weights-a)**2))*100),
                   max_deviation_pp=max_pp, outside_band=max_pp > config.band*100+1e-8)
        row.update({f"weight_{ticker}": float(w) for ticker, w in zip(prices.columns, weights)})
        rows.append(row)

    record(prices.index[first], nav-1, fees=initial_fee)
    for i in range(first+1, last):
        signal_date, date = prices.index[i-1], prices.index[i]
        monthly = date.to_period("M") != signal_date.to_period("M")
        previous_wealth = wealth
        flow = 0.
        if monthly:
            signal_h, signal_cash = h.copy(), cash
            signal_wealth = float(h.sum()+cash)
            signal_weights = h/signal_wealth
            flow = config.contribution_rate*signal_wealth if config.contribution_rate is not None else config.monthly_contribution
            # returns row j is the return at prices row j+1. Last known row
            # before this execution session is i-2, so history stops at i-1.
            history = returns[:i-1]
            forecasts = {name: forecast_risk(history, name,
                lookback=config.covariance_lookback_sessions, training_window=config.ridge_training_window,
                minimum_training=config.ridge_minimum_training_samples, ridge_penalty=config.ridge_penalty,
                half_life=config.ewma_half_life_sessions, shrinkage=config.covariance_diagonal_shrinkage)
                for name in RISK_MODELS}
            optimization = None
            buffer = np.zeros(len(a))
            if config.strategy in STRATEGIES:
                trades = plan(config.strategy, h, cash+flow, a, config.band, date.month)
                chosen = None
            elif config.strategy == "buffered_band":
                chosen = "ewma"
                trades, buffer = buffered_minimum_sale(h, cash, flow, a, config.band, forecasts[chosen].covariance, config.buffer_z)
            else:
                chosen = {"cost_aware": None, "scenario_historical": "historical",
                          "scenario_ewma": "ewma", "scenario_ridge": "ridge_vol",
                          "cvar_sales_ewma": "ewma", "cvar_sales_ridge": "ridge_vol"}[config.strategy]
                shocks = (np.zeros((1, len(a))) if chosen is None else
                          execution_scenarios(history, forecasts[chosen], count=config.scenario_count,
                                              seed=config.scenario_seed, stress_multiplier=config.stress_multiplier,
                                              half_life=config.ewma_half_life_sessions,
                                              shrinkage=config.covariance_diagonal_shrinkage,
                                              residual_window=config.covariance_lookback_sessions))
                optimizer = optimize_minimum_sale if config.strategy.startswith("cvar_sales") else optimize_execution
                try:
                    optimization = optimizer(h, cash, flow, a, shocks, settings)
                except ArithmeticError as error:
                    raise ArithmeticError(f"{config.strategy} at signal {signal_date.date()}: {error}") from error
                trades = optimization.trades
        h *= values[i]/values[i-1]
        before_flow = float(h.sum()+cash)
        market_factor = before_flow/previous_wealth
        buys = sales = fees = 0.
        if monthly:
            cash += flow
            before_trades = h.copy()
            h, cash, buys, sales, fees = execute_dollar_plan(h, cash, trades, rate)
            post_wealth = float(h.sum()+cash)
            post_weights = h/post_wealth
            post_max = float(np.max(np.abs(post_weights-a))*100)
            actual_trades = h-before_trades
            bound = minimum_sale_bound(signal_h, signal_cash+flow, np.maximum(a-config.band, 0), np.minimum(a+config.band, 1))
            cash_needed = float(max(0, np.max(signal_h/a)-signal_wealth))
            event = dict(signal_date=signal_date, execution_date=date, external_flow=flow,
                         signal_wealth=signal_wealth, execution_preflow_wealth=before_flow,
                         contribution_ratio_signal=flow/signal_wealth,
                         contribution_ratio_execution=flow/before_flow,
                         signal_exact_target_cash_needed=cash_needed,
                         signal_exact_target_reachable=flow >= cash_needed-1e-9*signal_wealth,
                         signal_buy_only_band_reachable=bound <= 1e-9*signal_wealth,
                         signal_rms_deviation_pp=float(np.sqrt(np.mean((signal_weights-a)**2))*100),
                         signal_max_deviation_pp=float(np.max(np.abs(signal_weights-a))*100),
                         posttrade_rms_deviation_pp=float(np.sqrt(np.mean((post_weights-a)**2))*100),
                         posttrade_max_deviation_pp=post_max,
                         posttrade_excess_pp=max(0., post_max-config.band*100),
                         posttrade_outside_band=post_max > config.band*100+1e-8,
                         posttrade_cash=cash, posttrade_wealth=post_wealth,
                         planned_min_sales=bound, planned_sales=float(np.maximum(-trades, 0).sum()),
                         actual_sales=sales, actual_buys=buys, fees=fees,
                         actual_sales_fraction_signal=sales/signal_wealth,
                         forecast_cutoff=signal_date,
                         requested_model=chosen or "none",
                         used_model=forecasts[chosen].used_model if chosen else "none",
                         ridge_variance_clips=int(forecasts["ridge_vol"].diagnostics.get("variance_clips", 0)),
                         training_samples=forecasts[chosen].training_samples if chosen else 0,
                         training_last_label_date=signal_date if chosen and forecasts[chosen].training_samples else pd.NaT,
                         order_hash=sha256(np.asarray(trades, dtype="<f8").tobytes()).hexdigest(),
                         fill_adjusted=bool(np.max(np.abs(actual_trades-trades)) > 1e-6*(signal_wealth+flow)),
                         solver_status=optimization.status if optimization else "analytic",
                         solver_trace=optimization.solver_trace if optimization else "analytic",
                         tie_break_completed=optimization.tie_break_completed if optimization else True,
                         solver_seconds=optimization.solve_seconds if optimization else 0.,
                         modeled_tail_loss=optimization.tail_loss if optimization else np.nan,
                         tail_active=bool(optimization and optimization.tail_loss > 1e-8),
                         modeled_risk_slack=optimization.risk_slack if optimization else np.nan,
                         optimization_objective=optimization.objective_name if optimization else "analytic",
                         mean_buffer_pp=float(buffer.mean()*100),
                         objective=optimization.objective if optimization else np.nan,
                         budget_residual=optimization.budget_residual if optimization else np.nan)
            for model, forecast in forecasts.items():
                event[f"qlike_{model}"] = float(qlike(returns[i-1], np.diag(forecast.covariance)).mean())
                for j, ticker in enumerate(prices.columns):
                    event[f"variance_{model}_{ticker}"] = float(forecast.covariance[j, j])
            for j, ticker in enumerate(prices.columns):
                event[f"planned_trade_{ticker}"] = float(trades[j])
                event[f"actual_trade_{ticker}"] = float(actual_trades[j])
                event[f"buffer_pp_{ticker}"] = float(buffer[j]*100)
            events.append(event)
        wealth = float(h.sum()+cash)
        factor = market_factor*wealth/(before_flow+flow)
        nav *= factor
        if abs(wealth-(before_flow+flow-fees)) > 1e-8*wealth or np.any(h < -1e-8) or cash < -1e-8:
            raise ArithmeticError("Self-financing/long-only accounting failed.")
        record(date, factor-1, flow, buys, sales, fees)
    return BacktestResult(pd.DataFrame(rows).set_index("date"), pd.DataFrame(events))


def research_summary(result):
    row = summarize(result)
    e = result.events
    row.update(mean_posttrade_excess_pp=float(e.posttrade_excess_pp.mean()) if len(e) else np.nan,
               max_posttrade_excess_pp=float(e.posttrade_excess_pp.max()) if len(e) else np.nan,
               fill_adjusted_months=int(e.fill_adjusted.sum()) if len(e) else 0,
               annual_sales_over_signal_wealth=float(12*e.actual_sales_fraction_signal.mean()) if len(e) else np.nan,
               solver_optimal_fraction=float(e.solver_status.isin(["optimal", "analytic"]).mean()) if len(e) else np.nan)
    row.update(tail_active_months=int(e.tail_active.sum()) if len(e) else 0,
               solver_retry_months=int(e.solver_trace.str.contains("retry").sum()) if len(e) else 0,
               tie_break_incomplete_months=int((~e.tie_break_completed).sum()) if len(e) else 0,
               risk_slack_months=int((e.modeled_risk_slack > 1e-6).sum()) if len(e) else 0,
               ridge_variance_clips=int(e.ridge_variance_clips.sum()) if len(e) else 0,
               realized_start=str(result.daily.index[0].date()), realized_end=str(result.daily.index[-1].date()))
    for model in RISK_MODELS:
        row[f"qlike_{model}"] = float(e[f"qlike_{model}"].mean()) if len(e) else np.nan
    return row
