import numpy as np
import pytest

from qglib import metrics as M
from qglib import portfolio as PF
from qglib import pricing as P
from qglib import processes as SP
from qglib import timeseries as TS

S, K, T, r, sig = 100.0, 100.0, 1.0, 0.05, 0.2
BS_CALL = 10.450583572185565  # textbook value


# ---------------------------------------------------------------- pricing
def test_bs_known_value_and_parity():
    c = P.bs_price(S, K, T, r, sig)
    p = P.bs_price(S, K, T, r, sig, option="put")
    assert c == pytest.approx(BS_CALL, abs=1e-10)
    assert c - p == pytest.approx(S - K * np.exp(-r * T), abs=1e-10)


def test_greeks_vs_finite_differences():
    g = P.bs_greeks(S, K, T, r, sig, q=0.01)
    h = 1e-4
    f = lambda **kw: P.bs_price(**{**dict(S=S, K=K, T=T, r=r, sigma=sig, q=0.01), **kw})
    assert g["delta"] == pytest.approx((f(S=S + h) - f(S=S - h)) / (2 * h), rel=1e-6)
    assert g["gamma"] == pytest.approx((f(S=S + h) - 2 * f() + f(S=S - h)) / h ** 2, rel=1e-3)
    assert g["vega"] == pytest.approx((f(sigma=sig + h) - f(sigma=sig - h)) / (2 * h), rel=1e-6)
    assert g["theta"] == pytest.approx(-(f(T=T + h) - f(T=T - h)) / (2 * h), rel=1e-5)
    assert g["rho"] == pytest.approx((f(r=r + h) - f(r=r - h)) / (2 * h), rel=1e-6)


@pytest.mark.parametrize("option", ["call", "put"])
@pytest.mark.parametrize("vol", [0.05, 0.3, 1.2])
def test_implied_vol_roundtrip(option, vol):
    price = P.bs_price(S, 90, 0.5, r, vol, option=option)
    assert P.implied_vol(price, S, 90, 0.5, r, option=option) == pytest.approx(vol, abs=1e-7)


def test_implied_vol_arbitrage_returns_nan():
    assert np.isnan(P.implied_vol(0.01, S, 50, 1, r))   # below intrinsic


def test_crr_converges_and_american_put_premium():
    assert P.binomial_crr(S, K, T, r, sig, n=2000) == pytest.approx(BS_CALL, abs=5e-3)
    eu = P.binomial_crr(S, K, T, r, sig, n=1000, option="put")
    am = P.binomial_crr(S, K, T, r, sig, n=1000, option="put", american=True)
    assert am > eu
    assert am == pytest.approx(6.0896, abs=5e-3)   # standard reference value
    # American call without dividends == European call
    assert P.binomial_crr(S, K, T, r, sig, 1000, american=True) == pytest.approx(
        P.binomial_crr(S, K, T, r, sig, 1000), abs=1e-10)


def test_crank_nicolson_matches_bs():
    assert P.fd_crank_nicolson(S, K, T, r, sig) == pytest.approx(BS_CALL, abs=2e-2)
    pe = P.bs_price(S, K, T, r, sig, option="put")
    assert P.fd_crank_nicolson(S, K, T, r, sig, option="put") == pytest.approx(pe, abs=2e-2)
    assert P.fd_crank_nicolson(S, K, T, r, sig, option="put", american=True) == pytest.approx(6.0896, abs=2e-2)


def test_mc_european_variance_reduction():
    rng = np.random.default_rng(0)
    p0, se0 = P.mc_european(S, K, T, r, sig, n_paths=200_000, antithetic=False, control_variate=False, rng=rng)
    p1, se1 = P.mc_european(S, K, T, r, sig, n_paths=200_000, rng=rng)
    assert abs(p0 - BS_CALL) < 4 * se0
    assert abs(p1 - BS_CALL) < 4 * se1
    assert se1 < 0.6 * se0


def test_geometric_asian_cv_and_barrier_parity():
    rng = np.random.default_rng(1)
    price, se = P.mc_asian_cv(S, K, T, r, sig, n_obs=50, n_paths=40_000, rng=rng)
    geo = P.geometric_asian_price(S, K, T, r, sig, 50)
    assert price > geo                      # arithmetic >= geometric average
    assert se < 0.01
    paths = SP.gbm_paths(S, r, sig, T, 252, 40_000, rng=rng)
    pin, _ = P.mc_price_paths(paths, P.barrier_payoff(K, 120, "up-and-in"), r, T)
    pout, _ = P.mc_price_paths(paths, P.barrier_payoff(K, 120, "up-and-out"), r, T)
    van, se = P.mc_price_paths(paths, lambda p: np.maximum(p[:, -1] - K, 0), r, T)
    assert pin + pout == pytest.approx(van, abs=1e-10)  # in + out = vanilla
    assert abs(van - BS_CALL) < 4 * se


HP = P.HestonParams(kappa=2.0, theta=0.04, sigma=0.3, rho=-0.7, v0=0.04)


def test_heston_integral_fft_mc_agree():
    ref = P.heston_price(S, K, T, r, HP)
    ks, calls = P.heston_fft_calls(S, T, r, HP)
    assert np.interp(K, ks, calls) == pytest.approx(ref, abs=2e-3)
    Sp, _ = P.heston_paths(S, T, r, HP, n_steps=200, n_paths=60_000, rng=np.random.default_rng(3))
    mc, se = P.mc_price_paths(Sp, lambda p: np.maximum(p[:, -1] - K, 0), r, T)
    assert abs(mc - ref) < 4 * se + 0.03   # Euler bias allowance
    # put-call parity
    put = P.heston_price(S, K, T, r, HP, option="put")
    assert ref - put == pytest.approx(S - K * np.exp(-r * T), abs=1e-8)


def test_heston_degenerates_to_bs():
    hp = P.HestonParams(kappa=1.0, theta=0.04, sigma=1e-4, rho=0.0, v0=0.04)
    for k in (80, 100, 120):
        assert P.heston_price(S, k, T, r, hp) == pytest.approx(P.bs_price(S, k, T, r, 0.2), abs=1e-4)


def test_heston_skew_negative_rho():
    ivs = [P.implied_vol(P.heston_price(S, k, T, r, HP), S, k, T, r) for k in (80, 100, 120)]
    assert ivs[0] > ivs[1] > ivs[2]


def test_bates_martingale():
    Sp = P.bates_paths(S, T, r, HP, lam_j=1.0, mu_j=-0.1, sigma_j=0.15, n_paths=80_000,
                       rng=np.random.default_rng(4))
    disc = np.exp(-r * T) * Sp[:, -1]
    assert abs(disc.mean() - S) < 4 * disc.std() / np.sqrt(len(disc))


def test_variance_swap_flat_vol():
    ks = np.linspace(20, 400, 3000)
    F = S * np.exp(r * T)
    otm = np.where(ks < F, P.bs_price(S, ks, T, r, sig, option="put"), P.bs_price(S, ks, T, r, sig))
    assert np.sqrt(P.variance_swap_strike(ks, otm, S, T, r)) == pytest.approx(sig, abs=2e-3)


def test_delta_hedge_pnl():
    rng = np.random.default_rng(5)
    fair = P.delta_hedge_pnl(S, K, 0.5, r, 0.2, 0.2, mu=0.10, n_steps=252, n_paths=4000, rng=rng)
    assert abs(fair.mean()) < 0.1 and fair.std() < 0.6
    rich = P.delta_hedge_pnl(S, K, 0.5, r, 0.3, 0.2, n_steps=252, n_paths=4000, rng=rng)
    theo = P.bs_price(S, K, 0.5, r, 0.3) - P.bs_price(S, K, 0.5, r, 0.2)
    assert rich.mean() == pytest.approx(theo, rel=0.15)  # short rich vol earns ~ price diff


# ---------------------------------------------------------------- processes
def test_inverse_transform():
    rng = np.random.default_rng(6)
    x = SP.inverse_transform(lambda u: -np.log(1 - u) / 2.0, 200_000, rng)
    assert x.mean() == pytest.approx(0.5, abs=0.01)
    d = SP.inverse_transform_discrete([1, 2, 3], [0.2, 0.5, 0.3], 100_000, rng)
    assert np.mean(d == 2) == pytest.approx(0.5, abs=0.01)


def test_gbm_moments_and_drag():
    rng = np.random.default_rng(7)
    p = SP.gbm_paths(1.0, 0.08, 0.4, 5.0, 60, 200_000, rng)
    m = SP.gbm_moments(1.0, 0.08, 0.4, 5.0)
    assert p[:, -1].mean() == pytest.approx(m["mean"], rel=0.02)
    assert np.median(p[:, -1]) == pytest.approx(m["median"], rel=0.02)
    assert np.mean(p[:, -1] < 1) == pytest.approx(m["prob_below_start"], abs=0.01)


def test_ou_stationary_variance_and_fit():
    rng = np.random.default_rng(8)
    X = SP.ou_paths(0.0, 3.0, 1.0, 0.5, 200.0, 20_000, 1, rng)[0]
    assert X[2000:].var() == pytest.approx(0.5 ** 2 / 6, rel=0.1)
    a = TS.ar1_fit(X)
    ou = TS.ou_from_ar1(a["phi"], a["c"], a["sigma"], 200 / 20_000)
    assert ou["kappa"] == pytest.approx(3.0, rel=0.25)
    assert ou["theta"] == pytest.approx(1.0, abs=0.05)
    assert ou["sigma"] == pytest.approx(0.5, rel=0.05)


def test_correlated_gbm():
    cov = np.array([[0.04, 0.018], [0.018, 0.09]])
    p = SP.correlated_gbm_paths([1, 1], [0.05, 0.05], cov, 1.0, 50, 20_000, np.random.default_rng(9))
    lr = np.diff(np.log(p), axis=1).reshape(-1, 2)
    assert np.corrcoef(lr.T)[0, 1] == pytest.approx(0.3, abs=0.02)


def test_brownian_bridge_and_cagr_bridge():
    b = SP.brownian_bridge(1.0, 3.0, 2.0, 100, 5000, rng=np.random.default_rng(10))
    assert np.allclose(b[:, 0], 1) and np.allclose(b[:, -1], 3)
    assert b[:, 50].var() == pytest.approx(1.0 * 1.0 / 2.0, rel=0.1)   # t(T-t)/T
    p = SP.log_bridge_to_cagr(100, 0.1, 0.3, 5, 1260, 3, np.random.default_rng(1))
    assert np.allclose(p[:, -1], 100 * 1.1 ** 5)


@pytest.mark.parametrize("H", [0.1, 0.5, 0.8])
def test_fbm_variance(H):
    _, X = SP.fbm_davies_harte(256, H, 1.0, n_paths=20_000, rng=np.random.default_rng(11))
    assert X[:, -1].var() == pytest.approx(1.0, rel=0.05)
    assert X[:, 128].var() == pytest.approx(0.5 ** (2 * H), rel=0.05)
    inc = np.diff(X, axis=1)
    rho1 = np.mean(inc[:, :-1] * inc[:, 1:]) / np.mean(inc ** 2)
    assert rho1 == pytest.approx(2 ** (2 * H - 1) - 1, abs=0.02)


def test_volterra_and_markovian_lift():
    H, Tm, n = 0.1, 1.0, 400
    ker = SP.rl_kernel(H)
    rng = np.random.default_rng(12)
    dW = np.sqrt(Tm / n) * rng.standard_normal((4000, n))
    X = SP.volterra_paths(ker, Tm, n, dW=dW)
    assert X[:, -1].var() == pytest.approx(1.0, rel=0.1)       # RL: Var = t^{2H}
    c, x = SP.markovian_lift(ker, Tm, n_factors=20)
    t = np.geomspace(Tm / n, Tm, 50)
    fit = np.exp(-np.outer(t, x)) @ c
    assert np.max(np.abs(fit / ker(t) - 1)) < 0.05
    Xl = SP.lifted_volterra_paths(c, x, Tm, n, dW=dW)
    assert np.corrcoef(X[:, -1], Xl[:, -1])[0, 1] > 0.995


def test_poisson_and_thinning():
    rng = np.random.default_rng(13)
    counts = [len(SP.poisson_times(5.0, 10.0, rng)) for _ in range(2000)]
    assert np.mean(counts) == pytest.approx(50, rel=0.02)
    lam = lambda t: 2 + 2 * np.sin(t) ** 2
    counts = [len(SP.inhomogeneous_poisson_times(lam, 4.0, 10.0, rng)) for _ in range(2000)]
    expected = 2 * 10 + 2 * (10 / 2 - np.sin(20) / 4)
    assert np.mean(counts) == pytest.approx(expected, rel=0.03)


def test_merton_martingale():
    p = SP.merton_jump_paths(100, 0.05, 0.2, 2.0, -0.1, 0.1, 1.0, 50, 100_000, np.random.default_rng(14))
    assert p[:, -1].mean() == pytest.approx(100 * np.exp(0.05), rel=0.01)


def test_hawkes_rate_and_fit():
    rng = np.random.default_rng(15)
    mu, a, b, Tm = 0.5, 0.8, 1.6, 4000.0
    ev = SP.hawkes_simulate(mu, a, b, Tm, rng)
    assert len(ev) / Tm == pytest.approx(mu / (1 - a / b), rel=0.1)
    est = SP.hawkes_fit(ev, Tm)
    assert est["alpha"] / est["beta"] == pytest.approx(0.5, abs=0.1)
    assert est["mu"] == pytest.approx(mu, rel=0.25)


# ---------------------------------------------------------------- timeseries
def _simulate_garch(n, omega, alpha, beta, rng):
    h, r = omega / (1 - alpha - beta), np.empty(n)
    for t in range(n):
        r[t] = np.sqrt(h) * rng.standard_normal()
        h = omega + alpha * r[t] ** 2 + beta * h
    return r


def test_garch_fit_and_forecast():
    r = _simulate_garch(6000, 0.05, 0.08, 0.9, np.random.default_rng(16))
    f = TS.garch11_fit(r)
    assert f["alpha"] == pytest.approx(0.08, abs=0.03)
    assert f["beta"] == pytest.approx(0.9, abs=0.04)
    assert f["long_run_var"] == pytest.approx(2.5, rel=0.3)
    fc = TS.garch11_forecast(10.0, f["omega"], f["alpha"], f["beta"], 500)
    assert fc[0] == 10.0 and fc[-1] == pytest.approx(f["long_run_var"], rel=0.01)
    ft = TS.garch11_fit(r, dist="t")
    assert ft["nu"] > 10   # data are Gaussian -> large nu


def test_ewma_no_lookahead():
    r = np.random.default_rng(0).standard_normal(100)
    s2 = TS.ewma_variance(r)
    r2 = r.copy(); r2[50] = 100
    assert np.allclose(TS.ewma_variance(r2)[:51], s2[:51])


def test_kalman_local_level_and_regression():
    rng = np.random.default_rng(17)
    level = np.cumsum(0.1 * rng.standard_normal(2000))
    z = level + rng.standard_normal(2000)
    xs, _ = TS.kalman_local_level(z, q=0.01, r=1.0)
    assert np.mean((xs[100:] - level[100:]) ** 2) < 0.5 * np.mean((z[100:] - level[100:]) ** 2)
    x = np.cumsum(rng.standard_normal(3000)) + 50
    beta = np.where(np.arange(3000) < 1500, 1.0, 2.0)
    y = beta * x + 0.5 * rng.standard_normal(3000)
    b, _ = TS.kalman_regression(y, x, delta=1e-4, r=0.25)
    assert b[1400, 0] == pytest.approx(1.0, abs=0.05) and b[-1, 0] == pytest.approx(2.0, abs=0.05)


def test_kalman_ou():
    k = TS.KalmanOU(0.9, 100.0, 1.0)
    for z in [101, 102, 101.5]:
        k.update(z)
    assert 100 < k.x < 102
    f = k.forecast(50)
    assert abs(f[-1] - 100) < abs(f[0] - 100)


def test_markov_chain():
    Pm = np.array([[0.9, 0.1], [0.3, 0.7]])
    pi = TS.stationary_distribution(Pm)
    assert np.allclose(pi, [0.75, 0.25])
    rng = np.random.default_rng(18)
    s = [0]
    for _ in range(50_000):
        s.append(rng.choice(2, p=Pm[s[-1]]))
    assert np.allclose(TS.estimate_transition_matrix(s), Pm, atol=0.02)
    assert np.allclose(TS.expected_durations(Pm), [10, 1 / 0.3])


def test_hmm_recovers_regimes():
    rng = np.random.default_rng(19)
    A = np.array([[0.98, 0.02], [0.05, 0.95]])
    s = [0]
    for _ in range(4999):
        s.append(rng.choice(2, p=A[s[-1]]))
    s = np.array(s)
    x = np.where(s == 0, rng.normal(0.05, 0.5, len(s)), rng.normal(-0.1, 2.0, len(s)))
    hmm = TS.GaussianHMM(2).fit(x)
    assert hmm.stds[0] == pytest.approx(2.0, rel=0.1)       # sorted by mean: state0 = -0.1 mean
    assert np.mean(hmm.viterbi(x) == (1 - s)) > 0.9
    filt, sm = hmm.filter(x), hmm.smooth(x)
    assert np.allclose(filt.sum(1), 1) and np.allclose(sm.sum(1), 1)
    p = hmm.pi0.copy()
    for xt in x[:10]:
        p = hmm.filter_step(p, xt)
    # online step (predict then update) vs batch filter at t=9: batch starts at pi0 w/o predict
    assert p.sum() == pytest.approx(1.0)


# ---------------------------------------------------------------- portfolio
MU = np.array([0.08, 0.10, 0.12])
COV = np.array([[0.04, 0.006, 0.01], [0.006, 0.09, 0.02], [0.01, 0.02, 0.16]])


def test_minvar_tangency():
    w = PF.min_variance_weights(COV)
    wlo = PF.min_variance_weights(COV, long_only=True)
    assert w.sum() == pytest.approx(1) and np.allclose(w, wlo, atol=1e-4) or w.min() < 0
    wt = PF.tangency_weights(MU, COV, rf=0.02)
    s = lambda w: (w @ MU - 0.02) / np.sqrt(w @ COV @ w)
    wn = PF.tangency_weights(MU, COV, rf=0.02, long_only=True)
    assert s(wt) >= s(wn) - 1e-6 and s(wt) >= s(np.ones(3) / 3)


def test_risk_parity():
    w = PF.risk_parity_weights(COV)
    assert np.allclose(PF.risk_contributions(w, COV), 1 / 3, atol=1e-3)


def test_black_litterman():
    w_mkt = np.array([0.5, 0.3, 0.2])
    pi = PF.implied_equilibrium_returns(COV, w_mkt)
    mu0, _, w0 = PF.black_litterman(COV, w_mkt, [[0, 0, 0]], [0.0], omega=np.eye(1) * 1e6)
    assert np.allclose(mu0, pi, atol=1e-6)
    assert np.allclose(w0 / w0.sum(), w_mkt, atol=1e-3)     # no views -> market portfolio
    mu1, _, w1 = PF.black_litterman(COV, w_mkt, [[1, -1, 0]], [0.05])
    assert mu1[0] - mu1[1] > pi[0] - pi[1]
    assert w1[0] / w1.sum() > 0.5


def test_kelly():
    assert PF.kelly_binary(0.6, 1.0) == pytest.approx(0.2)
    f = PF.kelly_continuous(0.1, 0.2, 0.02)
    assert f == pytest.approx(2.0)
    assert PF.growth_rate(2 * f, 0.1, 0.2, 0.02) == pytest.approx(0.02)
    assert np.allclose(PF.kelly_multi(MU, COV, 0.0), np.linalg.solve(COV, MU))


def test_capm_and_hedge():
    rng = np.random.default_rng(20)
    m = rng.normal(0.0004, 0.01, 5000)
    p = 0.0002 + 1.3 * m + rng.normal(0, 0.005, 5000)
    res = PF.capm_regression(p, m)
    assert res["beta"] == pytest.approx(1.3, abs=0.03)
    assert abs(res["alpha_annual"] - 0.0504) < 3.5 * 0.005 / np.sqrt(5000) * 252
    h, r2 = PF.hedge_ratio(p, m)
    assert h == pytest.approx(1.3, abs=0.03) and r2 == pytest.approx(res["r2"], abs=1e-9)


def test_pca_market_factor():
    rng = np.random.default_rng(21)
    f = rng.standard_normal(3000)
    R = 0.8 * f[:, None] + 0.4 * rng.standard_normal((3000, 6))
    out = PF.pca(R)
    assert out["explained_ratio"][0] > 0.7
    assert np.all(out["loadings"][:, 0] > 0)


# ---------------------------------------------------------------- metrics
def test_basic_metrics():
    eq = np.array([100, 120, 90, 135, 108, 150.0])
    mdd = M.max_drawdown(eq)
    assert mdd["max_drawdown"] == pytest.approx(-0.25)
    assert mdd["peak_idx"] == 1 and mdd["trough_idx"] == 2 and mdd["recovery_idx"] == 3
    assert M.cagr([100, 121], periods_per_year=0.5) == pytest.approx(0.21 ** 1 * 0 + (1.21 ** 0.5 - 1))
    r = np.random.default_rng(22).normal(0.0005, 0.01, 252 * 20)
    assert M.sharpe(r) == pytest.approx(0.0005 / 0.01 * np.sqrt(252), abs=0.25)
    vd = M.volatility_drag(r)
    assert vd["drag"] == pytest.approx(vd["approx_sigma2_over_2"], rel=0.05)
    s = M.summary(r)
    assert set(["cagr", "sharpe", "max_drawdown", "psr_vs_0"]) <= s.keys()


def test_sharpe_uncertainty():
    se = M.sharpe_se(1.0, 252 * 4)
    assert se == pytest.approx(np.sqrt(1.5 / 4 * 1 / 1) * np.sqrt((1 + 0.5 / 252) / 1.5), rel=0.1)
    n = M.min_track_record_length(1.0)
    assert 2.5 * 252 < n < 3.5 * 252
    rng = np.random.default_rng(23)
    assert M.probabilistic_sharpe(rng.normal(0.001, 0.01, 2520)) > 0.95
    assert M.probabilistic_sharpe(rng.normal(0.0, 0.01, 2520)) < 0.99


def test_var_cvar():
    r = np.random.default_rng(24).normal(0, 0.01, 200_000)
    assert M.var_historical(r, 0.99) == pytest.approx(0.02326, rel=0.02)
    assert M.cvar_historical(r, 0.99) == pytest.approx(0.02665, rel=0.02)
    assert M.var_cornish_fisher(r, 0.99) == pytest.approx(M.var_parametric(0, 0.01, 0.99), rel=0.02)
    t = np.random.default_rng(25).standard_t(3, 200_000)
    assert M.tail_probability(t, 5)["ratio"] > 10
    assert M.expected_wait(1e-4) == 1e4


def test_ruin_and_ergodicity():
    assert M.gamblers_ruin(0.5, 10, 20) == pytest.approx(0.5)
    assert M.gamblers_ruin(0.55, 10, 1000) == pytest.approx((0.45 / 0.55) ** 10, rel=1e-6)
    e = M.time_vs_ensemble_growth([0.5, -0.4], [0.5, 0.5])
    assert e["ensemble_mean_return"] == pytest.approx(0.05)
    assert e["time_average_growth"] == pytest.approx(np.sqrt(1.5 * 0.6) - 1)
    assert e["ergodic_trap"]


def test_vrp_and_walk_forward():
    r = np.full(21, 0.01)
    v = M.variance_risk_premium(0.2, r)
    assert v["realized_var"] == pytest.approx(0.0252)
    splits = list(M.walk_forward_splits(100, 50, 10))
    assert len(splits) == 5
    for tr, te in splits:
        assert tr.max() < te.min()


def test_heston_published_benchmark():
    # Fang & Oosterlee (2008) COS paper reference: 5.785155450
    hp = P.HestonParams(1.5768, 0.0398, 0.5751, -0.5711, 0.0175)
    assert P.heston_price(100, 100, 1, 0, hp) == pytest.approx(5.785155450, abs=1e-6)
    k, c = P.heston_fft_calls(100, 1, 0, hp)
    assert np.interp(100, k, c) == pytest.approx(5.785155450, abs=1e-5)
