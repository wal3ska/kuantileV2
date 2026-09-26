"""Derivatives pricing: Black-Scholes, Greeks, implied vol, lattices, PDEs,
Monte Carlo (with variance reduction), exotics, Heston/Bates, variance swaps,
delta-hedging simulation.

Source lectures (Quant Guild Library): 2, 6, 9, 11, 19, 23, 30, 32, 37, 38, 39,
43, 67, 73, 80, 83, 89, 91, 107, 113, 119, 130, 139.

Conventions
-----------
* T in years, r / q continuously compounded annual rates, sigma annualized.
* ``option`` is "call" or "put".
* Every function accepts ``rng`` (np.random.Generator) where randomness is used,
  so results are reproducible: ``rng = np.random.default_rng(42)``.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.integrate import quad
from scipy.linalg import solve_banded
from scipy.optimize import brentq
from scipy.stats import norm

__all__ = [
    "bs_price", "bs_greeks", "implied_vol", "binomial_crr", "fd_crank_nicolson",
    "mc_european", "mc_price_paths", "barrier_payoff", "asian_arith_payoff",
    "geometric_asian_price", "mc_asian_cv",
    "HestonParams", "heston_cf", "heston_price", "heston_fft_calls", "heston_paths",
    "bates_paths", "variance_swap_strike", "delta_hedge_pnl",
]


# ----------------------------------------------------------------------------
# Black-Scholes-Merton
# ----------------------------------------------------------------------------
def _d1d2(S, K, T, r, sigma, q=0.0):
    S, K, T, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, sigma))
    vs = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / vs
    return d1, d1 - vs


def bs_price(S, K, T, r, sigma, q=0.0, option="call"):
    """Black-Scholes-Merton price of a European option (vectorized)."""
    if np.any(np.asarray(T) <= 0):
        intrinsic = np.maximum(S - K, 0) if option == "call" else np.maximum(K - S, 0)
        if np.ndim(T) == 0:
            return intrinsic
    d1, d2 = _d1d2(S, K, T, r, sigma, q)
    dfq, dfr = np.exp(-q * np.asarray(T)), np.exp(-r * np.asarray(T))
    if option == "call":
        return S * dfq * norm.cdf(d1) - K * dfr * norm.cdf(d2)
    if option == "put":
        return K * dfr * norm.cdf(-d2) - S * dfq * norm.cdf(-d1)
    raise ValueError("option must be 'call' or 'put'")


def bs_greeks(S, K, T, r, sigma, q=0.0, option="call"):
    """Greeks. vega/rho per 1.00 change (divide by 100 for per-1%); theta per year
    (divide by 365 for per-calendar-day)."""
    d1, d2 = _d1d2(S, K, T, r, sigma, q)
    T = np.asarray(T, dtype=float)
    dfq, dfr = np.exp(-q * T), np.exp(-r * T)
    pdf = norm.pdf(d1)
    gamma = dfq * pdf / (S * sigma * np.sqrt(T))
    vega = S * dfq * pdf * np.sqrt(T)
    common_theta = -S * dfq * pdf * sigma / (2 * np.sqrt(T))
    if option == "call":
        delta = dfq * norm.cdf(d1)
        theta = common_theta - r * K * dfr * norm.cdf(d2) + q * S * dfq * norm.cdf(d1)
        rho = K * T * dfr * norm.cdf(d2)
    else:
        delta = -dfq * norm.cdf(-d1)
        theta = common_theta + r * K * dfr * norm.cdf(-d2) - q * S * dfq * norm.cdf(-d1)
        rho = -K * T * dfr * norm.cdf(-d2)
    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta, "rho": rho}


def implied_vol(price, S, K, T, r, q=0.0, option="call", lo=1e-6, hi=5.0):
    """Black-Scholes implied volatility via Brent root finding.

    Returns np.nan when the price violates no-arbitrage bounds (common with
    stale/wide option quotes -- filter those out instead of forcing a number).
    """
    dfq, dfr = np.exp(-q * T), np.exp(-r * T)
    if option == "call":
        lower, upper = max(S * dfq - K * dfr, 0.0), S * dfq
    else:
        lower, upper = max(K * dfr - S * dfq, 0.0), K * dfr
    if not (lower - 1e-12 <= price <= upper + 1e-12):
        return np.nan
    f = lambda s: bs_price(S, K, T, r, s, q, option) - price
    try:
        return brentq(f, lo, hi, xtol=1e-10, maxiter=200)
    except ValueError:
        return np.nan


# ----------------------------------------------------------------------------
# Lattice and PDE methods
# ----------------------------------------------------------------------------
def binomial_crr(S, K, T, r, sigma, n=500, q=0.0, option="call", american=False):
    """Cox-Ross-Rubinstein binomial tree (European or American)."""
    dt = T / n
    u = np.exp(sigma * np.sqrt(dt))
    d = 1.0 / u
    p = (np.exp((r - q) * dt) - d) / (u - d)
    if not 0 < p < 1:
        raise ValueError("Risk-neutral probability outside (0,1); increase n.")
    disc = np.exp(-r * dt)
    j = np.arange(n + 1)
    ST = S * u ** (n - j) * d ** j
    payoff = (lambda x: np.maximum(x - K, 0)) if option == "call" else (lambda x: np.maximum(K - x, 0))
    V = payoff(ST)
    for i in range(n - 1, -1, -1):
        V = disc * (p * V[:-1] + (1 - p) * V[1:])
        if american:
            Si = S * u ** (i - np.arange(i + 1)) * d ** np.arange(i + 1)
            V = np.maximum(V, payoff(Si))
    return float(V[0])


def fd_crank_nicolson(S, K, T, r, sigma, q=0.0, option="call", american=False,
                      n_space=300, n_time=300, s_max_mult=4.0):
    """Crank-Nicolson finite-difference solution of the Black-Scholes PDE.

    Unconditionally stable (the explicit scheme needs dt <= dS^2/(sigma^2 S_max^2)).
    American exercise handled by projection onto the payoff each step.
    Returns the price at S (linear interpolation on the grid).
    """
    s_max = s_max_mult * max(S, K)
    ds = s_max / n_space
    dt = T / n_time
    s = np.linspace(0, s_max, n_space + 1)
    payoff = np.maximum(s - K, 0) if option == "call" else np.maximum(K - s, 0)
    V = payoff.copy()
    i = np.arange(1, n_space)
    a = 0.25 * dt * (sigma ** 2 * i ** 2 - (r - q) * i)
    b = -0.5 * dt * (sigma ** 2 * i ** 2 + r)
    c = 0.25 * dt * (sigma ** 2 * i ** 2 + (r - q) * i)
    # LHS matrix (banded): -a V_{i-1} + (1-b) V_i - c V_{i+1}
    ab = np.zeros((3, n_space - 1))
    ab[0, 1:] = -c[:-1]
    ab[1, :] = 1 - b
    ab[2, :-1] = -a[1:]
    for k in range(n_time):
        tau = (k + 1) * dt  # time to maturity after this step
        if option == "call":
            lo_bc, hi_bc = 0.0, s_max * np.exp(-q * tau) - K * np.exp(-r * tau)
        else:
            lo_bc, hi_bc = K * np.exp(-r * tau), 0.0
        if american:
            lo_bc = max(lo_bc, payoff[0]); hi_bc = max(hi_bc, payoff[-1])
        rhs = a * V[:-2] + (1 + b) * V[1:-1] + c * V[2:]
        rhs[0] += a[0] * lo_bc
        rhs[-1] += c[-1] * hi_bc
        V[1:-1] = solve_banded((1, 1), ab, rhs)
        V[0], V[-1] = lo_bc, hi_bc
        if american:
            V = np.maximum(V, payoff)
    return float(np.interp(S, s, V))


# ----------------------------------------------------------------------------
# Monte Carlo
# ----------------------------------------------------------------------------
def mc_european(S, K, T, r, sigma, q=0.0, option="call", n_paths=100_000,
                antithetic=True, control_variate=True, rng=None):
    """European option by MC with antithetic variates and an S_T control variate.

    Returns (price, standard_error). The control variate uses
    E[e^{-rT} S_T] = S e^{-qT} with the optimal coefficient c* = Cov/Var.
    """
    rng = rng or np.random.default_rng()
    half = n_paths // 2 if antithetic else n_paths
    Z = rng.standard_normal(half)
    if antithetic:
        Z = np.concatenate([Z, -Z])
    ST = S * np.exp((r - q - 0.5 * sigma ** 2) * T + sigma * np.sqrt(T) * Z)
    disc = np.exp(-r * T)
    Y = disc * (np.maximum(ST - K, 0) if option == "call" else np.maximum(K - ST, 0))
    if control_variate:
        X = disc * ST
        c = np.cov(Y, X)[0, 1] / np.var(X, ddof=1)
        Y = Y - c * (X - S * np.exp(-q * T))
    if antithetic:  # pair-average so the SE accounts for the induced correlation
        Y = 0.5 * (Y[:half] + Y[half:])
    return float(Y.mean()), float(Y.std(ddof=1) / np.sqrt(len(Y)))


def mc_price_paths(paths, payoff_fn, r, T):
    """Generic path-dependent MC pricer. ``paths`` shape (n_paths, n_steps+1).
    ``payoff_fn(paths) -> (n_paths,)``. Returns (price, standard_error)."""
    Y = np.exp(-r * T) * payoff_fn(paths)
    return float(Y.mean()), float(Y.std(ddof=1) / np.sqrt(len(Y)))


def barrier_payoff(K, B, kind="up-and-in", option="call"):
    """Discretely-monitored barrier payoff factory for ``mc_price_paths``.
    Note: discrete monitoring misses crossings between steps; use many steps or
    the Broadie-Glasserman-Kou shift B*exp(+-0.5826*sigma*sqrt(dt))."""
    def f(p):
        up = "up" in kind
        hit = (p.max(axis=1) >= B) if up else (p.min(axis=1) <= B)
        alive = hit if kind.endswith("in") else ~hit
        ST = p[:, -1]
        vanilla = np.maximum(ST - K, 0) if option == "call" else np.maximum(K - ST, 0)
        return vanilla * alive
    return f


def asian_arith_payoff(K, option="call"):
    """Arithmetic-average Asian payoff (average over monitoring dates, excl. t=0)."""
    def f(p):
        A = p[:, 1:].mean(axis=1)
        return np.maximum(A - K, 0) if option == "call" else np.maximum(K - A, 0)
    return f


def geometric_asian_price(S, K, T, r, sigma, n_obs, q=0.0):
    """Closed-form discretely monitored geometric-average Asian call
    (monitoring at T/n, 2T/n, ..., T). Used as a control variate."""
    mu = np.log(S) + (r - q - 0.5 * sigma ** 2) * T * (n_obs + 1) / (2 * n_obs)
    var = sigma ** 2 * T * (n_obs + 1) * (2 * n_obs + 1) / (6 * n_obs ** 2)
    d1 = (mu - np.log(K) + var) / np.sqrt(var)
    d2 = d1 - np.sqrt(var)
    return float(np.exp(-r * T) * (np.exp(mu + 0.5 * var) * norm.cdf(d1) - K * norm.cdf(d2)))


def mc_asian_cv(S, K, T, r, sigma, n_obs=252, n_paths=50_000, q=0.0, rng=None):
    """Arithmetic Asian call with the geometric Asian as control variate
    (lecture 2 idea: subtract c*(control - E[control])). Returns (price, se)."""
    from .processes import gbm_paths
    paths = gbm_paths(S, r - q, sigma, T, n_obs, n_paths, rng=rng)
    disc = np.exp(-r * T)
    Y = disc * np.maximum(paths[:, 1:].mean(axis=1) - K, 0)
    X = disc * np.maximum(np.exp(np.log(paths[:, 1:]).mean(axis=1)) - K, 0)
    c = np.cov(Y, X)[0, 1] / np.var(X, ddof=1)
    adj = Y - c * (X - geometric_asian_price(S, K, T, r, sigma, n_obs, q))
    return float(adj.mean()), float(adj.std(ddof=1) / np.sqrt(n_paths))


# ----------------------------------------------------------------------------
# Heston / Bates stochastic volatility
# ----------------------------------------------------------------------------
@dataclass
class HestonParams:
    kappa: float  # mean-reversion speed of variance
    theta: float  # long-run variance
    sigma: float  # vol of variance ("xi")
    rho: float    # corr(dW_S, dW_v), typically negative for equities
    v0: float     # initial variance

    def feller_ok(self) -> bool:
        """2*kappa*theta > sigma^2 keeps variance strictly positive."""
        return 2 * self.kappa * self.theta > self.sigma ** 2


def heston_cf(u, T, S0, r, q, p: HestonParams):
    """phi(u) = E_Q[exp(i u ln S_T)], "little Heston trap" form (Albrecher et al.)."""
    i = 1j
    b = p.kappa - p.rho * p.sigma * i * u
    d = np.sqrt(b * b + p.sigma ** 2 * (i * u + u * u))
    g = (b - d) / (b + d)
    e = np.exp(-d * T)
    C = i * u * (r - q) * T + (p.kappa * p.theta / p.sigma ** 2) * (
        (b - d) * T - 2.0 * np.log((1 - g * e) / (1 - g)))
    D = ((b - d) / p.sigma ** 2) * ((1 - e) / (1 - g * e))
    return np.exp(C + D * p.v0 + i * u * np.log(S0))


def heston_price(S0, K, T, r, p: HestonParams, q=0.0, option="call", u_max=200.0):
    """Heston price by Gil-Pelaez inversion (P1/P2 probabilities, numerical quad).
    Accurate reference; use ``heston_fft_calls`` for a whole strike grid."""
    lnK = np.log(K)
    fwd = S0 * np.exp((r - q) * T)
    phi = lambda u: heston_cf(u, T, S0, r, q, p)
    i1 = lambda u: np.real(np.exp(-1j * u * lnK) * phi(u - 1j) / (1j * u * fwd))
    i2 = lambda u: np.real(np.exp(-1j * u * lnK) * phi(u) / (1j * u))
    P1 = 0.5 + quad(i1, 1e-10, u_max, limit=500)[0] / np.pi
    P2 = 0.5 + quad(i2, 1e-10, u_max, limit=500)[0] / np.pi
    call = S0 * np.exp(-q * T) * P1 - K * np.exp(-r * T) * P2
    if option == "call":
        return float(call)
    return float(call - S0 * np.exp(-q * T) + K * np.exp(-r * T))  # put-call parity


def heston_fft_calls(S0, T, r, p: HestonParams, q=0.0, N=4096, eta=0.25, alpha=1.5):
    """Carr-Madan FFT: call prices on a log-strike grid in one O(N log N) pass.
    Returns (strikes, call_prices). Interpolate for a particular K."""
    lam = 2 * np.pi / (N * eta)            # log-strike spacing
    b = N * lam / 2                        # log-strike range [-b, b) around 0
    v = eta * np.arange(N)
    k = -b + lam * np.arange(N) + np.log(S0)   # centre grid at ln S0
    psi = np.exp(-r * T) * heston_cf(v - (alpha + 1) * 1j, T, S0, r, q, p) / (
        alpha ** 2 + alpha - v ** 2 + 1j * (2 * alpha + 1) * v)
    w = np.ones(N); w[1:-1:2] = 4; w[2:-1:2] = 2; w[0] = w[-1] = 1  # Simpson
    x = np.exp(1j * v * (b - np.log(S0))) * psi * eta * w / 3
    calls = np.real(np.exp(-alpha * k) / np.pi * np.fft.fft(x))
    return np.exp(k), calls


def heston_paths(S0, T, r, p: HestonParams, n_steps=252, n_paths=10_000, q=0.0, rng=None):
    """Full-truncation Euler (log-Euler for S). Returns (S, v), each (n_paths, n_steps+1)."""
    rng = rng or np.random.default_rng()
    dt = T / n_steps
    S = np.empty((n_paths, n_steps + 1)); v = np.empty_like(S)
    S[:, 0], v[:, 0] = S0, p.v0
    for t in range(n_steps):
        z1 = rng.standard_normal(n_paths)
        z2 = p.rho * z1 + np.sqrt(1 - p.rho ** 2) * rng.standard_normal(n_paths)
        vp = np.maximum(v[:, t], 0)
        S[:, t + 1] = S[:, t] * np.exp((r - q - 0.5 * vp) * dt + np.sqrt(vp * dt) * z1)
        v[:, t + 1] = v[:, t] + p.kappa * (p.theta - vp) * dt + p.sigma * np.sqrt(vp * dt) * z2
    return S, np.maximum(v, 0)


def bates_paths(S0, T, r, p: HestonParams, lam_j, mu_j, sigma_j, n_steps=252,
                n_paths=10_000, q=0.0, rng=None):
    """Bates = Heston + Merton lognormal jumps (lecture 83). Drift is
    compensated by lam_j*k, k = E[e^J]-1, so e^{-rT}E[S_T] = S0 e^{-qT}."""
    rng = rng or np.random.default_rng()
    dt = T / n_steps
    k = np.exp(mu_j + 0.5 * sigma_j ** 2) - 1
    S = np.empty((n_paths, n_steps + 1)); S[:, 0] = S0
    v = np.full(n_paths, p.v0)
    for t in range(n_steps):
        z1 = rng.standard_normal(n_paths)
        z2 = p.rho * z1 + np.sqrt(1 - p.rho ** 2) * rng.standard_normal(n_paths)
        nj = rng.poisson(lam_j * dt, n_paths)
        J = mu_j * nj + sigma_j * np.sqrt(nj) * rng.standard_normal(n_paths)
        vp = np.maximum(v, 0)
        S[:, t + 1] = S[:, t] * np.exp((r - q - lam_j * k - 0.5 * vp) * dt + np.sqrt(vp * dt) * z1 + J)
        v = v + p.kappa * (p.theta - vp) * dt + p.sigma * np.sqrt(vp * dt) * z2
    return S


# ----------------------------------------------------------------------------
# Variance swaps (lecture 91: Demeterfi-Derman-Kamal-Zou replication)
# ----------------------------------------------------------------------------
def variance_swap_strike(strikes, otm_prices, S0, T, r, q=0.0):
    """Fair variance strike K_var (annualized variance) from a strip of OTM options:

        K_var = (2 e^{rT} / T) * integral( Q(K) / K^2 dK )

    where Q(K) is the OTM put for K < F and OTM call for K >= F.
    Vol-swap strike ~ sqrt(K_var) minus a convexity adjustment
    (Var[sigma^2] / (8 K_var^{3/2})) -- vol swaps are worth less than sqrt(var swaps).
    """
    strikes = np.asarray(strikes, float); otm = np.asarray(otm_prices, float)
    F = S0 * np.exp((r - q) * T)
    integral = np.trapezoid(otm / strikes ** 2, strikes)
    # correction when the strip's separating strike K0 != F (K0 = largest strike <= F)
    K0 = strikes[strikes <= F].max()
    return float(2 * np.exp(r * T) / T * integral - (F / K0 - 1) ** 2 / T)


# ----------------------------------------------------------------------------
# Delta hedging (lectures 9, 11, 23)
# ----------------------------------------------------------------------------
def delta_hedge_pnl(S0, K, T, r, sigma_implied, sigma_real, mu=None, n_steps=252,
                    n_paths=5_000, q=0.0, short=True, rng=None):
    """Simulate discretely delta-hedged option P&L (option sold at implied vol,
    underlying follows GBM with realized vol). Returns terminal P&L per path.

    Theory: continuous hedge P&L ~ 0.5 * integral Gamma S^2 (sigma_imp^2 - sigma_real^2) dt
    for the short option. Discrete hedging adds noise ~ O(1/sqrt(n_steps)).
    """
    from .processes import gbm_paths
    rng = rng or np.random.default_rng()
    mu = r if mu is None else mu
    S = gbm_paths(S0, mu - q, sigma_real, T, n_steps, n_paths, rng=rng)
    dt = T / n_steps
    sign = -1.0 if short else 1.0
    premium = bs_price(S0, K, T, r, sigma_implied, q)
    cash = -sign * premium  # short: receive premium
    pos = 0.0
    for t in range(n_steps):
        tau = T - t * dt
        delta = bs_greeks(S[:, t], K, tau, r, sigma_implied, q)["delta"]
        target = -sign * delta  # short call -> long delta shares
        cash = cash - (target - pos) * S[:, t]
        pos = target
        cash = cash * np.exp(r * dt) + pos * S[:, t] * (np.exp(q * dt) - 1)
    payoff = np.maximum(S[:, -1] - K, 0)
    return cash + pos * S[:, -1] + sign * payoff
