# Cash-flow allocation mathematics

The results below concern a single fixed-price state, fractional units, and no
fees, tax, borrowing, or short sales. They do not guarantee a delayed fill or
minimize cumulative selling over future portfolio paths.

## Exact target with purchases only

Let H_i be nonnegative dollar asset holdings, K nonnegative uninvested cash,
W = sum(H_i) + K, and C an external contribution. Target weights a_i > 0 sum to
one. Final target holdings are a_i(W+C), so required net purchases are
b_i = a_i(W+C) - H_i. These sum to K+C. Purchases alone reach the target iff
all b_i >= 0, equivalently

    C_min = max(0, max_i(H_i/a_i) - W).

For target 40/30/30, holdings 45/25/30, and K=0, C_min/W=12.5%.
A tolerance band can need much less cash than exact restoration.

## Closest target attainable without selling

For available cash A=K+C, total T=sum(H_i)+A, minimize squared allocation
deviation subject to b_i>=0 and sum(b_i)=A. With g_i=a_i*T-H_i, the solution is

    b_i = max(0, g_i-tau),  with sum(b_i)=A.

This is a Euclidean simplex projection. The common multiplier tau and active
zero-purchase constraints follow from the Lagrange/KKT conditions. Code uses a
box-simplex projection; tests also compare with an independent QP formulation.

## Minimum sales to reach a band

Let 0<=L_i<=U_i<=1, sum(L_i)<=1<=sum(U_i), and T=sum(H_i)+A. Define

    F = sum(max(H_i-U_i*T, 0))
    B = sum(max(L_i*T-H_i, 0))
    S_min = max(F, B-A, 0).

Positions above upper limits force F dollars of sales. Lower-limit purchases
need B dollars financed by A plus selling, yielding the second lower bound.

To prove attainability, clip holdings into the band:
Y_i=clip(H_i,L_i*T,U_i*T). This sells F and buys B, with remaining funding
Delta=T-sum(Y_i)=A+F-B. If Delta>=0, upper-bound capacity accommodates additional
purchases without additional sales. If Delta<0, lower-bound slack accommodates
additional sales of -Delta, without reversing forced purchases. The two cases
attain F and B-A respectively. Thus the bound is exact.

Buy-only band restoration is possible iff F=0 and B<=A. Checking upper limits
alone misses possible lower-limit funding needs.

Among minimum-sale allocations, minimize sum((X_i-a_i*T)^2) to specify a unique
final holding vector. The feasible set (box, budget, convex sales sublevel)
is convex, and this objective is strictly convex. Independent LP/QP checks in
the test suite validate both stages. This is not a novelty claim.

## Return-dispersion identity and denominator

If an account starts exactly at target with wealth W0, no cash, and asset simple
returns r_i, let r_p=sum(a_i*r_i) and W=W0*(1+r_p)>0. Then

    C_min = W0*(max(r_i)-r_p)
    C_min/W = (max(r_i)-r_p)/(1+r_p).

Only C/W0 uses the unscaled max-excess-return threshold. Drift carried from
previous months breaks the reset-to-target premise. This identity has not yet
been developed into a calibrated empirical forecasting result.

## Implementation boundary

The Python engine plans from a completed close and fills frozen dollar orders
at the following session's close. Its positions can move before execution.
Fees also change feasible purchases. Consequently, the theorem is checked at
the signal state; actual post-trade compliance is measured separately.
Whole-share and distribution-payment-date accounting require another data and
execution model. They are not represented by rounding total-return indices.
