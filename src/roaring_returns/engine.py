"""Daily mark-to-market, end-of-session external flows, and lagged dollar plans.

Prices are total-return UNIT INDICES, not tradable per-share ETF prices.
Distributions are implicit in their growth; adding dividend cash would double
count income. Whole-share and pay-date accounting are intentionally excluded.
"""

from dataclasses import dataclass
import numpy as np
import pandas as pd
from .policies import plan, minimum_sale_bound


@dataclass(frozen=True)
class BacktestConfig:
    strategy: str
    initial_wealth: float = 10000
    monthly_contribution: float = 100
    target: tuple = (1/3, 1/3, 1/3)
    band: float = 0.05
    cost_bps: float = 0
    contribution_rate: float | None = None


@dataclass
class BacktestResult:
    daily: pd.DataFrame
    events: pd.DataFrame


def execute_dollar_plan(holdings, cash, trades, cost_rate):
    """Fill frozen dollar orders; cap sales, scale buys to available cash.

    A cost-adjusted fill is not claimed to remain optimal for the frictionless
    planning objective. Never borrow or silently create extra contributions.
    """
    h = np.asarray(holdings, float).copy()
    t = np.asarray(trades, float)
    if not 0 <= cost_rate < 1 or cash < -1e-9 or np.any(h < 0):
        raise ValueError("Invalid execution inputs.")
    sales = np.minimum(np.maximum(-t, 0), h)
    h -= sales
    sell_total = float(sales.sum())
    available = max(0, cash + sell_total * (1 - cost_rate))
    buys = np.maximum(t, 0)
    planned_buys = float(buys.sum())
    scale = min(1.0, available / ((1 + cost_rate) * planned_buys)) if planned_buys else 0
    buys *= scale
    buy_total = float(buys.sum())
    fees = cost_rate * (sell_total + buy_total)
    remaining = cash + sell_total - buy_total - fees
    if remaining < -1e-7 * max(1, cash + sell_total):
        raise ArithmeticError("Execution borrowed cash.")
    return h + buys, max(remaining, 0), buy_total, sell_total, fees


def validate_prices(prices):
    if not isinstance(prices.index, pd.DatetimeIndex) or prices.empty or len(prices) < 2:
        raise ValueError("At least two indexed sessions required.")
    if not prices.index.is_monotonic_increasing or prices.index.has_duplicates:
        raise ValueError("Sessions must be sorted and unique.")
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise ValueError("Prices must be positive and complete; missing data is not filled.")


def backtest(prices, config):
    validate_prices(prices)
    a = np.asarray(config.target, float)
    if len(a) != len(prices.columns) or np.any(a <= 0) or not np.isclose(a.sum(), 1):
        raise ValueError("Invalid target.")
    if config.initial_wealth <= 0 or config.monthly_contribution < 0:
        raise ValueError("Invalid funding.")
    if config.contribution_rate is not None and config.contribution_rate < 0:
        raise ValueError("Invalid contribution rate.")
    rate = config.cost_bps / 10000
    zero = np.zeros(len(a))
    h, cash, _, _, initial_fee = execute_dollar_plan(
        zero, config.initial_wealth, config.initial_wealth * a, rate)
    wealth = float(h.sum() + cash)
    nav = wealth / config.initial_wealth
    rows, events = [], []

    def record(date, r, flow=0., buys=0., sales=0., fees=0., pre_rms=None):
        weights = h / wealth
        rms = float(np.sqrt(np.mean((weights - a)**2)) * 100)
        max_pp = float(np.max(np.abs(weights - a)) * 100)
        row = dict(date=date, wealth=wealth, cash=cash, external_flow=flow,
                   buys=buys, sales=sales, fees=fees, portfolio_return=r,
                   nav=nav, rms_deviation_pp=rms, max_deviation_pp=max_pp,
                   outside_band=max_pp > config.band * 100 + 1e-8,
                   pretrade_rms_pp=rms if pre_rms is None else pre_rms)
        row.update({f"weight_{ticker}": float(w) for ticker, w in zip(prices.columns, weights)})
        rows.append(row)

    record(prices.index[0], nav - 1, fees=initial_fee)
    values = prices.to_numpy(float)
    for i in range(1, len(prices)):
        previous_date, date = prices.index[i-1], prices.index[i]
        previous_wealth = wealth
        monthly = date.to_period("M") != previous_date.to_period("M")
        flow = 0.0
        trades = None
        if monthly:
            # This amount and the whole trade vector are fixed BEFORE today's return.
            flow = (config.contribution_rate * previous_wealth
                    if config.contribution_rate is not None else config.monthly_contribution)
            trades = plan(config.strategy, h, cash + flow, a, config.band, date.month)
            planned_sale_bound = minimum_sale_bound(
                h, cash + flow, np.maximum(a-config.band, 0), np.minimum(a+config.band, 1))
            signal_wealth = float(h.sum()+cash)
            signal_weights = h/signal_wealth
            cash_needed = float(max(0, np.max(h/a)-signal_wealth))
        h *= values[i] / values[i-1]
        before_flow = float(h.sum() + cash)
        market_factor = before_flow / previous_wealth
        pre_rms = float(np.sqrt(np.mean((h/before_flow-a)**2)) * 100)
        buys = sales = fees = 0.0
        if monthly:
            cash += flow  # External contribution arrives at today's CLOSE, after today's return.
            before_trades = h.copy()
            h, cash, buys, sales, fees = execute_dollar_plan(h, cash, trades, rate)
            post_weights = h/(h.sum()+cash)
            post_max = float(np.max(np.abs(post_weights-a))*100)
            event = dict(signal_date=previous_date, execution_date=date,
                         external_flow=flow, signal_wealth=signal_wealth,
                         execution_preflow_wealth=before_flow,
                         contribution_ratio_signal=flow/signal_wealth,
                         contribution_ratio_execution=flow/before_flow,
                         signal_exact_target_cash_needed=cash_needed,
                         signal_exact_target_reachable=flow >= cash_needed-1e-9*signal_wealth,
                         signal_buy_only_band_reachable=planned_sale_bound <= 1e-9*signal_wealth,
                         signal_rms_deviation_pp=float(np.sqrt(np.mean((signal_weights-a)**2))*100),
                         signal_max_deviation_pp=float(np.max(np.abs(signal_weights-a))*100),
                         posttrade_rms_deviation_pp=float(np.sqrt(np.mean((post_weights-a)**2))*100),
                         posttrade_max_deviation_pp=post_max,
                         posttrade_outside_band=post_max > config.band*100+1e-8,
                         posttrade_cash=cash, posttrade_wealth=float(h.sum()+cash),
                         planned_min_sales=planned_sale_bound,
                         planned_sales=float(np.maximum(-trades, 0).sum()),
                         actual_sales=sales, actual_buys=buys, fees=fees)
            for j, ticker in enumerate(prices.columns):
                event[f"planned_trade_{ticker}"] = float(trades[j])
                event[f"actual_trade_{ticker}"] = float(h[j]-before_trades[j])
            events.append(event)
        wealth = float(h.sum() + cash)
        execution_factor = wealth / (before_flow + flow)
        daily_factor = market_factor * execution_factor
        nav *= daily_factor
        if abs(wealth - (before_flow + flow - fees)) > 1e-8 * wealth:
            raise ArithmeticError("Wealth conservation failed.")
        if np.any(h < -1e-8) or cash < -1e-8:
            raise ArithmeticError("Short position or cash borrowing.")
        record(date, daily_factor-1, flow, buys, sales, fees, pre_rms)
    daily = pd.DataFrame(rows).set_index("date")
    return BacktestResult(daily, pd.DataFrame(events))


def summarize(result):
    d, e = result.daily, result.events
    years = (d.index[-1] - d.index[0]).days / 365.25
    nav = d.nav.to_numpy()
    # Include NAV=1 before initial investment so initial costs count in drawdown.
    peaks = np.maximum.accumulate(np.r_[1., nav])[1:]
    return {
        "sessions": len(d), "months": len(e), "final_wealth": float(d.wealth.iloc[-1]),
        "external_contributions": float(d.external_flow.sum()),
        "twr_cagr": float(nav[-1]**(1/years)-1),
        "annualized_volatility": float(d.portfolio_return.iloc[1:].std(ddof=1)*np.sqrt(252)),
        "max_drawdown": float(np.min(nav/peaks-1)),
        "rms_deviation_pp": float(np.sqrt(np.mean(d.rms_deviation_pp**2))),
        "signal_rms_deviation_pp": float(np.sqrt(np.mean(e.signal_rms_deviation_pp**2))) if len(e) else float("nan"),
        "posttrade_rms_deviation_pp": float(np.sqrt(np.mean(e.posttrade_rms_deviation_pp**2))) if len(e) else float("nan"),
        "posttrade_outside_band_fraction": float(e.posttrade_outside_band.mean()) if len(e) else float("nan"),
        "selling_posttrade_outside_fraction": float(e.loc[e.actual_sales > 1e-7, "posttrade_outside_band"].mean()) if len(e) else float("nan"),
        "outside_band_fraction": float(d.outside_band.mean()),
        "max_deviation_pp": float(d.max_deviation_pp.max()),
        "total_sales": float(d.sales.sum()), "selling_months": int((d.sales > 1e-7).sum()),
        "total_fees": float(d.fees.sum()), "mean_cash_fraction": float((d.cash/d.wealth).mean()),
        "annual_sales_over_mean_wealth": float(d.sales.sum()/d.wealth.mean()/years),
    }
