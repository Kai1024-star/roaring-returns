"""Causal covariance estimation, risk budgeting, and cash-flow-aware diagnostics.

The risk-budget objective follows the CVX risk-budget allocation exercise:
https://www.cvxgrp.org/cvx_short_course/docs/exercises/notebooks/13.20.html
No expected-return model or personalized suitability rule is fitted here.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.optimize import brentq


@dataclass(frozen=True)
class RiskBalance:
    weights: np.ndarray
    risky_weights: np.ndarray
    covariance: np.ndarray
    risk_contributions: np.ndarray
    annual_volatility: float
    first_date: str
    last_date: str
    observations: int
    shrinkage: float
    kkt_error: float
    solver: str


def risk_balance(prices, asof, cash_weight=.2, lookback=756, shrinkage=.25):
    """Equal estimated variance contributions inside a user-fixed risky slice.

    A strictly positive diagonal shrinkage gives a PD covariance. Solve in
    normalized units for conditioning, verify first-order optimality, then
    normalize positive positions. Only prices at or before asof can be read.
    """
    if (not np.isfinite([cash_weight, shrinkage]).all() or not 0 <= cash_weight <= 1
            or not 0 < shrinkage <= 1 or lookback < 126):
        raise ValueError('Invalid cash share, covariance window or shrinkage.')
    past = prices.loc[:pd.Timestamp(asof)].iloc[:, :3]
    if past.empty or not np.isfinite(past.to_numpy()).all() or (past <= 0).any().any():
        raise ValueError('Complete positive pre-decision prices are required.')
    returns = past.pct_change(fill_method=None).dropna().tail(lookback)
    if len(returns) < 126:
        raise ValueError('Risk balancing needs at least 126 earlier return observations.')
    raw = np.cov(returns.to_numpy(), rowvar=False, ddof=1)*252
    covariance = (1-shrinkage)*raw+shrinkage*np.diag(np.maximum(np.diag(raw), 1e-8))
    if np.linalg.eigvalsh(covariance).min() <= 0:
        raise ArithmeticError('Covariance is not positive definite.')
    scaled = covariance/np.trace(covariance)*3
    import cvxpy as cp
    x = cp.Variable(3, nonneg=True)
    objective = cp.Minimize(.5*cp.quad_form(x, scaled)-cp.sum(cp.log(x))/3)
    problem = cp.Problem(objective)
    problem.solve(solver='CLARABEL', tol_gap_abs=1e-10, tol_gap_rel=1e-10, tol_feas=1e-10, max_iter=300)
    if problem.status != 'optimal' or x.value is None:
        raise ArithmeticError(f'Risk-budget solver failed: {problem.status}')
    positions = np.asarray(x.value, float)
    error = float(np.max(np.abs(scaled@positions-1/(3*positions))))
    risky = positions/positions.sum()
    variance = float(risky@covariance@risky)
    rc = risky*(covariance@risky)/variance
    if error > 2e-5 or (risky <= 0).any() or not np.allclose(rc, 1/3, atol=2e-5):
        raise ArithmeticError('Risk-budget first-order verification failed.')
    weights = np.r_[cash_weight, (1-cash_weight)*risky]
    return RiskBalance(weights, risky, covariance, rc, (1-cash_weight)*np.sqrt(variance),
                       str(returns.index[0].date()), str(returns.index[-1].date()), len(returns),
                       shrinkage, error, 'Clarabel')


def money_weighted_return(result, path=0):
    """Annualized XIRR for one account; None when no timed investment exists.

    Contributions are outflows, the final portfolio liquidation is an inflow.
    With no withdrawals before liquidation this stream has at most one root.
    A contribution made at liquidation has no investment duration.
    """
    flows = np.diff(result.contributed, prepend=0.)
    values = -flows.astype(float)
    values[-1] += result.wealth[path, -1]
    if result.dates and result.period_unit == 'Session':
        dates = pd.to_datetime(result.dates)
        times = (dates-dates[0]).days.to_numpy()/365.25
    else:
        times = np.arange(len(values))/12
    # Collapse zero-duration inception and liquidation before checking a root.
    if len(times) < 2 or not np.any((values < -1e-10) & (times < times[-1])) or values[-1] <= 0:
        return None
    def npv(log_growth):
        return float(np.sum(values*np.exp(-log_growth*times)))
    lo, hi = npv(-20), npv(20)
    if lo*hi > 0:
        return None
    root = brentq(npv, -20, 20, xtol=1e-12)
    return float(np.expm1(root))


def performance_frame(result):
    """First-path dollars, unitized return and drawdown for plotting/export."""
    values = result.wealth[0]
    nav = result.nav[0] if result.nav is not None else np.full(len(values), np.nan)
    valid = result.return_valid[0] if result.return_valid is not None else np.zeros(len(values), bool)
    fees = result.fee_path[0] if result.fee_path is not None else np.full(len(values), np.nan)
    running_peak = np.maximum.accumulate(np.r_[1., nav])[1:]
    return pd.DataFrame({'Step': np.arange(len(values)), 'Balance': values,
        'Deposits': result.contributed, 'Net investment P&L': values-result.contributed,
        'Gross market P&L': values-result.contributed+fees, 'Fees': fees,
        'Return index': np.where(valid, nav*100, np.nan),
        'Drawdown': np.where(valid, -result.drawdown_path[0] if result.drawdown_path is not None else nav/running_peak-1, np.nan)})


def dollar_units(result, inflation, real):
    """Discount each cash flow at its own date, not all deposits at the end.

    Real P&L therefore includes erosion of purchasing power. Real cumulative
    fees discount fees when paid. Unitized percentage returns remain nominal.
    """
    if result.elapsed_months is not None:
        months = result.elapsed_months
    elif result.period_unit == 'Month':
        months = np.arange(result.wealth.shape[1])
    else:
        dates = pd.to_datetime(result.dates)
        months = (dates-dates[0]).days.to_numpy()/365.25*12
    scale = (1+inflation)**(months/12) if real else np.ones(len(months))
    deposits = np.cumsum(np.diff(result.contributed, prepend=0.)/scale)
    fees = np.cumsum(np.diff(result.fee_path, axis=1, prepend=0.)/scale, axis=1)
    values = result.wealth/scale
    return {'wealth':values,'deposits':deposits,'fees':fees,
            'holdings':result.sample_holdings/scale[:,None], 'pnl':values-deposits}
