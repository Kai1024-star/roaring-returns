"""Self-financing convex execution-risk planning with explicit proportional costs.

This is a finite-scenario application, not a reproduction of OT-DRO or DFL.
All trades are frozen dollars at the signal close; no recourse uses fill prices.
"""

from dataclasses import dataclass
import numpy as np
from .policies import validate_inputs, project_box_simplex


@dataclass(frozen=True)
class OptimizerSettings:
    band: float = .05
    cost_bps: float = 2.
    turnover_penalty: float = .002
    tail_weight: float = .5
    tail_level: float = .90
    risk_measure: str = "cvar"
    tail_budget: float = .0005
    tail_slack_penalty: float = 50.

    def validate(self):
        values = (self.band, self.cost_bps, self.turnover_penalty, self.tail_weight, self.tail_level,
                  self.tail_budget, self.tail_slack_penalty)
        if not np.isfinite(values).all() or not 0 <= self.band < 1 or not 0 <= self.cost_bps < 10000:
            raise ValueError("Invalid band or transaction costs.")
        if self.turnover_penalty <= 0 or self.tail_weight < 0 or not 0 <= self.tail_level < 1:
            raise ValueError("Invalid optimization penalties.")
        if self.risk_measure not in ("cvar", "worst_case"):
            raise ValueError("Unknown scenario risk measure.")
        if self.tail_budget < 0 or self.tail_slack_penalty <= 0:
            raise ValueError("Invalid tail budget or slack penalty.")


@dataclass(frozen=True)
class OptimizationPlan:
    trades: np.ndarray
    status: str
    objective: float
    tracking_loss: float
    turnover_fraction: float
    tail_loss: float
    modeled_fee: float
    budget_residual: float
    scenario_weights: np.ndarray
    scenario_excess_pp: np.ndarray
    solve_seconds: float
    objective_name: str = "tracking_cvar"
    risk_slack: float = 0.
    solver_trace: str = "CLARABEL"
    tie_break_completed: bool = True


def buffered_minimum_sale(holdings, cash, contribution, target, band, covariance, z=1.65):
    """First-order, per-asset lag buffer; not a joint coverage guarantee.

    With close-of-next-session dollar fills, lag returns act on ORIGINAL
    holdings. The Jacobian is diag(H/S)-a(H/S)^T, not diag(a)-aa^T.
    Costs are left to the common fill engine, as for the static minimum-sale rule.
    """
    h, a = validate_inputs(holdings, cash, target)
    covariance = np.asarray(covariance, float)
    if (not np.isfinite([contribution, band, z]).all() or contribution < 0
            or not 0 <= band < 1 or z < 0 or covariance.shape != (len(h), len(h))
            or not np.isfinite(covariance).all()):
        raise ValueError("Invalid analytic buffer settings.")
    total = float(h.sum()+cash+contribution)
    pre = h/total
    jacobian = np.diag(pre)-np.outer(a, pre)
    variance = np.diag(jacobian@covariance@jacobian.T)
    if variance.min() < -1e-10:
        raise ValueError("Invalid covariance matrix.")
    delta = np.minimum(z*np.sqrt(np.maximum(variance, 0)), .8*band)
    lo, hi = np.maximum(a-band+delta, 0), np.minimum(a+band-delta, 1)
    forced = np.maximum(h-hi*total, 0).sum()
    required = np.maximum(lo*total-h, 0).sum()
    if forced >= required-(cash+contribution):
        lo = np.maximum(lo, np.minimum(h/total, hi))
    else:
        hi = np.minimum(hi, np.maximum(h/total, lo))
    final = total*project_box_simplex(a, lo, hi)
    return final-h, delta


def finite_cvar(losses, level=.9):
    """Exact equal-probability discrete CVaR, including fractional tail mass."""
    x = np.asarray(losses, float)
    if x.ndim != 1 or not len(x) or not np.isfinite(x).all() or not 0 <= level < 1:
        raise ValueError("Invalid finite loss distribution.")
    mass = (1-level)*len(x)
    ordered = np.sort(x)[::-1]
    whole = min(int(np.floor(mass+1e-12)), len(x))
    partial = max(0., mass-whole)
    return float((ordered[:whole].sum()+(partial*ordered[whole] if whole < len(x) else 0))/mass)


def optimize_execution(holdings, cash, contribution, target, scenarios,
                       settings=OptimizerSettings()):
    import cvxpy as cp

    settings.validate()
    h, a = validate_inputs(holdings, cash, target)
    shocks = np.asarray(scenarios, float)
    if shocks.ndim != 2 or shocks.shape[1] != len(h) or not len(shocks):
        raise ValueError("A nonempty scenario-by-asset matrix is required.")
    if not np.isfinite(shocks).all() or np.any(shocks <= -1) or not np.isfinite(contribution) or contribution < 0:
        raise ValueError("Invalid scenarios or external contribution.")
    capital = float(h.sum()+cash+contribution)
    normalized = h/capital
    available = (cash+contribution)/capital
    rate = settings.cost_bps/10000
    count, assets = shocks.shape
    buys, sells = cp.Variable(assets, nonneg=True), cp.Variable(assets, nonneg=True)
    gross = cp.sum(buys+sells)
    fee = rate*gross
    final = (1+shocks)*normalized + cp.reshape(buys-sells, (1, assets), order="C")
    wealth = cp.sum(final, axis=1)
    deviation = final-cp.reshape(wealth, (count, 1), order="C")@a.reshape(1, assets)
    tracking = cp.sum_squares(deviation)/count
    # A hard self-financing constraint anticipates the same fees as the fill
    # engine. There is no deliberate residual cash target or round-trip order.
    constraints = [cp.sum(buys-sells)+fee == available,
                   sells <= np.minimum(normalized, np.min((1+shocks)*normalized, axis=0)),
                   wealth >= 1e-6]
    excess = cp.Variable(count, nonneg=True)
    for i in range(assets):
        constraints += [excess >= deviation[:, i]-settings.band*wealth,
                        excess >= -deviation[:, i]-settings.band*wealth]
    if settings.risk_measure == "cvar":
        eta = cp.Variable(nonneg=True)
        tail = eta + cp.sum(cp.pos(excess-eta))/((1-settings.tail_level)*count)
    else:
        tail = cp.max(excess)
    problem = cp.Problem(cp.Minimize(tracking+settings.turnover_penalty*gross+settings.tail_weight*tail), constraints)
    problem.solve(solver="CLARABEL", tol_gap_abs=1e-9, tol_feas=1e-9, tol_gap_rel=1e-8, max_iter=250)
    if problem.status != cp.OPTIMAL:
        raise ArithmeticError(f"Convex planning did not reach optimal status: {problem.status}")
    raw_buys = np.maximum(np.asarray(buys.value), 0)
    raw_sells = np.maximum(np.asarray(sells.value), 0)
    # Positive turnover penalty makes genuine simultaneous purchases/sales
    # suboptimal. Reject a material numerical round trip, net only roundoff.
    if np.max(np.minimum(raw_buys, raw_sells)) > 1e-6:
        raise ArithmeticError("Solver returned a material round-trip trade.")
    trades = (raw_buys-raw_sells)*capital
    actual_gross = float(np.abs(trades).sum())
    modeled_fee = rate*actual_gross
    residual = float(cash+contribution-trades.sum()-modeled_fee)
    if abs(residual) > 2e-6*capital:
        raise ArithmeticError("Planned fees and budget disagree.")
    scenario_h = (1+shocks)*h+trades
    scenario_wealth = scenario_h.sum(axis=1)
    scenario_weights = scenario_h/scenario_wealth[:, None]
    loss = np.maximum(np.max(np.abs(scenario_h-scenario_wealth[:, None]*a), axis=1)
                      -settings.band*scenario_wealth, 0)/capital
    tail_value = finite_cvar(loss, settings.tail_level) if settings.risk_measure == "cvar" else float(loss.max())
    track_value = float(np.mean(np.sum(((scenario_h-scenario_wealth[:, None]*a)/capital)**2, axis=1)))
    turnover = actual_gross/capital
    return OptimizationPlan(trades, problem.status,
                            track_value+settings.turnover_penalty*turnover+settings.tail_weight*tail_value,
                            track_value, turnover, tail_value, modeled_fee, residual,
                            scenario_weights, np.maximum(np.max(np.abs(scenario_weights-a), axis=1)-settings.band, 0)*100,
                            float(problem.solver_stats.solve_time or 0))


def optimize_minimum_sale(holdings, cash, contribution, target, scenarios,
                          settings=OptimizerSettings(), *, hard_risk=False):
    """Minimize sales plus explicit risk-budget slack, then tracking error.

    First stage is an LP with CVaR (or worst-case) band-excess budget. The second
    stage uniquely selects net trades near the target within numerical tolerance
    of the first objective. Hard-risk mode is for feasibility/mechanism checks;
    the study uses a soft budget so infeasible designed shocks remain visible.
    """
    import cvxpy as cp

    settings.validate()
    h, a = validate_inputs(holdings, cash, target)
    r = np.asarray(scenarios, float)
    if (r.ndim != 2 or r.shape[1] != len(h) or not len(r) or not np.isfinite(r).all()
            or np.any(r <= -1) or not np.isfinite(contribution) or contribution < 0):
        raise ValueError("Invalid execution scenarios or external contribution.")
    total = float(h.sum()+cash+contribution)
    rate = settings.cost_bps/10000
    m, n = r.shape
    buys, sells = cp.Variable(n, nonneg=True), cp.Variable(n, nonneg=True)
    gross = cp.sum(buys+sells)
    final = (1+r)*(h/total)+cp.reshape(buys-sells, (1, n), order="C")
    wealth = cp.sum(final, axis=1)
    deviation = final-cp.reshape(wealth, (m, 1), order="C")@a.reshape(1, n)
    loss = cp.Variable(m, nonneg=True)
    constraints = [cp.sum(buys-sells)+rate*gross == (cash+contribution)/total,
                   sells <= np.minimum(h/total, np.min((1+r)*(h/total), axis=0)), wealth >= 1e-6]
    for j in range(n):
        constraints += [loss >= deviation[:, j]-settings.band*wealth,
                        loss >= -deviation[:, j]-settings.band*wealth]
    if settings.risk_measure == "cvar":
        eta = cp.Variable(nonneg=True)
        tail = eta+cp.sum(cp.pos(loss-eta))/((1-settings.tail_level)*m)
    else:
        tail = cp.max(loss)
    slack = cp.Variable(nonneg=True)
    if hard_risk and settings.tail_budget == 0:
        # This exact limit reduces to hard scenario bands and avoids degenerate
        # zero-CVaR epigraph variables in the tie-break QP.
        constraints.append(loss == 0)
    else:
        constraints.append(tail <= settings.tail_budget+slack)
    if hard_risk:
        constraints.append(slack == 0)
    primary = cp.sum(sells)+settings.tail_slack_penalty*slack
    first = cp.Problem(cp.Minimize(primary), constraints)
    options = dict(solver="CLARABEL", tol_gap_abs=1e-9, tol_feas=1e-9, tol_gap_rel=1e-8, max_iter=250)
    first.solve(**options)
    if first.status != cp.OPTIMAL:
        raise ArithmeticError(f"Minimum-sale risk LP status: {first.status}")
    first_buys = np.maximum(np.asarray(buys.value), 0).copy()
    first_sells = np.maximum(np.asarray(sells.value), 0).copy()
    # Read the feasible primal objective rather than a slightly negative solver
    # bound at a zero-sale optimum. Keep this solution before a second solve can
    # clear all CVXPY variable values on an infeasible/inaccurate status.
    optimum = float(first_sells.sum()+settings.tail_slack_penalty*max(float(slack.value), 0.))
    zero_sale_face = optimum < 1e-8
    # A fixed normalized tolerance is auditable and preserves funding-scale
    # invariance. It is not an exact symbolic lexicographic optimum.
    constraints.append(primary <= optimum+1e-6)
    if zero_sale_face:
        constraints += [sells == 0, slack == 0]
    else:
        # Tracking must not spend the primary tolerance on extra micro-sales.
        # Preserve the LP's sales/slack decomposition up to solver roundoff.
        constraints += [cp.sum(sells) <= first_sells.sum()+1e-9,
                        slack <= max(float(slack.value), 0.)+1e-10]
    second = cp.Problem(cp.Minimize(cp.sum_squares(deviation)/m+1e-8*gross), constraints)
    import warnings
    solver_trace = "CLARABEL"
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Solution may be inaccurate")
        try:
            second.solve(**options)
        except cp.error.SolverError:
            pass
    if second.status != cp.OPTIMAL:
        # Retry the same mathematical QP with another open-source solver. Never
        # silently substitute a trading policy; the retry is recorded explicitly.
        try:
            second.solve(solver="OSQP", eps_abs=1e-8, eps_rel=1e-8, max_iter=100000, polishing=True)
        except cp.error.SolverError:
            pass
        solver_trace = "CLARABEL -> OSQP tie-break retry"
    tie_completed = second.status == cp.OPTIMAL
    if tie_completed:
        b, s = np.maximum(np.asarray(buys.value), 0), np.maximum(np.asarray(sells.value), 0)
    else:
        # Preserve the optimal first-stage policy, not an alternative trading
        # rule. Funding, holdings, realized scenario risk, and primary optimality
        # are rechecked below. The target-nearest tie-break was NOT completed.
        b, s = first_buys, first_sells
        solver_trace += f" -> LP-only fallback ({second.status})"
    if np.max(np.minimum(b, s)) > 1e-6:
        raise ArithmeticError("Minimum-sale solver returned a material round trip.")
    trades = (b-s)*total
    if zero_sale_face and tie_completed:
        # Remove equality-constrained roundoff without inventing a minimum trade
        # size. Reallocate purchases on exactly the same buy-only funding face.
        trades = np.maximum(trades, 0)
        buy_total = (cash+contribution)/(1+rate)
        if trades.sum() > 0:
            trades *= buy_total/trades.sum()
        elif buy_total > 1e-8*total:
            raise ArithmeticError("Buy-only optimal face lost funded purchases.")
    fee = rate*float(np.abs(trades).sum())
    residual = float(cash+contribution-trades.sum()-fee)
    if abs(residual) > 2e-6*total:
        raise ArithmeticError("Minimum-sale fee budget failed.")
    scenario_h = (1+r)*h+trades
    scenario_wealth = scenario_h.sum(axis=1)
    if np.min(scenario_h) < -2e-6*total or np.min(scenario_wealth) < 1e-6*total-2e-6:
        raise ArithmeticError("Minimum-sale scenario holdings failed feasibility checks.")
    scenario_w = scenario_h/scenario_wealth[:, None]
    deviations = (scenario_h-scenario_wealth[:, None]*a)/total
    losses = np.maximum(np.max(np.abs(deviations), axis=1)-settings.band*scenario_wealth/total, 0)
    tail_value = finite_cvar(losses, settings.tail_level) if settings.risk_measure == "cvar" else float(losses.max())
    risk_slack = max(0., tail_value-settings.tail_budget)
    objective = float(np.maximum(-trades, 0).sum()/total+settings.tail_slack_penalty*risk_slack)
    if objective > optimum+5e-6 or (hard_risk and risk_slack > 2e-6):
        raise ArithmeticError("Minimum-sale primary/risk objective failed numerical checks.")
    return OptimizationPlan(trades, "optimal" if tie_completed else "optimal_lp_only", objective,
        float(np.mean(np.sum(deviations**2, axis=1))), float(np.abs(trades).sum()/total),
        tail_value, fee, residual, scenario_w,
        np.maximum(np.max(np.abs(scenario_w-a), axis=1)-settings.band, 0)*100,
        float((first.solver_stats.solve_time or 0)+
              ((second.solver_stats.solve_time or 0) if second.solver_stats else 0)),
        "minimum_sale_risk_budget", risk_slack, solver_trace, tie_completed)
