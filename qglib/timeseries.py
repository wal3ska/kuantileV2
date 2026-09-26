"""Time series, volatility models, filtering and regimes.

Source lectures: 44 (time series), 47 (EWMA/ARCH/GARCH), 49/71 (Markov chains),
51 (HMM forward-backward), 72/74 (live Markov regime filter), 92/95 (Kalman),
93 (non-stationarity), 126 (GARCH regimes for tail risk).
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp
from scipy.stats import norm

__all__ = [
    "log_returns", "realized_vol", "ar1_fit", "ou_from_ar1", "adf_test", "rolling_zscore",
    "ewma_variance", "garch11_filter", "garch11_fit", "garch11_forecast",
    "KalmanFilter", "KalmanOU", "kalman_local_level", "kalman_regression",
    "stationary_distribution", "estimate_transition_matrix", "expected_durations",
    "GaussianHMM",
]


# ----------------------------------------------------------------------------
# Basics
# ----------------------------------------------------------------------------
def log_returns(prices):
    p = np.asarray(prices, float)
    return np.diff(np.log(p))


def realized_vol(returns, window=21, periods_per_year=252):
    """Rolling annualized close-to-close realized vol (zero-mean estimator)."""
    r = np.asarray(returns, float)
    out = np.full(len(r), np.nan)
    for i in range(window - 1, len(r)):
        out[i] = np.sqrt(np.mean(r[i - window + 1:i + 1] ** 2) * periods_per_year)
    return out


def ar1_fit(x):
    """OLS AR(1): x_t = c + phi x_{t-1} + eps. Returns dict(c, phi, sigma, mean)."""
    x = np.asarray(x, float)
    X = np.column_stack([np.ones(len(x) - 1), x[:-1]])
    (c, phi), *_ = np.linalg.lstsq(X, x[1:], rcond=None)
    resid = x[1:] - (c + phi * x[:-1])
    return {"c": c, "phi": phi, "sigma": resid.std(ddof=2),
            "mean": c / (1 - phi) if phi != 1 else np.nan}


def ou_from_ar1(phi, c, sigma_eps, dt):
    """Map AR(1) coefficients to OU (kappa, theta, sigma, half_life).
    Valid for 0 < phi < 1 (mean reverting)."""
    kappa = -np.log(phi) / dt
    theta = c / (1 - phi)
    sigma = sigma_eps * np.sqrt(2 * kappa / (1 - phi ** 2))
    return {"kappa": kappa, "theta": theta, "sigma": sigma, "half_life": np.log(2) / kappa}


def adf_test(x, maxlag=None):
    """Augmented Dickey-Fuller (requires statsmodels). Low p-value => stationary.
    Lecture 93: most price series are non-stationary, so 'timing' signals built on
    price levels are fragile; test returns/spreads instead."""
    try:
        from statsmodels.tsa.stattools import adfuller
    except ImportError as e:  # keep the core library dependency-light
        raise ImportError("pip install statsmodels for adf_test") from e
    stat, p, lags, nobs, crit, _ = adfuller(np.asarray(x, float), maxlag=maxlag)
    return {"stat": stat, "pvalue": p, "lags": lags, "nobs": nobs, "crit": crit}


def rolling_zscore(x, window):
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    for i in range(window - 1, len(x)):
        w = x[i - window + 1:i + 1]
        s = w.std(ddof=1)
        out[i] = (x[i] - w.mean()) / s if s > 0 else 0.0
    return out


# ----------------------------------------------------------------------------
# Volatility models (lecture 47)
# ----------------------------------------------------------------------------
def ewma_variance(returns, lam=0.94, init=None, burn_in=20):
    """RiskMetrics EWMA: s2_t = lam s2_{t-1} + (1-lam) r_{t-1}^2.
    Element t is the forecast for day t using data through t-1.
    Seeded with the mean square of the first ``burn_in`` returns (NOT the full-sample
    variance, which would leak future data) -- discard the first ``burn_in`` values
    in a backtest, or pass ``init`` from a prior calibration window."""
    r = np.asarray(returns, float)
    s2 = np.empty(len(r))
    s2[0] = np.mean(r[:burn_in] ** 2) if init is None else init
    for t in range(1, len(r)):
        s2[t] = lam * s2[t - 1] + (1 - lam) * r[t - 1] ** 2
    return s2


def garch11_filter(returns, omega, alpha, beta, mu=0.0, h0=None):
    """Conditional variance path h_t = omega + alpha eps_{t-1}^2 + beta h_{t-1}.
    h0 defaults to the long-run variance omega/(1-alpha-beta) (no look-ahead)."""
    eps = np.asarray(returns, float) - mu
    h = np.empty(len(eps))
    h[0] = omega / max(1 - alpha - beta, 1e-8) if h0 is None else h0
    for t in range(1, len(eps)):
        h[t] = omega + alpha * eps[t - 1] ** 2 + beta * h[t - 1]
    return h


def garch11_fit(returns, dist="normal"):
    """Gaussian (or Student-t, dist='t') MLE for GARCH(1,1) with constant mean.
    Use returns in *percent* (x100) for numerical stability.
    Returns dict(mu, omega, alpha, beta, [nu], persistence, long_run_var, loglik)."""
    r = np.asarray(returns, float)
    var0 = np.var(r)

    def unpack(p):
        mu, lo, la, lb = p[:4]
        omega = np.exp(lo)
        a, b = np.exp(la), np.exp(lb)
        s = 1 + a + b                      # softmax-style: a+b<1 always
        alpha, beta = a / s, b / s
        nu = 2.01 + np.exp(p[4]) if dist == "t" else None
        return mu, omega, alpha, beta, nu

    def nll(p):
        mu, omega, alpha, beta, nu = unpack(p)
        h = garch11_filter(r, omega, alpha, beta, mu, h0=var0)
        e = r - mu
        if dist == "t":
            from scipy.special import gammaln
            c = gammaln((nu + 1) / 2) - gammaln(nu / 2) - 0.5 * np.log(np.pi * (nu - 2))
            ll = c - 0.5 * np.log(h) - (nu + 1) / 2 * np.log1p(e ** 2 / (h * (nu - 2)))
        else:
            ll = -0.5 * (np.log(2 * np.pi) + np.log(h) + e ** 2 / h)
        return -np.sum(ll)

    x0 = [r.mean(), np.log(0.05 * var0), np.log(0.1 / 0.05), np.log(0.85 / 0.05)]
    if dist == "t":
        x0.append(np.log(6.0))
    res = minimize(nll, x0, method="Nelder-Mead", options={"maxiter": 20000, "xatol": 1e-8, "fatol": 1e-8})
    mu, omega, alpha, beta, nu = unpack(res.x)
    out = {"mu": mu, "omega": omega, "alpha": alpha, "beta": beta,
           "persistence": alpha + beta, "long_run_var": omega / (1 - alpha - beta),
           "loglik": -res.fun}
    if dist == "t":
        out["nu"] = nu
    return out


def garch11_forecast(h_next, omega, alpha, beta, horizon):
    """Multi-step variance forecast: E[h_{t+k}] = V_L + (alpha+beta)^{k-1} (h_{t+1} - V_L).
    Returns array of per-period variances for k = 1..horizon (sum them for the
    horizon variance, e.g. to price a 30-day option or size VaR)."""
    VL = omega / (1 - alpha - beta)
    k = np.arange(horizon)
    return VL + (alpha + beta) ** k * (h_next - VL)


# ----------------------------------------------------------------------------
# Kalman filtering (lectures 44, 92, 95)
# ----------------------------------------------------------------------------
class KalmanFilter:
    """Linear Gaussian state space:
        x_t = F x_{t-1} + w,  w~N(0,Q)      (state transition)
        z_t = H x_t + v,      v~N(0,R)      (observation)
    Call ``step(z)`` per observation; H may be passed per step (time-varying,
    e.g. regression on a changing regressor)."""

    def __init__(self, F, H, Q, R, x0, P0):
        self.F, self.H = np.atleast_2d(F).astype(float), np.atleast_2d(H).astype(float)
        self.Q, self.R = np.atleast_2d(Q).astype(float), np.atleast_2d(R).astype(float)
        self.x, self.P = np.atleast_1d(x0).astype(float), np.atleast_2d(P0).astype(float)

    def predict(self):
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.x

    def update(self, z, H=None):
        H = self.H if H is None else np.atleast_2d(H)
        z = np.atleast_1d(z)
        y = z - H @ self.x                           # innovation
        S = H @ self.P @ H.T + self.R                # innovation covariance
        K = self.P @ H.T @ np.linalg.inv(S)          # Kalman gain
        self.x = self.x + K @ y
        self.P = (np.eye(len(self.x)) - K @ H) @ self.P
        return self.x, y, S

    def step(self, z, H=None):
        self.predict()
        return self.update(z, H)


class KalmanOU:
    """1-D Kalman filter whose hidden state is an OU 'fair value' (lecture 95):
        x_t = phi x_{t-1} + (1-phi) mu + w,   z_t = x_t + v.
    Trading idea: z - x (price minus filtered fair value), scaled by sqrt(P+R),
    is a mean-reversion signal. obs_noise_scale = R / sigma^2 controls smoothing."""

    def __init__(self, phi, mu, sigma_process, obs_noise_scale=1.0):
        self.phi, self.mu = phi, mu
        self.Q = sigma_process ** 2 * max(1 - phi ** 2, 1e-6)
        self.R = sigma_process ** 2 * max(obs_noise_scale, 0.01)
        self.x, self.P = mu, self.R

    def update(self, z):
        self.x = self.phi * self.x + (1 - self.phi) * self.mu
        self.P = self.phi ** 2 * self.P + self.Q
        K = self.P / (self.P + self.R)
        innov = z - self.x
        self.x += K * innov
        self.P *= (1 - K)
        return self.x

    def zscore(self, z):
        return (z - self.x) / np.sqrt(self.P + self.R)

    def forecast(self, steps):
        return self.mu + self.phi ** np.arange(1, steps + 1) * (self.x - self.mu)


def kalman_local_level(z, q, r, x0=None, p0=1e6):
    """Random-walk-plus-noise smoother (online). q/r = signal-to-noise ratio.
    Returns filtered level and its variance."""
    z = np.asarray(z, float)
    x, P = (z[0] if x0 is None else x0), p0
    xs, Ps = np.empty(len(z)), np.empty(len(z))
    for t, zt in enumerate(z):
        P += q
        K = P / (P + r)
        x += K * (zt - x)
        P *= (1 - K)
        xs[t], Ps[t] = x, P
    return xs, Ps


def kalman_regression(y, X, delta=1e-4, r=1e-3):
    """Time-varying regression y_t = X_t beta_t + e (dynamic hedge ratio for pairs
    trading / rolling beta). beta follows a random walk with Q = delta/(1-delta) I.
    Returns betas (T, k) and innovations."""
    y = np.asarray(y, float)
    X = np.atleast_2d(np.asarray(X, float))
    if X.shape[0] != len(y):
        X = X.T
    k = X.shape[1]
    kf = KalmanFilter(np.eye(k), X[0], delta / (1 - delta) * np.eye(k), r, np.zeros(k), np.eye(k))
    betas, innov = np.empty((len(y), k)), np.empty(len(y))
    for t in range(len(y)):
        kf.predict()
        x, e, _ = kf.update(y[t], X[t][None, :])
        betas[t], innov[t] = x, e[0]
    return betas, innov


# ----------------------------------------------------------------------------
# Markov chains (lectures 49, 71)
# ----------------------------------------------------------------------------
def stationary_distribution(P):
    """pi with pi P = pi (left eigenvector for eigenvalue 1)."""
    P = np.asarray(P, float)
    w, v = np.linalg.eig(P.T)
    pi = np.real(v[:, np.argmin(np.abs(w - 1))])
    return pi / pi.sum()


def estimate_transition_matrix(states, n_states=None):
    """MLE transition matrix from an observed integer state sequence."""
    s = np.asarray(states, int)
    n = n_states or s.max() + 1
    C = np.zeros((n, n))
    np.add.at(C, (s[:-1], s[1:]), 1)
    rows = C.sum(axis=1, keepdims=True)
    return np.divide(C, rows, out=np.full_like(C, 1.0 / n), where=rows > 0)


def expected_durations(P):
    """Expected time spent in each state per visit: 1 / (1 - P_ii)."""
    return 1.0 / (1.0 - np.diag(np.asarray(P, float)))


# ----------------------------------------------------------------------------
# Hidden Markov Model with Gaussian emissions (lectures 51, 72, 74)
# ----------------------------------------------------------------------------
class GaussianHMM:
    """1-D Gaussian-emission HMM, log-space forward-backward, Viterbi, Baum-Welch.

    Typical use: regimes of returns or of realized vol.
        hmm = GaussianHMM(3).fit(x)            # or set A, means, stds by hand
        p = hmm.filter(x)                      # P(state_t | x_1..t)  -> tradable, no look-ahead
        g = hmm.smooth(x)                      # P(state_t | x_1..T)  -> analysis only (uses future!)
    States are sorted by mean after fitting (0 = lowest).
    """

    def __init__(self, n_states, A=None, means=None, stds=None, pi0=None):
        self.n = n_states
        self.A = None if A is None else np.asarray(A, float)
        self.means = None if means is None else np.asarray(means, float)
        self.stds = None if stds is None else np.asarray(stds, float)
        self.pi0 = np.full(n_states, 1.0 / n_states) if pi0 is None else np.asarray(pi0, float)

    def _logB(self, x):
        return norm.logpdf(np.asarray(x, float)[:, None], self.means, self.stds)

    def _forward(self, logB):
        T = len(logB)
        la = np.empty((T, self.n))
        logA = np.log(self.A)
        la[0] = np.log(self.pi0) + logB[0]
        for t in range(1, T):
            la[t] = logsumexp(la[t - 1][:, None] + logA, axis=0) + logB[t]
        return la

    def _backward(self, logB):
        T = len(logB)
        lb = np.zeros((T, self.n))
        logA = np.log(self.A)
        for t in range(T - 2, -1, -1):
            lb[t] = logsumexp(logA + logB[t + 1] + lb[t + 1], axis=1)
        return lb

    def loglik(self, x):
        return float(logsumexp(self._forward(self._logB(x))[-1]))

    def filter(self, x):
        la = self._forward(self._logB(x))
        return np.exp(la - logsumexp(la, axis=1, keepdims=True))

    def smooth(self, x):
        logB = self._logB(x)
        lg = self._forward(logB) + self._backward(logB)
        return np.exp(lg - logsumexp(lg, axis=1, keepdims=True))

    def filter_step(self, prior_probs, x_t):
        """One online Bayes update (lecture 74 live regime bot):
        predict with A, weight by emission likelihood, normalize."""
        pred = prior_probs @ self.A
        post = pred * norm.pdf(x_t, self.means, self.stds)
        return post / post.sum()

    def viterbi(self, x):
        logB = self._logB(x)
        T = len(logB)
        logA = np.log(self.A)
        d = np.log(self.pi0) + logB[0]
        bp = np.zeros((T, self.n), int)
        for t in range(1, T):
            m = d[:, None] + logA
            bp[t] = m.argmax(axis=0)
            d = m.max(axis=0) + logB[t]
        path = np.empty(T, int)
        path[-1] = d.argmax()
        for t in range(T - 1, 0, -1):
            path[t - 1] = bp[t, path[t]]
        return path

    def fit(self, x, n_iter=200, tol=1e-6, rng=None):
        """Baum-Welch (EM). Initializes from quantiles of x."""
        x = np.asarray(x, float)
        if self.means is None:
            qs = np.quantile(x, (np.arange(self.n) + 0.5) / self.n)
            self.means = qs.copy()
            self.stds = np.full(self.n, x.std())
        if self.A is None:
            self.A = np.full((self.n, self.n), 0.05 / max(self.n - 1, 1))
            np.fill_diagonal(self.A, 0.95)
        prev = -np.inf
        for _ in range(n_iter):
            logB = self._logB(x)
            la, lb = self._forward(logB), self._backward(logB)
            ll = logsumexp(la[-1])
            lg = la + lb - ll
            g = np.exp(lg)
            lxi = (la[:-1, :, None] + np.log(self.A)[None] + (logB[1:] + lb[1:])[:, None, :] - ll)
            xi = np.exp(lxi).sum(axis=0)
            self.pi0 = g[0] / g[0].sum()
            self.A = xi / xi.sum(axis=1, keepdims=True)
            w = g.sum(axis=0)
            self.means = (g * x[:, None]).sum(axis=0) / w
            self.stds = np.sqrt((g * (x[:, None] - self.means) ** 2).sum(axis=0) / w)
            self.stds = np.maximum(self.stds, 1e-8)
            if ll - prev < tol:
                break
            prev = ll
        order = np.argsort(self.means)
        self.means, self.stds = self.means[order], self.stds[order]
        self.A = self.A[np.ix_(order, order)]
        self.pi0 = self.pi0[order]
        return self
