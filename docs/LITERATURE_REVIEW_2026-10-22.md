# Optimization, machine learning, and portfolio research: reading guide

Screened on **22 October 2026** for the personal Python Roaring Returns project.
This is a curated starting point, not an exhaustive review or a ranking of all
optimization research. Publication status and repository instructions can change.

Codex checked primary author, proceedings, journal, arXiv, and official repository
sources, downloaded ten public manuscripts, and inspected selected methods,
experiments, and limitations. Claude supplied a separate shortlist and challenged
the project fit. Neither assistant reproduced these papers' numerical results in
this screening. Claude explicitly limited its first pass to metadata, abstracts,
and repository descriptions. These are AI-assisted reading notes, not peer review.

## Start here

1. **Markowitz Portfolio Construction at Seventy (2024):** learn how practical
   constraints, uncertainty, and trading costs enter a convex portfolio model.
2. **Simple Dynamic Stock/Bond/Gold Portfolios (September 2026 manuscript):**
   inspect a recent, small-universe study with public data and author code.
3. **Multi-Period Trading via Convex Optimization (2017):** read the planning and
   execution framework before adding machine learning.
4. **Return Prediction for Mean-Variance Portfolio Selection (ICAIF 2025)** and
   the **DFL survey (JAIR 2024):** understand what a decision loss changes, and
   what it does not guarantee.
5. Choose one research branch: **learned robustness** (Costa/Iyengar and Ohnemus
   et al.), or **differentiable optimization/multi-period learning** (Healey et al.
   and IPMO). Do not implement all branches at once.

The newest paper is not automatically the best first paper. Current Roaring
Returns studies execution toward a fixed target with external contributions;
return forecasting and choosing dynamic targets introduce different questions.

## Eight selected papers

### 1. Simple Dynamic Stock/Bond/Gold Portfolios

**Nikhil Devanathan, Alexandros E. Tzikas, Stephen P. Boyd.** Author page labels
this a **September 2026 manuscript**; the retrieved PDF cover is dated September
7, 2026. Do not describe it as a peer-reviewed journal article.

[Author page](https://web.stanford.edu/~boyd/papers/stock_bond_gold_portfolios.html)
| [Public PDF](https://web.stanford.edu/~boyd/papers/pdf/stock_bond_gold_portfolios.pdf)
| [Author code](https://github.com/cvxgrp/simple-portfolio-code)

The study uses SPY/AGG/GLD plus cash, monthly trading, volatility control, and
convex portfolio construction. Its small asset universe makes the model unusually
easy to connect to our project. Start with section 2, appendix A accounting, and
the sensitivity analyses. Public data and runnable-looking instructions are a
promising starting point, not evidence that we have reproduced its results.

**Project fit:** a separate dynamic-allocation replication track. Its target
selection objective differs from our fixed-target drift-versus-selling objective;
the assets, execution timing, contributions, and performance definitions must be
aligned before comparing strategies. Section 2.5 specifies a January 2006 to
January 2026 evaluation interval; this does not include the full 2026 year.

**Access:** paper and code obtained without a university login. The official
workflow requires a FRED key in `keys/fred_api.key`. Data acquisition and all
scripts remain untested here. Keep keys outside version control.

### 2. Markowitz Portfolio Construction at Seventy

**Stephen Boyd, Kasper Johansson, Ronald Kahn, Philipp Schiele, Thomas Schmelzer.**
**Journal of Portfolio Management 50(8), 117-160, July 2024.**

[Author page](https://web.stanford.edu/~boyd/papers/markowitz.html)
| [Public author PDF](https://web.stanford.edu/~boyd/papers/pdf/markowitz.pdf)
| [Reference implementation](https://github.com/cvxgrp/markowitz-reference)

This is a practical bridge from mean-variance calculus to constrained portfolio
construction with costs and uncertain inputs. Read the problem specification and
cost/robustness modeling before the full experiment. It helps us design a
cost-aware optimization comparator rather than adding more ad hoc trading rules.

**Access:** the author manuscript is free. The reference repository supplies
obfuscated ticker data under provider restrictions. Its original experiments
assume a valid MOSEK license; the current environment also lists Clarabel, but
solver substitution is not verified. A personal academic MOSEK license is an
option; raw identifiable vendor data are not implicitly licensed for redistribution.

### 3. Decision-Focused Learning: Foundations, State of the Art, Benchmark and Future Opportunities

**Jayanta Mandi, James Kotary, Senne Berden, Maxime Mulamba, Victor Bucarey, Tias
Guns, Ferdinando Fioretto. JAIR, 2024. DOI: 10.1613/jair.1.15320.**

[Journal page](https://jair.org/index.php/jair/article/view/15320)
| [Journal PDF](https://jair.org/index.php/jair/article/download/15320/27076/40841)
| [arXiv v4](https://arxiv.org/abs/2307.13565v4)
| [Official benchmark](https://github.com/PredOpt/predopt-benchmarks)

Use this as a map of ways to train for downstream decisions rather than only
prediction error. The survey evaluates eleven methods on seven problems and
includes portfolio optimization. Start with the problem formulation and method
taxonomy, then follow the portfolio benchmark. It is a survey, not a 2026 method.

**Access:** full text and code are public; the repository recommends an old
Python environment. Do not merge those dependencies into our research environment
without isolating and testing them.

**Metadata discrepancy:** the journal landing page and repository say volume 80
and August 31, 2024; the journal's own downloaded PDF says volume 81 and published
September 2024. These notes use the DOI and year rather than silently selecting
one conflicting volume/date. arXiv began in 2023, which is not the journal year.

### 4. Loss-Aware Distributionally Robust Optimization via Trainable Optimal Transport Ambiguity Sets

**Jonas Ohnemus, Marta Fochesato, Riccardo Zuliani, John Lygeros. ICML 2026,
PMLR 306, 94344-94382.** The earlier arXiv manuscript appeared in September 2025.

[Official proceedings](https://proceedings.mlr.press/v306/ohnemus26a.html)
| [Final PDF](https://raw.githubusercontent.com/mlresearch/v306/main/assets/ohnemus26a/ohnemus26a.pdf)
| [Author code](https://github.com/JonasOhn/trainable-ot-dro)

This is the most useful selected example of a recent optimization/ML method:
learn the shape of an optimal-transport uncertainty set using the decision loss,
rather than fixing its geometry before optimization. Read sections 3-6 and the
limitations in section 7. The formal guarantee concerns convergence to a critical
point, not a global optimum or guaranteed investment returns.

**Important limit:** the final paper explicitly states that its experiments are
synthetic, including Gaussian, discrete, and Gaussian-mixture portfolio cases.
It does not establish real-market alpha. Section 7 explicitly lacks a theoretical
guarantee for coverage of the true distribution; coverage is encouraged by a
bootstrap procedure. Treat this as a mechanism to investigate.

**Access:** final paper and Python implementation are public. The code link is
inside the final PDF and was initially missed when screening the abstract page;
it has now been verified. README lists Python >=3.10, CVXPY, POT, and Clarabel.
No commercial market dataset is needed for the synthetic examples. Installation,
licensing details beyond the README's MIT statement, and reproduction are untested.

### 5. Differentiating Through a Quadratic Cone Program

**Quill Healey, Parth Nobel, Stephen Boyd. Optimization Letters, May 2026**
according to the author's final-version page.

[Author page](https://web.stanford.edu/~boyd/papers/diff_quad_cone_prog.html)
| [Public final PDF](https://web.stanford.edu/~boyd/papers/pdf/diff_quad_cone_prog.pdf)
| [diffqcp](https://github.com/cvxgrp/diffqcp)

This addresses derivatives of an optimizer's solution with respect to its inputs,
using implicit differentiation for quadratic cone programs. It is a useful
optimization-method paper if we eventually train through a convex allocation
layer. Read the differentiability assumptions before the CPU/GPU benchmarks.

**Project fit:** a later tool/method track, not a requirement for three-asset
buy-only projection. A small active-set calculation and finite differences provide
a more transparent initial gradient check.

**Access and readiness:** paper and JAX code are public, with CPU support. At
screening, README says its default LSMR path needs source-version `lineax`, and
direct-solve gradient behavior is still being debugged. Pin versions and validate
gradients before relying on it. No GPU purchase is needed to start reading or
working on small examples.

### 6. Distributionally Robust End-to-End Portfolio Construction

**Giorgio Costa and Garud N. Iyengar. Quantitative Finance 23(10), 1465-1482,
2023.** The accessible arXiv manuscript is the June 2022 v1, not a verified copy
of the final typeset journal article.

[Author publication list](https://gcosta151.github.io/)
| [Public manuscript](https://arxiv.org/abs/2206.05134)
| [Columbia Iyengar Lab code](https://github.com/Iyengar-Lab/E2E-DRO)

This connects return prediction, a robust decision layer, and learning risk
tolerance/robustness parameters. It is older than the newest candidates but
particularly valuable for understanding the ML/DRO bridge and a nearby Columbia
research group. Compare nominal, robust, and end-to-end models separately.

**Access:** reading and source code do not need Columbia login. The data module
contains Kenneth French and AlphaVantage routes; `main.py`'s historical experiment
uses AlphaVantage or cached data, and its comments require an academic or paid
license for adjusted prices. Current access must be checked before fetching;
an API key alone is not proof of entitlement. Code/environment compatibility has
not been tested. No cached Python pickle has been loaded or executed.

### 7. Return Prediction for Mean-Variance Portfolio Selection: How Decision-Focused Learning Shapes Forecasting Models

**Junhyeong Lee, Haeun Jeon, Hyunglip Bae, Yongjae Lee. ICAIF 2025, 114-122,
published November 14, 2025. DOI: 10.1145/3768292.3770423.** arXiv v4 is November
9, 2025; the first preprint was September 2024.

[ACM publication](https://doi.org/10.1145/3768292.3770423)
| [Public arXiv v4](https://arxiv.org/abs/2409.09684v4)

A short mechanistic paper: decision training can reshape return predictions rather
than simply reduce MSE. Useful for a small analytical experiment and for asking
whether learned inputs remain interpretable as calibrated return forecasts.

**Caution:** its inverse-covariance gradient explanation is derived for an
unconstrained problem. Budget constraints change the sensitivity matrix;
nonnegativity requires active-set treatment. Do not transfer that expression
unchanged to our constrained problem or treat reported performance as guaranteed.

**Access:** nine-page arXiv PDF obtained; ACM's indexed publication page is labeled
open access although direct automated retrieval returned 403. That is a retrieval
limitation, not evidence that a subscription is needed. An official implementation
was not verified in this screening; a from-scratch mechanism experiment is possible.

### 8. Integrated Prediction and Multi-period Portfolio Optimization

**Yuxuan Linghu, Zhiyuan Liu, Qi Deng. arXiv:2512.11273v3, revised September 9,
2026; first posted December 2025.** No accepted venue verified in this screening.

[Versioned preprint](https://arxiv.org/abs/2512.11273v3)
| [Full HTML](https://arxiv.org/html/2512.11273v3)

This combines multi-period forecasts, turnover penalties, a convex decision layer,
and mirror-descent fixed-point differentiation. It is a close recent direction to
watch, after learning the simpler multi-period framework. Read sections 3-5 and
the precise forward/backward dependency structure, not only the return tables.

**Limits and access:** the manuscript is free; official code was not verified.
The final downloaded v3 has 25 PDF pages despite the arXiv metadata saying 23.
It contains seven-ETF experiments and an added 100-stock CRSP experiment. Exact
replication of the latter requires licensed CRSP data and the authors' selection
and timing details. Its claims should not be treated as an independently replicated
result. A surrogate ETF experiment is an adaptation, not exact reproduction.

## Two older foundations worth keeping

- **Boyd et al., Multi-Period Trading via Convex Optimization (2017), Foundations
  and Trends in Optimization 3(1), 1-76.**
  [Author page](https://web.stanford.edu/~boyd/papers/cvx_portfolio.html),
  [public manuscript](https://web.stanford.edu/~boyd/papers/pdf/cvx_portfolio.pdf),
  [cvxportfolio](https://www.cvxportfolio.com/).
  Plan several periods, implement the first action, then replan. Directly useful
  for separating a policy's objective from the quality of its forecasts.
- **Agrawal et al., Differentiable Convex Optimization Layers (NeurIPS 2019).**
  [Author page](https://web.stanford.edu/~boyd/papers/diff_cvxpy.html),
  [public PDF](https://web.stanford.edu/~boyd/papers/pdf/diff_cvxpy.pdf),
  [cvxpylayers](https://github.com/cvxpy/cvxpylayers).
  Read before newer differentiable solver papers; a general method, not a
  portfolio alpha study.

## Additional candidates, screened more lightly

| Candidate | Why retain it | Important qualification |
| --- | --- | --- |
| [DF2: Distribution-Free Decision-Focused Learning, UAI 2025](https://proceedings.mlr.press/v286/kong25a.html) | Alternative decision-learning formulation; [author code](https://github.com/Lingkai-Kong/DF2) | Repository examples are synthetic, wind, and inventory; adapting to portfolios is additional work. |
| [Cost-aware Portfolios in a Large Universe of Assets, arXiv:2412.11575v2, August 2025](https://arxiv.org/abs/2412.11575v2) | High-dimensional estimation plus trading costs | Working paper on the checked author page; less relevant to a three-ETF problem. Official code/data access not established here. |
| [PyEPO, Mathematical Programming Computation, 2024](https://arxiv.org/abs/2206.14234) | Python implementation resource for predict-then-optimize | [Current main](https://github.com/khalil-research/PyEPO) differs from the paper; original experiments use the MPC branch. Solver requirements vary. |
| [The Unintended Consequences of Rebalancing, NBER WP 33554, March 2025 / revised January 2026](https://www.nber.org/papers/w33554) | Institutional rebalancing and price impact | Metadata/abstract verified; NBER direct retrieval returned 403 and this paper was not downloaded. Full latest text and data availability remain unresolved. Do not extrapolate institutional impact estimates to a small retail account. |

## Human intervention: what is actually needed

**Nothing is currently needed to read the ten downloaded manuscripts.** We did
not log into university services, create accounts, obtain keys, or buy data.

| If we choose this next step | Human step / actual limitation |
| --- | --- |
| Run the 2026 stock/bond/gold author's complete data workflow | Create/login to a [FRED account and request an API key](https://fred.stlouisfed.org/docs/api/api_key.html). Store it locally, not in chat or Git. |
| Reproduce the original Markowitz reference experiments with MOSEK | Apply using academic email for a [personal academic license](https://www.mosek.com/products/academic-licenses/); research/educational use and eligibility apply. |
| Re-fetch the Costa/Iyengar AlphaVantage adjusted-price dataset | Verify current provider entitlements and obtain the appropriate key/license. The repository's historical comments are not a current pricing guarantee. |
| Reproduce IPMO's CRSP stock-universe experiment, or audit our Yahoo data against a second source | Use Columbia's [WRDS access guide](https://guides.library.columbia.edu/WRDS/overview) and [subscription guide](https://guides.library.columbia.edu/WRDS/collection). Columbia lists CRSP, but the exact tables and endpoint dates must be checked after login. Master's/PhD and undergraduate access differ; undergraduates generally use designated library workstations unless eligible as an RA. |
| Obtain a publisher-specific final version or unresolved NBER revision | Try author/open versions first. If still needed, use Columbia library access; a server 403 alone does not establish a paywall. |

No author code availability issue can be solved merely by university login. When
code is not verified, the options are a transparent reimplementation or an explicit
request to the authors, not assuming it exists behind a library subscription.

## Proposed connection to our next research stage

The closest next question is: **With fixed targets and monthly contributions, how
should trades account for the price uncertainty between signal and execution?**
Our current signal-price minimum-sale result is static and does not ensure the
filled portfolio remains in band. Scenario or robust optimization could study
that gap while retaining the existing objective. This is a proposal to test,
not a claim of a new theorem or a successful method.

First construct a transparent cost-aware single-period comparator, then a small
multi-period/scenario version. Only after that ask whether learning an uncertainty
set or a decision loss improves outcomes relative to fixed, well-calibrated rules.
Compare at common targets, contributions, execution times, costs, and risk/drift
metrics. Learnable inputs need not be expected returns; they could instead model
execution uncertainty. The generic ideas require adaptation to our trading model.

The existing 2005-2025 results have already been inspected. New variants on those
dates are exploratory. Joint block resampling can examine uncertainty/mechanisms
under assumptions; it cannot turn previously inspected history back into an
untouched test set. A future evaluation requires a newly frozen protocol and
subsequently unobserved data.

## Finding future papers

Use Google Scholar for citation trails and author alerts, then verify candidates
on primary sources. For new optimization/ML work check arXiv `math.OC`, `cs.LG`,
`stat.ML`, `q-fin.PM`, and `q-fin.CP`; ICML/UAI proceedings at PMLR;
NeurIPS/ICLR papers and reviews; Mathematical Programming, Mathematical Programming
Computation, SIAM Journal on Optimization, and relevant finance journals. A search
result, a GitHub star count, or a very recent upload is not a quality assessment.

Useful search phrases: `transaction cost multi-period portfolio optimization`,
`decision-focused learning portfolio`, `optimal transport distributionally robust
portfolio`, and `differentiable quadratic programming`.

## Local reading packet

Ten PDFs plus a SHA-256/download manifest were saved outside the public repository
under `outputs/literature_review_2026-10-22/` in the parent workspace. The Costa/
Iyengar item is an earlier public manuscript; the remaining exact URLs, page
counts, and retrieval times are in that local manifest. Source PDFs and extracted
full text are not republished in this repository. Only these original notes and
links are intended for the public project.
