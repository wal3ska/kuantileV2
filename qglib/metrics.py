"""Performance, risk and 'is it skill or luck' statistics.

Source lectures: 3/21/26/28/46/60 (expectation, gambling vs trading, gambler's ruin),
4/40/48/101/112/129 (Sharpe, Sortino, drawdown, misleading metrics),
81 (ergodicity), 96/78 (alpha significance), 97/118 (backtesting pitfalls),
117/125/135/136 (CAGR, volatility drag), 119 (volatility risk premium),
126 (tail risk: VaR/CVaR, waiting times).
"""
from __future__ import annotations

import numpy as np
from scipy.stats import kurtosis, norm, skew

__all__ = [
    "equity_curve", "cagr", "annualized_return", "annualized_vol", "volatility_drag",
    "sharpe", "sharpe_se", "probabilistic_sharpe", "min_track_record_length", "sortino",
    "max_drawdown", "drawdown_series", "calmar", "summary",
    "var_historical", "cvar_historical", "var_parametric", "var_cornish_fisher",
    "tail_probability", "expected_wait", "gamblers_ruin", "time_vs_ensemble_growth",
    "variance_risk_premium", "walk_forward_splits",
]


def equity_curve(returns, start=1.0):
    return start * np.cumprod(1 + np.asarray(returns, float))


def cagr(equity, periods_per_year=252):
    """Compound annual growth rate from an equity curve (lecture 125)."""
    e = np.asarray(equity, float)
    years = (len(e) - 1) / periods_per_year
    return (e[-1] / e[0]) ** (1 / years) - 1


def annualized_return(returns, periods_per_year=252, geometric=True):
    r = np.asarray(returns, float)
    if geometric:
        return np.prod(1 + r) ** (periods_per_year / len(r)) - 1
    return r.mean() * periods_per_year


def annualized_vol(returns, periods_per_year=252):
    return np.asarray(returns, float).std(ddof=1) * np.sqrt(periods_per_year)


def volatility_drag(returns, periods_per_year=252):
    """Arithmetic minus geometric annualized return (~ sigma^2/2). Lectures 117/136:
    the drag is why -50% needs +100%, and why reducing vol (diversification,
    rebalancing) can *raise* compounded wealth at the same arithmetic mean."""
    r = np.asarray(returns, float)
    arith = r.mean() * periods_per_year
    geo = np.log1p(r).mean() * periods_per_year
    return {"arithmetic": arith, "log_growth": geo, "drag": arith - geo,
            "approx_sigma2_over_2": 0.5 * r.var(ddof=1) * periods_per_year}


def sharpe(returns, rf=0.0, periods_per_year=252):
    """Annualized Sharpe of periodic returns; rf is per-period."""
    ex = np.asarray(returns, float) - rf
    sd = ex.std(ddof=1)
    return np.sqrt(periods_per_year) * ex.mean() / sd if sd > 0 else np.nan


def sharpe_se(sr_annual, n_obs, periods_per_year=252, skewness=0.0, excess_kurt=0.0):
    """Standard error of an annualized Sharpe estimate (Lo 2002 / Mertens).
    Rule of thumb: SE ~ sqrt(years)^-1, so a 1.0 Sharpe needs ~4+ years to reach t=2."""
    sr = sr_annual / np.sqrt(periods_per_year)
    var = (1 + 0.5 * sr ** 2 - skewness * sr + (excess_kurt / 4) * sr ** 2) / n_obs
    return np.sqrt(var * periods_per_year)


def probabilistic_sharpe(returns, sr_benchmark_annual=0.0, periods_per_year=252):
    """P(true Sharpe > benchmark) accounting for sample size, skew and fat tails
    (Bailey & Lopez de Prado). > 0.95 ~ 'significant'."""
    r = np.asarray(returns, float)
    n = len(r)
    sr = r.mean() / r.std(ddof=1)
    sr_b = sr_benchmark_annual / np.sqrt(periods_per_year)
    g3, g4 = skew(r), kurtosis(r, fisher=False)
    den = np.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    return float(norm.cdf((sr - sr_b) * np.sqrt(n - 1) / den))


def min_track_record_length(sr_annual, sr_benchmark_annual=0.0, periods_per_year=252,
                            skewness=0.0, kurt=3.0, confidence=0.95):
    """Periods of data needed before a Sharpe of sr_annual is distinguishable from
    the benchmark at the given confidence."""
    sr = sr_annual / np.sqrt(periods_per_year)
    sr_b = sr_benchmark_annual / np.sqrt(periods_per_year)
    z = norm.ppf(confidence)
    return 1 + (1 - skewness * sr + (kurt - 1) / 4 * sr ** 2) * (z / (sr - sr_b)) ** 2


def sortino(returns, target=0.0, periods_per_year=252):
    """Sortino ratio with downside semideviation below ``target`` (lecture 101)."""
    r = np.asarray(returns, float)
    downside = np.sqrt(np.mean(np.minimum(r - target, 0) ** 2))
    return np.sqrt(periods_per_year) * (r.mean() - target) / downside if downside > 0 else np.nan


def drawdown_series(equity):
    e = np.asarray(equity, float)
    peak = np.maximum.accumulate(e)
    return e / peak - 1


def max_drawdown(equity):
    """Returns dict(max_drawdown (negative), peak_idx, trough_idx, recovery_idx or None,
    longest_underwater periods)."""
    e = np.asarray(equity, float)
    dd = drawdown_series(e)
    trough = int(dd.argmin())
    peak = int(e[:trough + 1].argmax())
    rec = np.where(e[trough:] >= e[peak])[0]
    under = dd < 0
    longest, cur = 0, 0
    for u in under:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    return {"max_drawdown": float(dd.min()), "peak_idx": peak, "trough_idx": trough,
            "recovery_idx": int(trough + rec[0]) if len(rec) else None,
            "longest_underwater": longest}


def calmar(returns, periods_per_year=252):
    eq = equity_curve(returns)
    mdd = max_drawdown(np.concatenate([[1.0], eq]))["max_drawdown"]
    return annualized_return(returns, periods_per_year) / abs(mdd) if mdd < 0 else np.nan


def summary(returns, rf=0.0, periods_per_year=252):
    """One-shot performance table for a periodic return series."""
    r = np.asarray(returns, float)
    eq = np.concatenate([[1.0], equity_curve(r)])
    return {
        "cagr": cagr(eq, periods_per_year),
        "ann_vol": annualized_vol(r, periods_per_year),
        "sharpe": sharpe(r, rf, periods_per_year),
        "sharpe_se": sharpe_se(sharpe(r, rf, periods_per_year), len(r), periods_per_year),
        "psr_vs_0": probabilistic_sharpe(r - rf, 0.0, periods_per_year),
        "sortino": sortino(r, 0.0, periods_per_year),
        "max_drawdown": max_drawdown(eq)["max_drawdown"],
        "calmar": calmar(r, periods_per_year),
        "skew": float(skew(r)), "excess_kurtosis": float(kurtosis(r)),
        "hit_rate": float(np.mean(r > 0)), "n_obs": len(r),
    }


# ----------------------------------------------------------------------------
# Tail risk (lecture 126)
# ----------------------------------------------------------------------------
def var_historical(returns, alpha=0.99):
    """Historical VaR as a positive loss number at confidence alpha."""
    return float(-np.quantile(np.asarray(returns, float), 1 - alpha))


def cvar_historical(returns, alpha=0.99):
    """Expected shortfall: mean loss beyond VaR."""
    r = np.asarray(returns, float)
    q = np.quantile(r, 1 - alpha)
    return float(-r[r <= q].mean())


def var_parametric(mu, sigma, alpha=0.99):
    return float(-(mu + sigma * norm.ppf(1 - alpha)))


def var_cornish_fisher(returns, alpha=0.99):
    """Normal VaR corrected for skew and excess kurtosis."""
    r = np.asarray(returns, float)
    z = norm.ppf(1 - alpha)
    s, k = skew(r), kurtosis(r)
    zcf = z + (z ** 2 - 1) * s / 6 + (z ** 3 - 3 * z) * k / 24 - (2 * z ** 3 - 5 * z) * s ** 2 / 36
    return float(-(r.mean() + zcf * r.std(ddof=1)))


def tail_probability(returns, k_sigma=4.0):
    """Empirical vs Gaussian probability of a |move| > k sigma. Real returns show
    ratios of 10-1000x at 4-6 sigma: normal-based risk badly understates crashes."""
    r = np.asarray(returns, float)
    z = (r - r.mean()) / r.std(ddof=1)
    emp = float(np.mean(np.abs(z) > k_sigma))
    gauss = float(2 * norm.sf(k_sigma))
    return {"empirical": emp, "gaussian": gauss, "ratio": emp / gauss if gauss > 0 else np.inf}


def expected_wait(p_per_period):
    """Expected periods until first occurrence of an event of per-period probability p
    (geometric distribution): 1/p. E.g. a 1e-4 daily event ~ 40 years of trading days."""
    return 1.0 / p_per_period


# ----------------------------------------------------------------------------
# Games, ruin, ergodicity (lectures 26, 28, 81)
# ----------------------------------------------------------------------------
def gamblers_ruin(p, start, target):
    """P(ruin) for a +/-1 random walk with up-prob p from ``start`` before reaching
    ``target`` (absorbing at 0 and target). Even with an edge, a small bankroll
    relative to bet size keeps ruin risk material."""
    q = 1 - p
    if np.isclose(p, 0.5):
        return 1 - start / target
    r = q / p
    return (r ** start - r ** target) / (1 - r ** target)


def time_vs_ensemble_growth(outcomes, probs):
    """Ergodicity check for a multiplicative bet with returns ``outcomes`` (e.g.
    [+0.5, -0.4]) and probabilities. Ensemble (expected) return can be positive
    while the time-average growth of a single path is negative."""
    o, p = np.asarray(outcomes, float), np.asarray(probs, float)
    ensemble = float(p @ o)
    time_avg = float(np.exp(p @ np.log1p(o)) - 1)
    return {"ensemble_mean_return": ensemble, "time_average_growth": time_avg,
            "ergodic_trap": ensemble > 0 > time_avg}


# ----------------------------------------------------------------------------
# Options risk premia (lecture 119)
# ----------------------------------------------------------------------------
def variance_risk_premium(implied_vol_annual, future_returns, periods_per_year=252):
    """VRP = implied variance - subsequently realized variance (annualized).
    ``future_returns`` = the returns over the option's life *after* the IV observation.
    Positive on average for equity indices (option sellers are paid for crash risk)."""
    r = np.asarray(future_returns, float)
    rv = np.mean(r ** 2) * periods_per_year
    return {"implied_var": implied_vol_annual ** 2, "realized_var": rv,
            "vrp_var": implied_vol_annual ** 2 - rv,
            "vrp_vol": implied_vol_annual - np.sqrt(rv)}


# ----------------------------------------------------------------------------
# Backtesting hygiene (lectures 97, 118, 142)
# ----------------------------------------------------------------------------
def walk_forward_splits(n, train, test, step=None, expanding=False):
    """Yield (train_idx, test_idx) index arrays for walk-forward evaluation.
    Fit ONLY on train, evaluate on the following test block; never shuffle time series."""
    step = step or test
    start = 0
    while start + train + test <= n:
        tr0 = 0 if expanding else start
        yield np.arange(tr0, start + train), np.arange(start + train, start + train + test)
        start += step
