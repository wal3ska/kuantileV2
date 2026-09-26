---
name: qg-portfolio-risk
description: Build, size and evaluate portfolios and strategies in code — MVO, Black-Litterman, risk parity, Kelly, CAPM alpha/beta, PCA, Sharpe significance, drawdowns, VaR/CVaR, vol drag, ruin/ergodicity, walk-forward backtests (Quant Guild methods).
---

# Portfolio construction, sizing & risk evaluation (Quant Guild methods)

Methods distilled from the Quant Guild Library (Roman Paolucci — github.com/romanmichaelpaolucci/Quant-Guild-Library, youtube.com/@QuantGuild), implemented and tested in `qglib.portfolio` and `qglib.metrics`. Use when the user wants to optimize weights, size bets, attribute performance, measure risk, or judge whether a strategy's results are skill or luck, inside a code project. Turkish triggers: portföy optimizasyonu, Black-Litterman, Kelly, pozisyon büyüklüğü, alfa/beta, Sharpe, Sortino, maksimum düşüş (drawdown), VaR/CVaR, kuyruk riski, volatilite sürüklenmesi, backtest.

## Step 0 — Integrate with the project first
1. Search the project for `qglib`. If present: `from qglib import portfolio as PF, metrics as M`.
2. If absent, offer to vendor `qglib/` (+ tests) or implement inline from the snippets below with identical names/signatures.
3. Inputs: periodic **simple** returns as numpy arrays (T,) or (T, n); state `periods_per_year` explicitly (252 daily, 52 weekly, 12 monthly). Accept pandas but convert at the boundary.
4. Every metric shown to a user comes with its uncertainty where one exists (Sharpe SE / PSR, alpha t-stat).

## Method selection

| Need | Method | qglib |
|---|---|---|
| Weights with trusted μ, Σ | Mean-variance / tangency / min-variance | `mean_variance_weights`, `tangency_weights`, `min_variance_weights`, `efficient_frontier` |
| μ is noisy (almost always) | Black-Litterman: equilibrium Π=δΣw_mkt + views | `implied_equilibrium_returns`, `black_litterman` |
| No return views at all | Min-variance or equal risk contribution | `risk_parity_weights`, `risk_contributions` |
| How much to bet / leverage | Kelly (binary, continuous, multi-asset) — use ½-Kelly | `kelly_binary`, `kelly_continuous`, `kelly_multi`, `growth_rate` |
| Is my return alpha or beta? | CAPM OLS with t-stats, IR | `capm_regression` |
| Hedge a book with an index | Min-variance hedge ratio, R² = variance removed | `hedge_ratio` |
| Common drivers across assets | PCA (PC1 ≈ market) | `pca` |
| Performance table | CAGR, vol, Sharpe(+SE), PSR, Sortino, MDD, Calmar, skew, kurtosis | `summary` |
| Is the Sharpe real? | Sharpe SE, Probabilistic Sharpe, Min Track Record Length | `sharpe_se`, `probabilistic_sharpe`, `min_track_record_length` |
| Tail risk | Historical / parametric / Cornish-Fisher VaR, CVaR, tail-prob ratio, wait time | `var_*`, `cvar_historical`, `tail_probability`, `expected_wait` |
| Compounding reality | Vol drag = arithmetic − log growth ≈ σ²/2 | `volatility_drag`, `cagr` |
| Survival | Gambler's ruin, time vs ensemble growth | `gamblers_ruin`, `time_vs_ensemble_growth` |
| Short-vol edge | Variance risk premium = IV² − realized var | `variance_risk_premium` |
| Honest out-of-sample test | Walk-forward splits | `walk_forward_splits` |

## Core reference code

```python
import numpy as np
from scipy.stats import norm, skew, kurtosis

def black_litterman(cov, w_mkt, P, Q, delta=2.5, tau=0.05):
    pi = delta*cov@w_mkt                                   # implied equilibrium returns
    P, Q = np.atleast_2d(P), np.atleast_1d(Q)
    omega = np.diag(np.diag(P@(tau*cov)@P.T))              # He-Litterman view uncertainty
    A = np.linalg.inv(np.linalg.inv(tau*cov) + P.T@np.linalg.inv(omega)@P)
    mu = A@(np.linalg.inv(tau*cov)@pi + P.T@np.linalg.inv(omega)@Q)
    cov_bl = cov + A
    return mu, cov_bl, np.linalg.solve(delta*cov_bl, mu)  # posterior mean, cov, MV weights

def kelly_continuous(mu, sigma, r=0.0):                    # optimal leverage for GBM
    return (mu - r)/sigma**2                               # growth g(f)=r+f(mu-r)-f^2 sigma^2/2

def capm_regression(port, bench, rf=0.0, ppy=252):
    y, x = np.asarray(port) - rf, np.asarray(bench) - rf
    X = np.column_stack([np.ones(len(y)), x]); b, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X@b; s2 = e@e/(len(y) - 2); se = np.sqrt(np.diag(s2*np.linalg.inv(X.T@X)))
    return dict(alpha_annual=b[0]*ppy, beta=b[1], t_alpha=b[0]/se[0], t_beta=b[1]/se[1],
                r2=1 - e@e/np.sum((y - y.mean())**2), ir=b[0]*ppy/np.sqrt(s2*ppy))

def sharpe(r, rf=0.0, ppy=252):
    ex = np.asarray(r) - rf; return np.sqrt(ppy)*ex.mean()/ex.std(ddof=1)

def probabilistic_sharpe(r, sr_bench_annual=0.0, ppy=252):     # P(true SR > benchmark)
    r = np.asarray(r); sr = r.mean()/r.std(ddof=1); srb = sr_bench_annual/np.sqrt(ppy)
    g3, g4 = skew(r), kurtosis(r, fisher=False)
    return norm.cdf((sr - srb)*np.sqrt(len(r) - 1)/np.sqrt(1 - g3*sr + (g4 - 1)/4*sr**2))

def max_drawdown(equity):
    e = np.asarray(equity); return (e/np.maximum.accumulate(e) - 1).min()

def cvar_historical(r, alpha=0.99):
    q = np.quantile(r, 1 - alpha); return -np.asarray(r)[r <= q].mean()
```

Key formulas:
- Tangency (unconstrained) `w ∝ Σ⁻¹(μ − r_f)`; min-var `w ∝ Σ⁻¹1`; risk contribution `w_i(Σw)_i / w'Σw`.
- Kelly binary `f* = p/a − (1−p)/b`; at 2f* growth falls to r; beyond, ruin in the long run. Estimated μ is so noisy that ½-Kelly (≈75% of max growth, ½ the variance) is the practical default (lecture 36).
- Sharpe SE ≈ `√((1 + SR²/2)/years)` annualized → a true 1.0 Sharpe needs ~3–4 years of daily data to be significant (`min_track_record_length`). Sharpe is blind to path order and tails (lectures 101, 112): always pair with Sortino, MDD, skew/kurtosis, PSR.
- CAGR vs arithmetic mean: `geo ≈ arith − σ²/2`; −50% needs +100%. Reducing σ at the same arithmetic mean raises compounded wealth — diversification/rebalancing "creates" growth (lectures 117, 136).
- Ergodicity (lecture 81): a +50%/−40% coin has ensemble mean +5% but time-average growth √(1.5·0.6)−1 ≈ −5.1%. Size for the time average.
- Gambler's ruin: `P(ruin) = ((q/p)^i − (q/p)^N)/(1 − (q/p)^N)`; with edge and N→∞, `(q/p)^i`. Bankroll in units of bet size is what matters.
- CAPM: alpha with |t| < 2 is indistinguishable from luck (lectures 78, 96); high R² + beta ≈ 1 means you own the index with fees.
- Black-Litterman: with no views (Ω→∞) it returns the market portfolio; views tilt weights smoothly — this is its stability advantage over MVO on sample means, which swings wildly under small input noise (lectures 20, 100).
- Tail risk (lecture 126): empirical 4–6σ frequency is 10–1000× the Gaussian; `expected_wait = 1/p`. Risk maps calibrated in calm regimes blow up in crises — condition VaR on a volatility regime (GARCH/HMM from `qg-stochastic-models`) and stress-test with crisis windows.
- VRP (lecture 119): short-vol strategies (covered calls, CSPs, short straddles) harvest IV² − RV² on average and pay it back in crashes; report CVaR, not just Sharpe.

## Backtest discipline (lectures 97, 112, 118, 122, 124, 142)
1. No look-ahead: signals at t use data ≤ t; trade at t+1 open/close; rolling estimators seeded without future data.
2. Walk-forward: fit on train block, evaluate on the next block, roll (`walk_forward_splits`); never shuffle time series.
3. Include costs, slippage, borrow/margin (lecture 140: short squeezes + margin calls), and position limits.
4. Report uncertainty: Sharpe SE/PSR, alpha t-stat, bootstrap confidence bands; count how many variants you tried (multiple testing inflates the best Sharpe).
5. Null test: run the same pipeline on simulated zero-edge returns (GBM or shuffled returns) — if it "finds" alpha there, the pipeline is broken.
6. Regime check: split results by volatility regime; "profitable" ≠ "tradable" if P&L comes from one regime (lecture 77).

## Validation (write these as tests)
- Tangency Sharpe ≥ long-only tangency Sharpe ≥ equal-weight Sharpe on the same (μ, Σ).
- Risk parity: all risk contributions = 1/n (±1e-3).
- BL with no views → posterior μ = Π and weights ∝ w_mkt; a view "A beats B by 5%" raises μ_A − μ_B.
- Kelly: `kelly_binary(0.6, 1) = 0.2`; `growth_rate(2f*) = r`.
- CAPM on simulated `p = α + 1.3m + ε` recovers β ±0.03 and α within 3.5 SE; `hedge_ratio` R² = CAPM R².
- PCA on one-factor data: PC1 explains most variance with same-sign loadings.
- MDD of [100,120,90,135,108,150] = −25%, peak idx 1, trough 2, recovery 3.
- Normal returns: VaR99 ≈ 2.326σ, CVaR99 ≈ 2.665σ; Cornish-Fisher ≈ parametric; Student-t(3) 5σ tail ratio > 10.
- Ruin p=0.5: `1 − i/N`; ergodic trap flag true for [+0.5, −0.4].
- Walk-forward: every train index < every test index.

## Lecture map
Expectation, gambling vs trading 3, 21, 26, 46, 57, 60 · gambler's ruin 28 · Kelly 36 · PCA 17 · optimization pitfalls 20 · BL vs MVO 100 · portfolio engineering/management 88, 115, 123, 127 · alpha & beta 78, 96, 128 · Sharpe/metrics 4, 40, 48, 101, 112, 129 · CAGR & vol drag 117, 125, 135, 136 · ergodicity 81 · tail risk 126 · crash hedging 138 · VRP 119 · backtesting 75, 97, 118, 124, 142 · retail pitfalls 99, 111, 121, 122 · margin/short risk 140.
