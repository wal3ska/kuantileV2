---
name: qg-derivatives-pricing
description: Price and hedge options in code — Black-Scholes, Greeks, implied vol, CRR tree, Crank-Nicolson PDE, Monte Carlo with variance reduction, exotics, Heston/Bates, variance swaps, delta-hedge P&L (Quant Guild methods).
---

# Derivatives pricing (Quant Guild methods)

Methods distilled from the Quant Guild Library (Roman Paolucci — github.com/romanmichaelpaolucci/Quant-Guild-Library, youtube.com/@QuantGuild), rewritten as clean, vectorized, tested code in the `qglib` package (`qglib.pricing`). Use this skill when the user wants to implement, choose, debug or explain an option-pricing / hedging method inside a code project. Turkish triggers: opsiyon fiyatlama, Black-Scholes, Yunanlar (Greeks), zımni volatilite, Monte Carlo, Heston, varyans swap, delta hedge.

## Step 0 — Integrate with the project first

1. Look for the library: search the project for `qglib` (a `qglib/` folder or `import qglib`). If present, **call it, don't re-implement**: `from qglib import pricing as P`.
2. If absent, ask whether to vendor it (the user has the `qglib` package + tests; copy `qglib/` into the project and `pip install -e .`) or implement inline from the reference code below. Keep the same function names/signatures so later vendoring is drop-in.
3. Match the project's conventions (pandas vs numpy, typing, logging). Keep pricing functions pure: inputs in, numbers out; no I/O or plotting inside them.
4. Every new pricer ships with a test from the **Validation** list.

Conventions: `T` in years; `r`, `q` continuous annual rates; `sigma` annualized; `option in {"call","put"}`; randomness via `rng = np.random.default_rng(seed)` passed explicitly.

## Method selection

| Need | Method | qglib function |
|---|---|---|
| European vanilla, flat vol | Black-Scholes-Merton closed form | `bs_price`, `bs_greeks` |
| Vol from a market price | Brent root-find on BS (return NaN on arbitrage violation) | `implied_vol` |
| American exercise | CRR binomial (n≈500–2000) or CN PDE with projection | `binomial_crr(..., american=True)`, `fd_crank_nicolson(..., american=True)` |
| Grid of prices / Greeks from PDE | Crank-Nicolson (unconditionally stable) | `fd_crank_nicolson` |
| Path-dependent (barrier, Asian, lookback) | Monte Carlo on simulated paths | `mc_price_paths` + `barrier_payoff` / `asian_arith_payoff` |
| Tighter MC | Antithetic + control variates (S_T, geometric Asian) | `mc_european`, `mc_asian_cv` |
| Skew / smile, stochastic vol | Heston: Gil-Pelaez integral (single K) or Carr-Madan FFT (strike grid) | `heston_price`, `heston_fft_calls` |
| Exotics under stochastic vol | Heston full-truncation Euler MC | `heston_paths` |
| Jumps + stoch vol (crash risk) | Bates MC (compensated jumps) | `bates_paths` |
| Variance / vol swap | Static replication with OTM option strip (DDKZ / VIX formula) | `variance_swap_strike` |
| How much does hedging at the wrong vol make/lose? | Discrete delta-hedge simulation | `delta_hedge_pnl` |

## Core reference code

```python
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq

def bs_price(S, K, T, r, sigma, q=0.0, option="call"):
    vs = sigma*np.sqrt(T)
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T)/vs; d2 = d1 - vs
    if option == "call":
        return S*np.exp(-q*T)*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
    return K*np.exp(-r*T)*norm.cdf(-d2) - S*np.exp(-q*T)*norm.cdf(-d1)

def bs_greeks(S, K, T, r, sigma, q=0.0, option="call"):
    vs = sigma*np.sqrt(T); d1 = (np.log(S/K)+(r-q+0.5*sigma**2)*T)/vs; d2 = d1-vs
    dq, dr, pdf = np.exp(-q*T), np.exp(-r*T), norm.pdf(d1)
    gamma = dq*pdf/(S*vs); vega = S*dq*pdf*np.sqrt(T)          # vega per 1.00 vol
    th0 = -S*dq*pdf*sigma/(2*np.sqrt(T))                           # theta per year
    if option == "call":
        return dict(delta=dq*norm.cdf(d1), gamma=gamma, vega=vega,
                    theta=th0 - r*K*dr*norm.cdf(d2) + q*S*dq*norm.cdf(d1), rho=K*T*dr*norm.cdf(d2))
    return dict(delta=-dq*norm.cdf(-d1), gamma=gamma, vega=vega,
                theta=th0 + r*K*dr*norm.cdf(-d2) - q*S*dq*norm.cdf(-d1), rho=-K*T*dr*norm.cdf(-d2))

def implied_vol(price, S, K, T, r, q=0.0, option="call"):
    lo = max(S*np.exp(-q*T) - K*np.exp(-r*T), 0) if option == "call" else max(K*np.exp(-r*T) - S*np.exp(-q*T), 0)
    hi = S*np.exp(-q*T) if option == "call" else K*np.exp(-r*T)
    if not lo <= price <= hi: return np.nan        # stale/wide quote: drop it, don't force it
    return brentq(lambda s: bs_price(S, K, T, r, s, q, option) - price, 1e-6, 5.0, xtol=1e-10)
```

**CRR tree** — `u=e^{σ√dt}, d=1/u, p=(e^{(r-q)dt}-d)/(u-d)`; backward induction `V=e^{-r dt}(pV_up+(1-p)V_down)`, American: `V=max(V, intrinsic)` at each node. Converges O(1/n) with odd/even oscillation — average n and n+1 if you need smoothness.

**Crank-Nicolson** — grid `S∈[0, 4·max(S,K)]`, θ=½ scheme on the BS PDE `V_t + ½σ²S²V_SS + (r-q)SV_S - rV = 0`; solve the tridiagonal system with `scipy.linalg.solve_banded`; boundaries: call `V(0)=0, V(Smax)=Smax e^{-qτ}-Ke^{-rτ}`, put `V(0)=Ke^{-rτ}, V(Smax)=0`. The explicit scheme (lecture 38) is only stable if `dt ≤ dS²/(σ²S_max²)` — prefer CN.

**Monte Carlo with variance reduction** (lectures 2, 19, 33, 73):
```python
def mc_european(S, K, T, r, sigma, q=0.0, option="call", n=100_000, rng=None):
    rng = rng or np.random.default_rng()
    Z = rng.standard_normal(n//2); Z = np.concatenate([Z, -Z])          # antithetic
    ST = S*np.exp((r-q-0.5*sigma**2)*T + sigma*np.sqrt(T)*Z)
    Y = np.exp(-r*T)*(np.maximum(ST-K, 0) if option == "call" else np.maximum(K-ST, 0))
    X = np.exp(-r*T)*ST                                                  # control, E[X] = S e^{-qT}
    Y = Y - np.cov(Y, X)[0, 1]/np.var(X, ddof=1)*(X - S*np.exp(-q*T))
    Y = 0.5*(Y[:n//2] + Y[n//2:])                                        # pair-average for honest SE
    return Y.mean(), Y.std(ddof=1)/np.sqrt(len(Y))
```
Always report the standard error. For arithmetic Asians use the closed-form **geometric** Asian as control variate (`geometric_asian_price`): `μ = ln S + (r-q-σ²/2)T(n+1)/(2n)`, `v = σ²T(n+1)(2n+1)/(6n²)`.
Barrier options: discrete monitoring misses crossings; use many steps or shift the barrier by `exp(±0.5826 σ√dt)` (Broadie-Glasserman-Kou). Sanity: in + out = vanilla on the same paths.

**Heston** (lectures 39, 80): `dS = (r-q)S dt + √v S dW₁`, `dv = κ(θ-v)dt + σ√v dW₂`, `corr = ρ`.
```python
def heston_cf(u, T, S0, r, q, kappa, theta, sigma, rho, v0):   # "little Heston trap" — stable
    b = kappa - rho*sigma*1j*u
    d = np.sqrt(b*b + sigma**2*(1j*u + u*u)); g = (b-d)/(b+d); e = np.exp(-d*T)
    C = 1j*u*(r-q)*T + kappa*theta/sigma**2*((b-d)*T - 2*np.log((1-g*e)/(1-g)))
    D = (b-d)/sigma**2*(1-e)/(1-g*e)
    return np.exp(C + D*v0 + 1j*u*np.log(S0))
```
Price = `S e^{-qT} P1 - K e^{-rT} P2`, `P2 = ½ + (1/π)∫Re[e^{-iu lnK} φ(u)/(iu)]du`, `P1 = ½ + (1/π)∫Re[e^{-iu lnK} φ(u-i)/(iu·F)]du` (F = forward). Carr-Madan FFT: damped call transform `ψ(v)=e^{-rT}φ(v-(α+1)i)/(α²+α-v²+i(2α+1)v)`, α≈1.5, N=4096, η=0.25, Simpson weights → whole strike grid in one FFT. MC: full truncation `v⁺=max(v,0)` in drift and diffusion, log-Euler for S. Check Feller `2κθ > σ²` and warn if violated (MC bias grows).
**Bates** = Heston + Merton jumps; compensate drift by `λk`, `k=e^{μ_J+σ_J²/2}-1`, so the discounted price stays a martingale.

**Variance swap** (lecture 91): `K_var = (2e^{rT}/T)∫ Q(K)/K² dK − (F/K₀−1)²/T`, Q = OTM put below F, OTM call above; K₀ = largest strike ≤ F. Vol swap strike < √K_var (convexity: ≈ Var[σ²]/(8K_var^{3/2})). Long var swap P&L = notional × (σ²_realized − K_var).

**Delta hedging** (lectures 9, 11, 23): short option at implied σ_i, hedge with BS delta at σ_i, realized σ_r ⇒ P&L ≈ ½∫Γ S²(σ_i² − σ_r²)dt. Hedging error from discrete rebalancing ∝ 1/√(rebalances). Drift μ does not matter for a hedged book (the "physics proof" of BS, lecture 67; risk-neutral pricing, lecture 83).

## Trading-side knowledge to apply
- Implied vol is the market's price of future realized vol; the surface (lectures 30, 84) has skew because of crash risk. Build it by inverting mid prices per (K, T), filter out quotes violating bounds or with tiny vega.
- Vol crush (lecture 43): IV drops after earnings; a long straddle needs realized move > implied move `≈ S·σ_IV·√(T)·√(2/π)`.
- Covered call / cash-secured put (lectures 106, 113): short-vol payoffs; their edge is the variance risk premium, their risk is the left tail — pair with the tail-risk tools in `qg-portfolio-risk`.
- Greeks as Taylor terms (lecture 11): ΔP ≈ Δ·dS + ½Γ·dS² + Θ·dt + Vega·dσ. Use this for scenario P&L of an option book.

## Validation (write these as tests)
- `bs_price(100,100,1,0.05,0.2) == 10.450583572185565`; put-call parity `C − P = Se^{-qT} − Ke^{-rT}`.
- Greeks equal central finite differences of `bs_price` (rel 1e-5).
- IV round trip for vols 0.05–1.2 within 1e-7.
- CRR(n=2000) → BS within 5e-3; American put (100,100,1,5%,20%) ≈ 6.0896; American call w/o dividends = European.
- CN within 2e-2 of BS.
- MC within 4 standard errors of BS; control/antithetic SE < 0.6 × plain SE.
- Heston benchmark (Fang-Oosterlee): κ=1.5768, θ=0.0398, σ=0.5751, ρ=−0.5711, v0=0.0175, S=K=100, T=1, r=0 → **5.785155450** (integral within 1e-6, FFT within 1e-5). Heston with σ→0, v0=θ → BS with vol √θ. Negative ρ ⇒ downward-sloping IV skew.
- Bates/Merton: `e^{-rT}E[S_T] = S0 e^{-qT}` within 4 SE.
- Variance swap under flat BS vol σ ⇒ √K_var ≈ σ (±2e-3 with a dense strike strip).
- Delta hedge at σ_i = σ_r ⇒ mean P&L ≈ 0; short at σ_i > σ_r ⇒ mean P&L ≈ BS(σ_i) − BS(σ_r).

## Pitfalls
- Mixing day-count units (T in days with annual σ). Convert once at the boundary.
- `np.random.seed` globals → use a passed `Generator` for reproducible, parallel-safe runs.
- Using `np.var(whole_sample)` or future data to seed anything used in a backtest.
- Pricing with historical μ: risk-neutral drift is r − q, always.
- Heston "original" CF formulation has branch-cut discontinuities for long T — use the little-trap form above.

## Lecture map (Quant Guild Library folder numbers)
BS & Greeks 6, 9, 11, 107, 139 · IV & surface 23, 30, 84, 89 · MC 19, 33, 73 + control variates 2 · exotics 32 · PDE/FD 37, 38 · Heston/FFT 39, 80 · risk-neutral/Bates 67, 83 · variance swaps 91 · vol crush / earnings 43, 55 · options strategies 105, 106, 108, 113 · CRR project 130 · market-making simulator 69, 132.
