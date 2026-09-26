"""Portfolio construction, sizing and attribution.

Source lectures: 17 (PCA), 20 (why optimization fails), 36 (Kelly), 78/88/128
(CAPM alpha/beta), 100 (Black-Litterman vs MVO), 115/123/127 (portfolio
engineering/management), 138 (crash hedging via regression/PCA).
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from scipy.stats import t as t_dist

__all__ = [
    "annualize_moments", "min_variance_weights", "tangency_weights", "mean_variance_weights",
    "efficient_frontier", "risk_parity_weights", "risk_contributions",
    "implied_equilibrium_returns", "black_litterman",
    "kelly_binary", "kelly_continuous", "kelly_multi", "growth_rate",
    "capm_regression", "hedge_ratio", "pca",
]


def annualize_moments(returns, periods_per_year=252):
    """Sample mean vector and covariance from a (T, n) matrix of periodic simple returns."""
    R = np.asarray(returns, float)
    return R.mean(axis=0) * periods_per_year, np.cov(R, rowvar=False) * periods_per_year


# ----------------------------------------------------------------------------
# Mean-variance family
# ----------------------------------------------------------------------------
def min_variance_weights(cov, long_only=False):
    cov = np.asarray(cov, float)
    n = len(cov)
    if not long_only:
        w = np.linalg.solve(cov, np.ones(n))
        return w / w.sum()
    return _solve(lambda w: w @ cov @ w, n, long_only=True)


def tangency_weights(mu, cov, rf=0.0, long_only=False):
    """Max-Sharpe portfolio. Unconstrained closed form: w ~ Sigma^{-1}(mu - rf)."""
    mu, cov = np.asarray(mu, float), np.asarray(cov, float)
    if not long_only:
        w = np.linalg.solve(cov, mu - rf)
        return w / w.sum()
    neg_sharpe = lambda w: -(w @ mu - rf) / np.sqrt(w @ cov @ w)
    return _solve(neg_sharpe, len(mu), long_only=True)


def mean_variance_weights(mu, cov, risk_aversion=3.0, long_only=False, budget=True):
    """max_w  w'mu - (delta/2) w'Sigma w  [s.t. sum w = 1, w >= 0]."""
    mu, cov = np.asarray(mu, float), np.asarray(cov, float)
    obj = lambda w: -(w @ mu - 0.5 * risk_aversion * w @ cov @ w)
    if not long_only and not budget:
        return np.linalg.solve(risk_aversion * cov, mu)
    return _solve(obj, len(mu), long_only=long_only, budget=budget)


def efficient_frontier(mu, cov, n_points=50, long_only=True):
    """Returns (vols, rets, weights) of min-variance portfolios for target returns."""
    mu, cov = np.asarray(mu, float), np.asarray(cov, float)
    targets = np.linspace(mu.min(), mu.max(), n_points)
    vols, W = [], []
    for tr in targets:
        cons = [{"type": "eq", "fun": lambda w: w.sum() - 1},
                {"type": "eq", "fun": lambda w, tr=tr: w @ mu - tr}]
        bounds = [(0, 1)] * len(mu) if long_only else None
        res = minimize(lambda w: w @ cov @ w, np.full(len(mu), 1 / len(mu)),
                       bounds=bounds, constraints=cons, method="SLSQP")
        W.append(res.x); vols.append(np.sqrt(res.x @ cov @ res.x))
    return np.array(vols), targets, np.array(W)


def risk_contributions(w, cov):
    """Fraction of portfolio variance from each asset: w_i (Sigma w)_i / w'Sigma w."""
    w, cov = np.asarray(w, float), np.asarray(cov, float)
    return w * (cov @ w) / (w @ cov @ w)


def risk_parity_weights(cov):
    """Equal-risk-contribution long-only weights (robust alternative when mu is unknown,
    see lecture 21 'expected returns don't exist')."""
    cov = np.asarray(cov, float)
    n = len(cov)
    obj = lambda w: np.sum((risk_contributions(w, cov) - 1 / n) ** 2)
    return _solve(obj, n, long_only=True, x0=1 / np.sqrt(np.diag(cov)))


def _solve(obj, n, long_only=False, budget=True, x0=None):
    x0 = np.full(n, 1 / n) if x0 is None else np.asarray(x0, float) / np.sum(x0)
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}] if budget else []
    bounds = [(0, 1)] * n if long_only else None
    res = minimize(obj, x0, bounds=bounds, constraints=cons, method="SLSQP",
                   options={"maxiter": 1000, "ftol": 1e-12})
    return res.x


# ----------------------------------------------------------------------------
# Black-Litterman (lecture 100)
# ----------------------------------------------------------------------------
def implied_equilibrium_returns(cov, w_mkt, risk_aversion=2.5):
    """Reverse optimization: Pi = delta * Sigma * w_mkt (returns the market 'believes')."""
    return risk_aversion * np.asarray(cov, float) @ np.asarray(w_mkt, float)


def black_litterman(cov, w_mkt, P, Q, risk_aversion=2.5, tau=0.05, omega=None, view_confidence=None):
    """Black-Litterman posterior.

    P (k x n) pick matrix, Q (k,) view returns. Omega defaults to
    diag(P tau Sigma P') (He-Litterman). ``view_confidence`` in (0,1] per view
    scales Omega down (more confident -> closer to the view).

        mu_BL = [(tau S)^-1 + P' O^-1 P]^-1 [(tau S)^-1 Pi + P' O^-1 Q]
        S_BL  = S + [(tau S)^-1 + P' O^-1 P]^-1

    Returns (mu_bl, cov_bl, weights) with weights = unconstrained MV optimum
    (S_BL^-1 mu_BL / delta). Small view tilts -> small weight tilts: that is the
    stability advantage over raw MVO on noisy sample means.
    """
    cov = np.asarray(cov, float)
    P, Q = np.atleast_2d(np.asarray(P, float)), np.atleast_1d(np.asarray(Q, float))
    pi = implied_equilibrium_returns(cov, w_mkt, risk_aversion)
    ts = tau * cov
    if omega is None:
        omega = np.diag(np.diag(P @ ts @ P.T))
        if view_confidence is not None:
            c = np.clip(np.asarray(view_confidence, float), 1e-6, 1.0)
            omega = omega * np.diag((1 - c) / c + 1e-12)
    ts_inv = np.linalg.inv(ts)
    om_inv = np.linalg.inv(omega)
    M = np.linalg.inv(ts_inv + P.T @ om_inv @ P)
    mu_bl = M @ (ts_inv @ pi + P.T @ om_inv @ Q)
    cov_bl = cov + M
    w = np.linalg.solve(risk_aversion * cov_bl, mu_bl)
    return mu_bl, cov_bl, w


# ----------------------------------------------------------------------------
# Kelly criterion (lecture 36)
# ----------------------------------------------------------------------------
def kelly_binary(p, b, a=1.0):
    """Bet fraction for win prob p, net odds b (win b per 1 staked), loss a per 1.
    f* = p/a - (1-p)/b. Negative => don't bet (or take the other side)."""
    return p / a - (1 - p) / b


def kelly_continuous(mu, sigma, r=0.0):
    """Continuous-time (GBM) Kelly leverage: f* = (mu - r) / sigma^2.
    Growth at f*: r + (mu-r)^2/(2 sigma^2). Over-betting at 2f* gives growth r (zero excess);
    beyond 2f* long-run wealth -> 0 even with positive edge. Use half-Kelly in practice
    because mu is estimated with huge error."""
    return (mu - r) / sigma ** 2


def kelly_multi(mu, cov, r=0.0):
    """Multi-asset Kelly: f* = Sigma^{-1} (mu - r)."""
    return np.linalg.solve(np.asarray(cov, float), np.asarray(mu, float) - r)


def growth_rate(f, mu, sigma, r=0.0):
    """Expected log-growth of leveraged GBM: g(f) = r + f(mu - r) - f^2 sigma^2 / 2."""
    return r + f * (mu - r) - 0.5 * f ** 2 * sigma ** 2


# ----------------------------------------------------------------------------
# Alpha / beta attribution (lectures 78, 88, 128)
# ----------------------------------------------------------------------------
def capm_regression(port, bench, rf=0.0, periods_per_year=252):
    """OLS of excess returns: r_p - rf = alpha + beta (r_m - rf) + e.

    Returns alpha (per period and annualized), beta, their t-stats and p-values,
    R^2, residual (idiosyncratic) vol, information ratio. Lecture 96: an alpha
    with |t| < 2 is statistically indistinguishable from luck.
    """
    y = np.asarray(port, float) - rf
    x = np.asarray(bench, float) - rf
    n = len(y)
    X = np.column_stack([np.ones(n), x])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    s2 = resid @ resid / (n - 2)
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    tstats = coef / se
    pvals = 2 * t_dist.sf(np.abs(tstats), n - 2)
    r2 = 1 - resid @ resid / np.sum((y - y.mean()) ** 2)
    resid_vol = np.sqrt(s2 * periods_per_year)
    alpha_ann = coef[0] * periods_per_year
    return {"alpha": coef[0], "alpha_annual": alpha_ann, "beta": coef[1],
            "t_alpha": tstats[0], "t_beta": tstats[1], "p_alpha": pvals[0], "p_beta": pvals[1],
            "r2": r2, "residual_vol": resid_vol,
            "information_ratio": alpha_ann / resid_vol if resid_vol > 0 else np.nan}


def hedge_ratio(port, hedge):
    """Minimum-variance hedge ratio h* = Cov(p, h)/Var(h): short h* units of the hedge
    per unit of portfolio (e.g. SPY puts/shorts against a stock book, lecture 138).
    Variance reduction achieved = corr^2."""
    p, h = np.asarray(port, float), np.asarray(hedge, float)
    c = np.cov(p, h)
    return c[0, 1] / c[1, 1], (c[0, 1] ** 2) / (c[0, 0] * c[1, 1])


# ----------------------------------------------------------------------------
# PCA (lecture 17)
# ----------------------------------------------------------------------------
def pca(returns, standardize=True):
    """PCA of a (T, n) return matrix. Returns dict with eigenvalues, explained
    variance ratio, loadings (n x n, columns = PCs) and factor scores (T x n).
    PC1 of equities is usually 'the market' (all loadings same sign)."""
    R = np.asarray(returns, float)
    Z = R - R.mean(axis=0)
    if standardize:
        Z = Z / R.std(axis=0, ddof=1)
    C = np.cov(Z, rowvar=False)
    vals, vecs = np.linalg.eigh(C)
    idx = np.argsort(vals)[::-1]
    vals, vecs = vals[idx], vecs[:, idx]
    vecs = vecs * np.sign(vecs.sum(axis=0, keepdims=True) + 1e-18)  # sign convention
    return {"eigenvalues": vals, "explained_ratio": vals / vals.sum(),
            "loadings": vecs, "scores": Z @ vecs}
