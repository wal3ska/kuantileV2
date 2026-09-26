"""Stochastic processes and random-variable generation.

Source lectures: 1 (inverse transform), 7/36/51/58/59/81 (OU), 25 (fBM Davies-Harte),
27/103/125 (Brownian bridge), 29/31/37 (Ito, SDEs), 59/135 (ABM/GBM),
82 (Poisson), 85 (Volterra), 94 (Hawkes), 102 (Markovian lifting of rough vol).

All path generators return arrays of shape (n_paths, n_steps + 1) including t=0.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import nnls
from scipy.special import gamma as gamma_fn

__all__ = [
    "inverse_transform", "inverse_transform_discrete",
    "abm_paths", "gbm_paths", "gbm_moments", "correlated_gbm_paths", "ou_paths",
    "brownian_bridge", "log_bridge_to_cagr",
    "fbm_davies_harte", "volterra_paths", "rl_kernel", "markovian_lift", "lifted_volterra_paths",
    "poisson_times", "inhomogeneous_poisson_times", "merton_jump_paths",
    "hawkes_simulate", "hawkes_loglik", "hawkes_fit",
]


# ----------------------------------------------------------------------------
# Random variable generation (lecture 1)
# ----------------------------------------------------------------------------
def inverse_transform(ppf, n, rng=None):
    """X = F^{-1}(U), U~Uniform(0,1). ``ppf`` is the inverse CDF, e.g.
    ``lambda u: -np.log(1 - u) / lam`` for Exponential(lam)."""
    rng = rng or np.random.default_rng()
    return ppf(rng.random(n))


def inverse_transform_discrete(values, probs, n, rng=None):
    """Discrete inverse transform: search U in the cumulative distribution."""
    rng = rng or np.random.default_rng()
    cdf = np.cumsum(probs)
    cdf[-1] = 1.0
    return np.asarray(values)[np.searchsorted(cdf, rng.random(n), side="right")]


# ----------------------------------------------------------------------------
# Brownian motions (lectures 59, 135)
# ----------------------------------------------------------------------------
def abm_paths(x0, mu, sigma, T, n_steps, n_paths, rng=None):
    """Arithmetic BM: dX = mu dt + sigma dW (can go negative; X_T ~ N(x0+mu T, sigma^2 T))."""
    rng = rng or np.random.default_rng()
    dt = T / n_steps
    inc = mu * dt + sigma * np.sqrt(dt) * rng.standard_normal((n_paths, n_steps))
    return np.hstack([np.full((n_paths, 1), x0), x0 + np.cumsum(inc, axis=1)])


def gbm_paths(s0, mu, sigma, T, n_steps, n_paths, rng=None, antithetic=False):
    """Geometric BM, exact log scheme: S_{t+dt} = S_t exp((mu - sigma^2/2)dt + sigma dW).
    For risk-neutral pricing pass mu = r - q."""
    rng = rng or np.random.default_rng()
    dt = T / n_steps
    if antithetic:
        Z = rng.standard_normal((n_paths // 2, n_steps)); Z = np.vstack([Z, -Z])
    else:
        Z = rng.standard_normal((n_paths, n_steps))
    logret = (mu - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * Z
    return s0 * np.exp(np.hstack([np.zeros((Z.shape[0], 1)), np.cumsum(logret, axis=1)]))


def gbm_moments(s0, mu, sigma, t):
    """Key GBM facts (volatility drag, lectures 117/135/136):
    mean = s0 e^{mu t}; median = s0 e^{(mu - sigma^2/2) t};
    geometric (typical path) growth rate = mu - sigma^2/2."""
    return {
        "mean": s0 * np.exp(mu * t),
        "median": s0 * np.exp((mu - 0.5 * sigma ** 2) * t),
        "variance": s0 ** 2 * np.exp(2 * mu * t) * (np.exp(sigma ** 2 * t) - 1),
        "geometric_growth_rate": mu - 0.5 * sigma ** 2,
        "prob_below_start": _norm_cdf(-(mu - 0.5 * sigma ** 2) * np.sqrt(t) / sigma),
    }


def _norm_cdf(x):
    from scipy.stats import norm
    return norm.cdf(x)


def correlated_gbm_paths(s0, mu, cov, T, n_steps, n_paths, rng=None):
    """Multi-asset GBM with annualized covariance ``cov`` (Cholesky).
    Returns array (n_paths, n_steps+1, n_assets)."""
    rng = rng or np.random.default_rng()
    s0, mu, cov = np.asarray(s0, float), np.asarray(mu, float), np.asarray(cov, float)
    L = np.linalg.cholesky(cov)
    dt = T / n_steps
    Z = rng.standard_normal((n_paths, n_steps, len(s0))) @ L.T
    logret = (mu - 0.5 * np.diag(cov)) * dt + np.sqrt(dt) * Z
    cum = np.concatenate([np.zeros((n_paths, 1, len(s0))), np.cumsum(logret, axis=1)], axis=1)
    return s0 * np.exp(cum)


def ou_paths(x0, kappa, theta, sigma, T, n_steps, n_paths, rng=None):
    """Ornstein-Uhlenbeck dX = kappa(theta - X)dt + sigma dW, *exact* transition:
    X_{t+dt} = theta + (X_t - theta)e^{-kappa dt} + sigma sqrt((1-e^{-2 kappa dt})/(2 kappa)) Z.
    Stationary variance sigma^2/(2 kappa); half-life ln2/kappa."""
    rng = rng or np.random.default_rng()
    dt = T / n_steps
    e = np.exp(-kappa * dt)
    sd = sigma * np.sqrt((1 - e ** 2) / (2 * kappa))
    X = np.empty((n_paths, n_steps + 1)); X[:, 0] = x0
    Z = rng.standard_normal((n_paths, n_steps))
    for t in range(n_steps):
        X[:, t + 1] = theta + (X[:, t] - theta) * e + sd * Z[:, t]
    return X


# ----------------------------------------------------------------------------
# Brownian bridge (lectures 27, 103, 125)
# ----------------------------------------------------------------------------
def brownian_bridge(a, b, T, n_steps, n_paths=1, sigma=1.0, rng=None):
    """Brownian bridge pinned at X_0=a, X_T=b: X_t = a + W_t - (t/T)(W_T - (b-a)).
    Var(X_t) = sigma^2 t (T-t)/T."""
    rng = rng or np.random.default_rng()
    W = abm_paths(0.0, 0.0, sigma, T, n_steps, n_paths, rng)
    t = np.linspace(0, T, n_steps + 1)
    return a + W - (t / T) * (W[:, -1:] - (b - a))


def log_bridge_to_cagr(s0, cagr, sigma, T_years, n_steps, n_paths=1, rng=None):
    """Price paths that all end exactly at s0*(1+cagr)^T but wander with vol sigma
    (lecture 125: the same CAGR can hide wildly different paths/drawdowns)."""
    end = np.log(s0) + T_years * np.log1p(cagr)
    return np.exp(brownian_bridge(np.log(s0), end, T_years, n_steps, n_paths, sigma, rng))


# ----------------------------------------------------------------------------
# Rough / fractional processes (lectures 25, 85, 102)
# ----------------------------------------------------------------------------
def fbm_davies_harte(n, H, T=1.0, n_paths=1, rng=None):
    """Exact fractional Brownian motion on n steps via circulant embedding (FFT).
    H<0.5 rough/anti-persistent, H=0.5 BM, H>0.5 persistent.
    Returns (t, paths) with paths shape (n_paths, n+1)."""
    rng = rng or np.random.default_rng()
    k = np.arange(n + 1)
    gam = 0.5 * (np.abs(k + 1) ** (2 * H) - 2 * np.abs(k) ** (2 * H) + np.abs(k - 1) ** (2 * H))
    c = np.concatenate([gam, gam[-2:0:-1]])          # length 2n
    lam = np.fft.fft(c).real
    if np.any(lam < -1e-10):
        raise ValueError("Circulant embedding not PSD for this (n, H).")
    lam = np.clip(lam, 0, None)
    M = 2 * n
    W = rng.standard_normal((n_paths, M)) + 1j * rng.standard_normal((n_paths, M))
    fgn = np.fft.fft(np.sqrt(lam / M) * W, axis=1)[:, :n].real * (T / n) ** H
    t = np.linspace(0, T, n + 1)
    return t, np.hstack([np.zeros((n_paths, 1)), np.cumsum(fgn, axis=1)])


def rl_kernel(H, normalize="rl"):
    """Fractional Volterra kernel K(t) = c t^{H-1/2}.
    normalize='rl' -> c = sqrt(2H) (Riemann-Liouville fBM, Var X_t = t^{2H});
    normalize='gamma' -> c = 1/Gamma(H+1/2) (rough Heston convention)."""
    c = np.sqrt(2 * H) if normalize == "rl" else 1.0 / gamma_fn(H + 0.5)
    return lambda t: c * np.power(t, H - 0.5)


def volterra_paths(kernel, T, n_steps, n_paths=1, rng=None, dW=None):
    """X_t = int_0^t K(t-s) dW_s by direct convolution (O(n^2), lecture 85).

    Weights are variance-matched per lag bin, w_k = sqrt(int_{k dt}^{(k+1)dt} K(s)^2 ds / dt),
    so Var(X_t) is exact even for the singular rough kernel (H<1/2), where naive
    left-point/midpoint evaluation badly underestimates the variance."""
    from scipy.integrate import quad
    rng = rng or np.random.default_rng()
    dt = T / n_steps
    if dW is None:
        dW = np.sqrt(dt) * rng.standard_normal((n_paths, n_steps))
    w = np.array([np.sqrt(quad(lambda s: kernel(s) ** 2, k * dt, (k + 1) * dt)[0] / dt)
                  for k in range(n_steps)])
    X = np.zeros((dW.shape[0], n_steps + 1))
    for i in range(1, n_steps + 1):
        X[:, i] = dW[:, :i] @ w[:i][::-1]
    return X


def markovian_lift(kernel, T, n_factors=10, x_min=None, x_max=None, n_fit=400):
    """Markovian lifting (lecture 102, Abi Jaber & El Euch): approximate a
    completely monotone kernel by a sum of exponentials

        K(t) ~ sum_i c_i exp(-x_i t),

    so the non-Markov Volterra process becomes a sum of n_factors OU factors,
    each Markov: dY_i = -x_i Y_i dt + dW, X = sum c_i Y_i.
    Mean reversions x_i on a geometric grid; weights c_i >= 0 by NNLS on a
    log-spaced time grid. Returns (c, x)."""
    x_min = x_min or 0.1 / T
    x_max = x_max or 1e4 / T
    x = np.geomspace(x_min, x_max, n_factors)
    t = np.geomspace(T / 1e4, T, n_fit)
    A = np.exp(-np.outer(t, x))
    target = kernel(t)
    wts = 1.0 / np.maximum(np.abs(target), 1e-12)   # relative error fit
    c, _ = nnls(A * wts[:, None], target * wts)
    return c, x


def lifted_volterra_paths(c, x, T, n_steps, n_paths=1, rng=None, dW=None):
    """Simulate X = sum c_i Y_i with exact OU-factor updates driven by common dW.
    O(n_steps * n_factors) instead of O(n_steps^2)."""
    rng = rng or np.random.default_rng()
    dt = T / n_steps
    if dW is None:
        dW = np.sqrt(dt) * rng.standard_normal((n_paths, n_steps))
    e = np.exp(-x * dt)
    # variance-matched increment: Var(int_bin e^{-x(t-s)} dW) = (1-e^{-2x dt})/(2x)
    g = np.sqrt(-np.expm1(-2 * x * dt) / (2 * x * dt))
    Y = np.zeros((dW.shape[0], len(x)))
    X = np.zeros((dW.shape[0], n_steps + 1))
    for i in range(n_steps):
        Y = Y * e + dW[:, i:i + 1] * g
        X[:, i + 1] = Y @ c
    return X


# ----------------------------------------------------------------------------
# Jump / point processes (lectures 82, 83, 94)
# ----------------------------------------------------------------------------
def poisson_times(lam, T, rng=None):
    """Homogeneous Poisson arrival times on [0,T] (exponential inter-arrivals)."""
    rng = rng or np.random.default_rng()
    n = rng.poisson(lam * T)
    return np.sort(rng.uniform(0, T, n))


def inhomogeneous_poisson_times(lam_fn, lam_max, T, rng=None):
    """Lewis-Shedler thinning for time-varying intensity lam_fn(t) <= lam_max
    (e.g. intraday U-shaped order arrival)."""
    rng = rng or np.random.default_rng()
    cand = poisson_times(lam_max, T, rng)
    keep = rng.random(len(cand)) < lam_fn(cand) / lam_max
    return cand[keep]


def merton_jump_paths(s0, mu, sigma, lam, mu_j, sigma_j, T, n_steps, n_paths, rng=None):
    """Merton jump-diffusion with compensated drift (so E[S_T] = s0 e^{mu T})."""
    rng = rng or np.random.default_rng()
    dt = T / n_steps
    k = np.exp(mu_j + 0.5 * sigma_j ** 2) - 1
    N = rng.poisson(lam * dt, (n_paths, n_steps))
    J = mu_j * N + sigma_j * np.sqrt(N) * rng.standard_normal((n_paths, n_steps))
    logret = (mu - lam * k - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * rng.standard_normal((n_paths, n_steps)) + J
    return s0 * np.exp(np.hstack([np.zeros((n_paths, 1)), np.cumsum(logret, axis=1)]))


def hawkes_simulate(mu, alpha, beta, T, rng=None):
    """Self-exciting Hawkes process, exponential kernel, via Ogata thinning:
        lambda(t) = mu + sum_{t_i<t} alpha exp(-beta (t - t_i)).
    Stationary iff branching ratio alpha/beta < 1; mean rate mu/(1 - alpha/beta).
    Models volatility/trade clustering (lecture 94)."""
    rng = rng or np.random.default_rng()
    t, times, excite = 0.0, [], 0.0   # excite = lambda(t) - mu just after t
    while True:
        lam_bar = mu + excite
        w = rng.exponential(1 / lam_bar)
        t += w
        if t > T:
            break
        excite *= np.exp(-beta * w)
        if rng.random() * lam_bar <= mu + excite:
            times.append(t)
            excite += alpha
    return np.array(times)


def hawkes_loglik(params, times, T):
    """Exact log-likelihood of an exponential Hawkes process (O(n) recursion)."""
    mu, alpha, beta = params
    if mu <= 0 or alpha < 0 or beta <= 0:
        return -np.inf
    A, ll, prev = 0.0, 0.0, None
    for t in times:
        if prev is not None:
            A = np.exp(-beta * (t - prev)) * (1 + A)
        ll += np.log(mu + alpha * A)
        prev = t
    comp = mu * T + (alpha / beta) * np.sum(1 - np.exp(-beta * (T - times)))
    return ll - comp


def hawkes_fit(times, T, x0=(0.5, 0.5, 1.0)):
    """MLE of (mu, alpha, beta)."""
    from scipy.optimize import minimize
    res = minimize(lambda p: -hawkes_loglik(np.exp(p), times, T), np.log(x0), method="Nelder-Mead",
                   options={"maxiter": 4000, "xatol": 1e-6, "fatol": 1e-6})
    return dict(zip(("mu", "alpha", "beta"), np.exp(res.x)))
