"""Educational, monthly budget scenarios. No asset selection or return forecasts.

Monthly decisions follow observed month-end returns and affect the next month.
This engine does not claim the daily execution guarantees of the research lab.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd

ASSET_NAMES = ("Cash", "US large-cap stocks", "Gold", "7–10y Treasury fund")
EXAMPLES = {
    "Savings reference": (1., 0., 0., 0.),
    "More cash": (.65, .15, .05, .15),
    "Mixed example": (.20, .40, .15, .25),
    "More stocks": (.05, .70, .10, .15),
}


@dataclass(frozen=True)
class Budget:
    savings: float = 5000.
    emergency_reserve: float = 2000.
    near_term: float = 1000.
    monthly: float = 200.
    months: int = 60
    goal_today: float = 15000.
    comfortable_dip: float = 1000.

    def validate(self):
        amounts = (self.savings, self.emergency_reserve, self.near_term, self.monthly,
                   self.goal_today, self.comfortable_dip)
        if not np.isfinite(amounts).all() or min(amounts) < 0:
            raise ValueError("Budget amounts must be finite and nonnegative.")
        if not isinstance(self.months, int) or not 1 <= self.months <= 120:
            raise ValueError("Choose a horizon from 1 to 120 months.")

    @property
    def initial(self):
        return max(0., self.savings-self.emergency_reserve-self.near_term)

    @property
    def reserve_gap(self):
        return max(0., self.emergency_reserve+self.near_term-self.savings)

    @property
    def protected_now(self):
        return min(self.savings, self.emergency_reserve+self.near_term)

    def contributions(self, extra_monthly=0.):
        """Fill an unfunded protected-cash target before investing new money."""
        self.validate()
        monthly = self.monthly+extra_monthly
        if not np.isfinite(monthly) or monthly < 0:
            raise ValueError("Monthly contribution cannot be negative.")
        before = np.maximum(self.reserve_gap-np.arange(self.months)*monthly, 0)
        return np.maximum(monthly-before, 0)


@dataclass(frozen=True)
class PlanningSettings:
    paths: int = 800
    block_months: int = 6
    seed: int = 20261022
    cash_rate: float = .03
    inflation: float = .025
    return_haircut: float = 0.
    cost_bps: float = 2.
    band: float = .05
    rebalancing: str = "cash_first_band"

    def validate(self):
        values = (self.cash_rate, self.inflation, self.return_haircut, self.cost_bps, self.band)
        if not np.isfinite(values).all() or not -.05 <= self.cash_rate <= .2 or not 0 <= self.inflation <= .2:
            raise ValueError("Invalid cash/inflation assumptions.")
        if not 0 <= self.return_haircut <= .1 or not 0 <= self.cost_bps <= 100 or not 0 < self.band < .5:
            raise ValueError("Invalid planning cost, band or return adjustment.")
        if not isinstance(self.paths, int) or not 1 <= self.paths <= 5000 or not 1 <= self.block_months <= 24:
            raise ValueError("Invalid scenario count or block length.")
        if self.rebalancing not in ("cash_first_band", "contributions_only"):
            raise ValueError("Unknown monthly rebalancing rule.")


@dataclass
class PlanningResult:
    wealth: np.ndarray
    fees: np.ndarray
    sales: np.ndarray
    selling_months: np.ndarray
    maximum_dip: np.ndarray
    contributed: np.ndarray
    sample_holdings: np.ndarray
    period_unit: str = "Month"
    dates: list[str] | None = None
    nav: np.ndarray | None = None
    return_valid: np.ndarray | None = None
    max_drawdown: np.ndarray | None = None
    fee_path: np.ndarray | None = None
    sample_asset_pnl: np.ndarray | None = None
    sample_path: "PlanningResult | None" = None
    risk_observation: str = "Month-end"
    elapsed_months: np.ndarray | None = None
    drawdown_path: np.ndarray | None = None



def monthly_returns(prices):
    if (not isinstance(prices, pd.DataFrame) or prices.shape[1] not in (3, 4) or prices.index.has_duplicates
            or not prices.index.is_monotonic_increasing or not np.isfinite(prices.to_numpy()).all()
            or (prices <= 0).any().any()):
        raise ValueError("Complete positive asset indices and optional cash proxy are required.")
    levels = prices.resample("ME").last()
    if levels.isna().any().any():
        raise ValueError("A missing month must not be silently filled.")
    return levels.pct_change(fill_method=None).iloc[1:]


def sampled_paths(returns, months, settings):
    """Joint circular monthly blocks. Identical draws are used for every mix."""
    settings.validate()
    x = np.asarray(returns, float)
    if x.ndim != 2 or x.shape[1] not in (3, 4) or len(x) < 24 or not np.isfinite(x).all() or (x <= -1).any():
        raise ValueError("At least 24 complete monthly joint returns are required.")
    if not isinstance(months, int) or not 1 <= months <= 120:
        raise ValueError("Invalid planning horizon.")
    rng = np.random.default_rng(settings.seed)
    # Keep prefixes identical when the user changes only the time horizon.
    starts = rng.integers(0, len(x), (settings.paths, int(np.ceil(120/settings.block_months))))
    indexes = ((starts[:, :, None]+np.arange(settings.block_months)) % len(x)).reshape(settings.paths, -1)[:, :months]
    sampled = np.log1p(x[indexes])
    if x.shape[1] == 4:
        # A common future cash-rate anchor plus historical excess log returns.
        # Do not compare low-rate historical bond total returns with a different
        # future cash rate. The optional premium haircut is a sensitivity only.
        sampled = sampled[:, :, :3]-sampled[:, :, 3:4]+np.log1p(settings.cash_rate)/12
    draws = np.expm1(sampled-settings.return_haircut/12)
    return draws, indexes


def _settle_month(h, flow, a, settings):
    """One net, self-financing trade after a month-end contribution."""
    count, rate = len(h), settings.cost_bps/10000
    total = h.sum(1)+flow
    gaps = np.maximum(total[:, None]*a-h, 0)
    allocation = np.divide(flow*gaps, gaps.sum(1)[:, None], out=np.zeros_like(h),
                           where=gaps.sum(1)[:, None] > 0)
    buys = allocation[:, 1:]/(1+rate)
    next_h = h.copy()
    next_h[:, 0] += flow-buys.sum(1)*(1+rate)
    next_h[:, 1:] += buys
    fees = rate*buys.sum(1)
    sales = np.zeros(count)
    candidate = next_h.sum(1)
    deviations = np.divide(next_h, candidate[:, None], out=np.zeros_like(h),
                           where=candidate[:, None] > 0)-a
    trigger = ((np.abs(deviations).max(1) > settings.band+1e-12) & (total > 0)
               if settings.rebalancing == "cash_first_band" else np.zeros(count, dtype=bool))
    if trigger.any():
        old, capital = h[trigger], total[trigger]
        low, high = np.maximum(capital*(1-2*rate), 0), capital.copy()
        # W + cost*sum(abs(a_risky*W-H_risky)) = pretrade capital.
        for _ in range(36):
            mid = (low+high)/2
            error = mid+rate*np.abs(mid[:, None]*a[1:]-old[:, 1:]).sum(1)-capital
            high = np.where(error > 0, mid, high)
            low = np.where(error <= 0, mid, low)
        target = ((low+high)/2)[:, None]*a
        trades = target[:, 1:]-old[:, 1:]
        next_h[trigger] = target
        fees[trigger] = rate*np.abs(trades).sum(1)
        sales[trigger] = np.maximum(-trades, 0).sum(1)
    if np.any(next_h < -1e-7) or not np.allclose(next_h.sum(1), total-fees, rtol=1e-9, atol=1e-7):
        raise ArithmeticError("Planning cash-flow/fee conservation failed.")
    return next_h, fees, sales


def flow_neutral_step(previous, marked, end, flow, nav, peak, valid):
    """Issue units at pre-flow NAV, then charge fees pro rata to all units.

    A previously empty pot starts at NAV 1 when first funded. Empty periods do
    not create a measured investment return. Initial purchase fees are included.
    """
    previous, marked, end = np.asarray(previous), np.asarray(marked), np.asarray(end)
    funded = (previous > 1e-12) | (np.asarray(flow) > 1e-12)
    market_factor = np.divide(marked, previous, out=np.ones_like(end), where=previous > 1e-12)
    pre_nav = nav*market_factor
    fee_factor = np.divide(end, marked+flow, out=np.ones_like(end), where=marked+flow > 1e-12)
    next_nav = pre_nav*fee_factor
    next_peak = np.where(funded, np.maximum(peak, pre_nav), peak)
    drawdown = np.where(funded, np.maximum(0, 1-next_nav/np.maximum(next_peak, 1e-15)), 0)
    return next_nav, next_peak, valid | funded, drawdown


def simulate_mix(draws, budget, weights, settings, *, extra_monthly=0.):
    """Mark holdings, add cash, then implement a monthly cash-first band rule.

    Dollar dip uses a high-water mark increased by each external deposit, so
    deposits cannot erase an existing investment loss. Cash-rate/inflation are
    user assumptions, not a live deposit product or historical cash total return.
    """
    budget.validate(); settings.validate()
    r, a = np.asarray(draws, float), np.asarray(weights, float)
    if (r.ndim != 3 or r.shape[0] < 1 or r.shape[2] != 3 or not 1 <= r.shape[1] <= budget.months
            or not np.isfinite(r).all() or (r <= -1).any()
            or a.shape != (4,) or not np.isfinite(a).all() or (a < 0).any() or not np.isclose(a.sum(), 1)):
        raise ValueError("Invalid market paths or allocation weights.")
    count, months, _ = r.shape
    rate = settings.cost_bps/10000
    initial_wealth = budget.initial/(1+rate*(1-a[0]))
    h = np.broadcast_to(initial_wealth*a, (count, 4)).copy()
    wealth = np.zeros((count, months+1)); wealth[:, 0] = initial_wealth
    fees = np.full(count, budget.initial-initial_wealth)
    sales, selling = np.zeros(count), np.zeros(count, dtype=int)
    high_water = np.full(count, budget.initial)
    max_dip = np.full(count, budget.initial-initial_wealth)
    sample = np.zeros((months+1, 4)); sample[0] = h[0]
    flows = budget.contributions(extra_monthly)[:months]
    nav = np.ones((count, months+1)); nav[:, 0] = initial_wealth/budget.initial if budget.initial else 1.
    valid = np.zeros((count, months+1), bool); valid[:, 0] = budget.initial > 0
    peak = np.ones(count); max_dd = np.full(count, 1-nav[0, 0] if budget.initial else 0.)
    fee_path = np.zeros((count, months+1)); fee_path[:, 0] = fees
    dd_path = np.zeros_like(wealth); dd_path[:, 0] = max_dd
    asset_pnl = np.zeros((months+1, 4))
    cash_factor = (1+settings.cash_rate)**(1/12)
    for month, flow in enumerate(flows):
        gain = h*np.column_stack([np.full(count, cash_factor-1), r[:, month]])
        asset_pnl[month+1] = asset_pnl[month]+gain[0]
        h += gain
        marked_wealth = h.sum(1)
        h, month_fees, month_sales = _settle_month(h, flow, a, settings)
        end = h.sum(1)
        fees += month_fees; sales += month_sales
        selling += month_sales > 1e-6*np.maximum(marked_wealth, 1)
        high_water = np.maximum(high_water+flow, end)
        max_dip = np.maximum(max_dip, high_water-end)
        nav[:, month+1], peak, valid[:, month+1], dd = flow_neutral_step(
            wealth[:, month], marked_wealth, end, flow, nav[:, month], peak, valid[:, month])
        max_dd = np.maximum(max_dd, dd)
        dd_path[:, month+1] = dd
        fee_path[:, month+1] = fees
        wealth[:, month+1] = end
        sample[month+1] = h[0]
    contributed = budget.initial+np.r_[0., np.cumsum(flows)]
    return PlanningResult(wealth, fees, sales, selling, max_dip, contributed, sample,
                          nav=nav, return_valid=valid, max_drawdown=max_dd,
                          fee_path=fee_path, sample_asset_pnl=asset_pnl, drawdown_path=dd_path)


def replay_daily(prices, budget, weights, settings, start, end):
    """Replay daily close marks with monthly contributions and net trades.

    Adjusted-close ratios represent reinvested return units. With a fourth BIL
    column cash follows that observed proxy; three-column fixtures use the
    constant cash assumption by elapsed calendar days/365.25. No premium
    adjustment is applied to observed risky returns. This is a historical-pattern
    what-if, not a reconstruction of an actual deposit account or intraday lows.
    """
    budget.validate(); settings.validate()
    monthly_returns(prices)  # Validate order, positivity and coverage.
    a = np.asarray(weights, float)
    if a.shape != (4,) or not np.isfinite(a).all() or (a < 0).any() or not np.isclose(a.sum(), 1):
        raise ValueError("Invalid replay allocation weights.")
    start = pd.Timestamp(start)
    end = min(pd.Timestamp(end), start.to_period("M").end_time.normalize()+pd.offsets.MonthEnd(budget.months-1))
    before = prices.index[prices.index < start]
    window = prices.loc[start:end]
    if len(before) == 0 or window.empty:
        raise ValueError("Replay needs an initialization close and at least one session.")
    baseline = before[-1]
    levels = prices.loc[baseline:window.index[-1]]
    days = levels.index
    # Month-end dates come from the full observed trading calendar. A partial
    # replay ending mid-month must not cause an early contribution or trade.
    month_ends = set(prices.groupby(prices.index.to_period("M")).tail(1).index)
    rate = settings.cost_bps/10000
    initial = budget.initial/(1+rate*(1-a[0]))
    h = (initial*a)[None, :]
    wealth, sample, deposited = [initial], [h[0].copy()], [budget.initial]
    fees, sales, selling = np.array([budget.initial-initial]), np.zeros(1), np.zeros(1, dtype=int)
    high_water, max_dip = budget.initial, budget.initial-initial
    flows, flow_index = budget.contributions(), 0
    nav = [initial/budget.initial if budget.initial else 1.]
    valid = [budget.initial > 0]; peak = np.ones(1)
    max_dd = 1-nav[0] if budget.initial else 0.
    fee_path = [fees[0]]; asset_pnl = [np.zeros(4)]; dd_path = [max_dd]
    for i in range(1, len(days)):
        elapsed = (days[i]-days[i-1]).days
        factors = (levels.iloc[i]/levels.iloc[i-1]).to_numpy()
        cash_factor = factors[3] if len(factors) == 4 else (1+settings.cash_rate)**(elapsed/365.25)
        gain = h*(np.r_[cash_factor, factors[:3]]-1)
        asset_pnl.append(asset_pnl[-1]+gain[0])
        h += gain
        marked = h.sum(1)[0]
        # Include the pre-trade close too: depositing or trading cannot conceal
        # a loss that was visible at this close.
        high_water = max(high_water, marked)
        max_dip = max(max_dip, high_water-marked)
        flow = 0.
        if days[i] in month_ends and flow_index < len(flows):
            flow = flows[flow_index]; flow_index += 1
            h, paid, sold = _settle_month(h, flow, a, settings)
            fees += paid; sales += sold
            selling += sold > 1e-6*max(marked, 1)
        value = h.sum(1)[0]
        high_water = max(high_water+flow, value)
        max_dip = max(max_dip, high_water-value)
        next_nav, peak, next_valid, dd = flow_neutral_step(
            np.array([wealth[-1]]), np.array([marked]), np.array([value]), flow,
            np.array([nav[-1]]), peak, np.array([valid[-1]]))
        nav.append(next_nav[0]); valid.append(bool(next_valid[0])); max_dd = max(max_dd, dd[0])
        fee_path.append(fees[0]); dd_path.append(dd[0])
        wealth.append(value); sample.append(h[0].copy()); deposited.append(deposited[-1]+flow)
    return PlanningResult(np.array([wealth]), fees, sales, selling, np.array([max_dip]),
                          np.array(deposited), np.array(sample), "Session", [str(d.date()) for d in days],
                          nav=np.array([nav]), return_valid=np.array([valid]), max_drawdown=np.array([max_dd]),
                          fee_path=np.array([fee_path]), sample_asset_pnl=np.array(asset_pnl), risk_observation="Daily-close", drawdown_path=np.array([dd_path]))


def describe_result(result, budget, settings):
    if result.period_unit != "Month":
        raise ValueError("Monthly scenario summaries cannot interpret a daily replay as months.")
    terminal = result.wealth[:, -1]
    deflator = (1+settings.inflation)**((result.wealth.shape[1]-1)/12)
    summary = {"ending_low_today": float(np.quantile(terminal, .1)/deflator),
        "ending_middle_today": float(np.quantile(terminal, .5)/deflator),
        "ending_high_today": float(np.quantile(terminal, .9)/deflator),
        "ending_below_deposits_frequency": float(np.mean(terminal < result.contributed[-1]-1e-7)),
        "dip_exceeds_comfort_frequency": float(np.mean(result.maximum_dip > budget.comfortable_dip+1e-7)),
        "dip_90_nominal": float(np.quantile(result.maximum_dip, .9)),
        "median_fees": float(np.median(result.fees)), "median_selling_months": float(np.median(result.selling_months)),
        "total_deposits_nominal": float(result.contributed[-1])}
    if result.nav is not None:
        mask = result.return_valid[:, -1]
        summary["median_twr"] = float(np.median(result.nav[mask, -1]-1)) if mask.any() else None
        summary["drawdown_90"] = float(np.quantile(result.max_drawdown[mask], .9)) if mask.any() else None
        summary["median_net_pnl"] = float(np.median(terminal-result.contributed[-1]))
    if budget.goal_today > 0:
        summary["goal_frequency"] = float(np.mean(terminal/deflator >= budget.goal_today))
    return summary
