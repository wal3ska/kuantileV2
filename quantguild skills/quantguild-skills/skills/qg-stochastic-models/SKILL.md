---
name: qg-stochastic-models
description: Simulate and fit stochastic processes and market regimes in code — GBM/OU/bridges, fBM and rough vol (Volterra, Markovian lifting), Poisson/Hawkes jumps, GARCH, Kalman filters, Markov chains and HMM regimes (Quant Guild methods).
---

# Stochastic processes, volatility & regimes (Quant Guild methods)

Methods distilled from the Quant Guild Library (Roman Paolucci — github.com/romanmichaelpaolucci/Quant-Guild-Library, youtube.com/@QuantGuild), implemented and tested in `qglib.processes` and `qglib.timeseries`. Use when the user needs to simulate price/vol/event paths, estimate model parameters from data, filter a hidden state, or detect regimes inside a code project. Turkish triggers: stokastik süreç, Brownian hareket, OU / ortalamaya dönüş, GARCH volatilite, Kalman filtresi, Markov zinciri, gizli Markov (HMM), rejim, Hawkes, kaba (rough) volatilite.

## Step 0 — Integrate with the project first
1. Search the project for `qglib`. If present: `from qglib import processes as SP, timeseries as TS` and call it.
2. If absent, offer to vendor `qglib/` (+ its tests) or implement inline from the snippets below with identical names/signatures.
3. Path arrays are **(n_paths, n_steps+1)** including t=0; every random function takes `rng` (`np.random.default_rng(seed)`).
4. Anything consumed by a live strategy or backtest must be **causal**: state at t uses data ≤ t only (filter, not smoother; no full-sample initialization).

## Method selection

| Question | Model | qglib |
|---|---|---|
| Price paths, positive, lognormal | GBM exact log scheme | `gbm_paths`, `gbm_moments` |
| Spread / rate / P&L can go negative | ABM | `abm_paths` |
| Mean-reverting spread, pairs, vol | OU with **exact** transition; fit via AR(1) | `ou_paths`, `ar1_fit` → `ou_from_ar1` |
| Multi-asset with correlation | Cholesky of covariance | `correlated_gbm_paths` |
| Path forced to a known endpoint / CAGR | Brownian bridge (log bridge) | `brownian_bridge`, `log_bridge_to_cagr` |
| Sample any distribution | Inverse transform `F⁻¹(U)` | `inverse_transform(_discrete)` |
| Long memory / roughness (H≠½) | fBM via Davies-Harte (exact, FFT) | `fbm_davies_harte` |
| Rough volatility kernel `t^{H-½}` | Volterra convolution (O(n²)) or Markovian lift (sum of OU factors, O(n·m)) | `volterra_paths`, `markovian_lift`, `lifted_volterra_paths` |
| Discrete events (defaults, jumps, orders) | Poisson; time-varying rate by thinning | `poisson_times`, `inhomogeneous_poisson_times` |
| Jumps in prices | Merton jump-diffusion (compensated) | `merton_jump_paths` |
| Clustered events (trades, vol bursts) | Hawkes, Ogata thinning + exact MLE | `hawkes_simulate`, `hawkes_fit` |
| Volatility forecast | EWMA (λ=0.94) / GARCH(1,1) MLE (+Student-t) | `ewma_variance`, `garch11_fit`, `garch11_forecast` |
| Hidden fair value / noisy signal | Kalman: local level, OU state, dynamic regression (hedge ratio) | `kalman_local_level`, `KalmanOU`, `kalman_regression`, `KalmanFilter` |
| Discrete market states | Markov chain: transition MLE, stationary dist., durations | `estimate_transition_matrix`, `stationary_distribution`, `expected_durations` |
| Unobserved regimes (calm/normal/stress) | Gaussian HMM: filter (causal), smooth (analysis), Viterbi, Baum-Welch | `GaussianHMM` |
| Is the series stationary? | ADF (statsmodels) | `adf_test` |

## Core reference code

```python
import numpy as np

def gbm_paths(s0, mu, sigma, T, n_steps, n_paths, rng=None):
    rng = rng or np.random.default_rng(); dt = T/n_steps
    lr = (mu - 0.5*sigma**2)*dt + sigma*np.sqrt(dt)*rng.standard_normal((n_paths, n_steps))
    return s0*np.exp(np.hstack([np.zeros((n_paths, 1)), np.cumsum(lr, axis=1)]))

def ou_paths(x0, kappa, theta, sigma, T, n_steps, n_paths, rng=None):   # exact, any dt
    rng = rng or np.random.default_rng(); dt = T/n_steps
    e = np.exp(-kappa*dt); sd = sigma*np.sqrt((1 - e**2)/(2*kappa))
    X = np.empty((n_paths, n_steps + 1)); X[:, 0] = x0
    for t in range(n_steps):
        X[:, t+1] = theta + (X[:, t] - theta)*e + sd*rng.standard_normal(n_paths)
    return X

def ou_from_ar1(phi, c, sigma_eps, dt):     # x_t = c + phi x_{t-1} + eps  (OLS)
    kappa = -np.log(phi)/dt
    return dict(kappa=kappa, theta=c/(1 - phi), sigma=sigma_eps*np.sqrt(2*kappa/(1 - phi**2)),
                half_life=np.log(2)/kappa)
```
GBM facts (lectures 117, 135, 136): mean `s0e^{μt}`, median `s0e^{(μ-σ²/2)t}`, typical path grows at `μ − σ²/2` (volatility drag), `P(S_t<s0)=Φ(−(μ−σ²/2)√t/σ)`.

**Brownian bridge:** `X_t = a + W_t − (t/T)(W_T − (b−a))`, `Var = σ²t(T−t)/T`. Exponentiate a bridge in log-price to create paths with an identical CAGR but different drawdowns (lecture 125).

**fBM (Davies-Harte, lecture 25):** autocovariance of fGn `γ(k)=½(|k+1|^{2H}−2|k|^{2H}+|k−1|^{2H})`; circulant vector `c=[γ(0..n), γ(n−1..1)]`; eigenvalues `λ=Re FFT(c)` (must be ≥0); `fGn = Re FFT(√(λ/2n)·(Z₁+iZ₂))[:n]·(T/n)^H`; fBM = cumsum. Checks: `Var B_H(t)=t^{2H}`, lag-1 increment corr `2^{2H−1}−1`.

**Rough vol / Volterra (lectures 85, 102):** `X_t=∫₀ᵗK(t−s)dW_s`, RL kernel `K(t)=√(2H) t^{H−½}` (Var = t^{2H}); rough-Heston convention `t^{H−½}/Γ(H+½)`. Discretize with **variance-matched weights** `w_k=√(∫_{k dt}^{(k+1)dt}K²ds / dt)` — naive midpoint weights understate variance ~15% at H=0.1. **Markovian lifting**: fit `K(t)≈Σc_i e^{−x_i t}` (x_i geometric grid, c_i≥0 by NNLS on log-spaced t), then simulate m OU factors `Y_i ← e^{−x_i dt}Y_i + g_i dW`, `g_i=√((1−e^{−2x_i dt})/(2x_i dt))`, `X=Σc_iY_i`. Turns an O(n²) non-Markov problem into O(n·m) Markov state (needed for PDE/filters/live updates).

**Hawkes (lecture 94):** `λ(t)=μ+Σα e^{−β(t−t_i)}`; stationary iff `α/β<1`; mean rate `μ/(1−α/β)`. Log-likelihood via recursion `A_i=e^{−β(t_i−t_{i−1})}(1+A_{i−1})`, `ℓ=Σlog(μ+αA_i) − μT − (α/β)Σ(1−e^{−β(T−t_i)})`.

**GARCH(1,1) (lecture 47):** `h_t=ω+αε²_{t−1}+βh_{t−1}`, fit by MLE on returns **in percent**; constrain α,β≥0, α+β<1; long-run var `ω/(1−α−β)`; k-step forecast `V_L+(α+β)^{k−1}(h_{t+1}−V_L)`. EWMA = IGARCH with ω=0. Seed recursions with a burn-in window or long-run variance, never full-sample variance (look-ahead). Use Student-t innovations when kurtosis is high.

**Kalman (lectures 44, 92, 95):**
```python
def kalman_local_level(z, q, r, p0=1e6):          # random walk + noise; q/r = signal/noise
    x, P, out = z[0], p0, np.empty(len(z))
    for t, zt in enumerate(z):
        P += q; K = P/(P + r); x += K*(zt - x); P *= (1 - K); out[t] = x
    return out
```
OU-state variant (`KalmanOU`): predict `x←φx+(1−φ)μ`, `P←φ²P+Q` with `Q=σ²(1−φ²)`, update with gain `K=P/(P+R)`; signal `z=(price−x)/√(P+R)` for mean-reversion entries; φ, μ, σ from `ar1_fit` on a calibration window. Dynamic hedge ratio for pairs: state = β_t (random walk, `Q=δ/(1−δ)·I`), observation `y_t = x_tβ_t + e`.

**Markov chains / HMM (lectures 49, 51, 71, 72, 74):** transition MLE = row-normalized transition counts; stationary π solves `πP=π`; expected stay `1/(1−P_ii)`. HMM forward recursion in log space `logα_t = logsumexp(logα_{t−1}+logA) + logB_t`; filtered probs are causal (use for trading), smoothed probs use the future (analysis only). Live regime update (lecture 74 bot): `post ∝ (prior @ A) * N(x_t; μ_k, σ_k)`. Typical input: rolling realized vol or returns; 2–3 states; sort states by mean after fitting to keep labels stable.

## Validation (write these as tests)
- GBM: MC mean/median/P(below start) match `gbm_moments` (≤2%).
- OU: stationary variance `σ²/2κ`; AR(1)→OU recovers θ, σ (κ is noisier — ±25%).
- Correlated GBM: sample log-return correlation ≈ target.
- Bridge endpoints exact; mid variance `t(T−t)/T`.
- fBM for H∈{0.1,0.5,0.8}: `Var=t^{2H}`, lag-1 corr `2^{2H−1}−1`.
- Volterra RL: `Var X_T≈T^{2H}`; lift fit rel. error <5% on [dt, T]; lifted vs exact paths corr >0.995 with shared dW.
- Poisson mean count λT; thinning count `∫λ(t)dt`; Merton `E[S_T]=s0e^{μT}`.
- Hawkes empirical rate ≈ `μ/(1−α/β)`; MLE recovers branching ratio ±0.1.
- GARCH MLE on simulated data recovers α, β (±0.03/0.04); forecasts converge to V_L.
- EWMA/GARCH causality: changing r[t] leaves outputs ≤ t unchanged.
- Kalman regression tracks a β break; HMM Viterbi accuracy >90% on well-separated simulated regimes; filtered/smoothed rows sum to 1.

## Pitfalls
- Euler on OU/GBM when an exact scheme exists → discretization bias for large dt.
- Fitting OU on non-stationary prices (lecture 93): test stationarity (ADF) of the spread/returns first; "timing" rules on levels are fragile.
- Model risk (lecture 58): parameters drift; re-calibrate on rolling windows and monitor out-of-sample likelihood.
- HMM label switching; local optima → multiple initializations, keep the best log-likelihood.
- Hawkes with α/β≥1 explodes; clip or reparametrize.
- Itô vs ordinary calculus (lectures 29, 31): `d(ln S) = (μ−σ²/2)dt + σdW`, the −σ²/2 is the source of vol drag — never drop it.

## Lecture map
Inverse transform 1 · Itô/SDEs 29, 31, 37 · BM/ABM/GBM 59, 135 · OU 7, 36, 51, 58, 81 · Brownian bridge/KL 27, 103, 125 · CLT/LLN/Markov property 61, 71, 114 · fBM 25 · Volterra & rough vol 85, 102 · Poisson 82 · Hawkes 94 · GARCH 47, 126 · Kalman 44, 92, 95 · Markov chains 49 · HMM 51 · regime bot 72, 74 · non-stationarity 93 · model breaks 58.
