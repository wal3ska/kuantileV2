import numpy as np
import pandas as pd
import pytest

import advanced_risk as adv


def _rets(n=1000, mu=0.0005, sig=0.02, seed=1):
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(mu, sig, n), index=pd.bdate_range("2022-01-03", periods=n))


def test_expected_shortfall_deeper_than_var():
    r = _rets()
    es = adv.expected_shortfall(r, 0.99)
    var = float(np.quantile(r, 0.01))
    assert es is not None and es <= var < 0
    assert adv.expected_shortfall(r.head(30), 0.99) is None


def test_var_backtest_iid_normal_green():
    r = _rets(1200, seed=7)
    bt = adv.var_backtest(r, 0.99)
    assert bt is not None
    assert bt["days"] == 250
    assert bt["violations"] <= 9              # iid'de asiri ihlal beklenmez
    assert bt["basel_zone"] in ("green", "yellow")
    assert 0 <= bt["kupiec_p"] <= 1
    assert adv.var_backtest(r.head(300), 0.99) is None


def test_risk_attribution_sums_to_total():
    rng = np.random.default_rng(2)
    idx = pd.bdate_range("2023-01-02", periods=500)
    rets = pd.DataFrame({"A": rng.normal(0, 0.02, 500),
                         "B": rng.normal(0, 0.01, 500)}, index=idx)
    res = adv.risk_attribution(rets, {"A": 60_000, "B": 40_000}, 0.99, -0.03)
    assert res is not None
    total = sum(c["cvar_tl"] for c in res["components"])
    assert total == pytest.approx(res["total_var_tl"], rel=1e-9)
    # daha oynak + daha buyuk pozisyon daha cok risk tasimali
    assert res["components"][0]["name"] == "A"


def test_real_metrics():
    r = pd.Series(np.full(504, np.log(1.45) / 252),
                  index=pd.bdate_range("2024-01-01", periods=504))
    cpi = pd.Series([100 * 1.035 ** i for i in range(30)],
                    index=pd.date_range("2024-01-31", periods=30, freq="ME"))
    m = adv.real_metrics(r, cpi)
    assert m is not None
    assert m["inflation_12m"] == pytest.approx(1.035 ** 12 - 1, rel=1e-9)
    assert m["nominal_return_12m"] == pytest.approx(0.45, rel=1e-6)
    exp_real = 1.45 / (1.035 ** 12) - 1
    assert m["real_return_12m"] == pytest.approx(exp_real, rel=1e-6)


def test_fx_decomposition_pure_usd_asset():
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2023-01-02", periods=400)
    fx = pd.Series(rng.normal(0.001, 0.01, 400), index=idx)
    # TL getirisi tamamen kurdan gelen varlik (yerel getiri sifir)
    rets = pd.DataFrame({"USDvarlik": fx})
    res = adv.fx_decomposition(rets, fx, {"USDvarlik": 100_000}, {"USDvarlik"})
    assert res is not None
    assert res["usd_exposure_share"] == 1.0
    assert res["fx_share"] == pytest.approx(1.0, abs=1e-9)
    assert res["local_share"] == pytest.approx(0.0, abs=1e-9)


def test_liquidity_var_scaling():
    res = adv.liquidity_var([
        {"name": "Kucuk", "value_tl": 100_000, "adv_tl": 10_000, "kind": "equity"},
        {"name": "BTC", "value_tl": 100_000, "adv_tl": None, "kind": "liquid"},
    ], var_value_tl=-5_000)
    assert res is not None
    kucuk = next(r for r in res["positions"] if r["name"] == "Kucuk")
    assert kucuk["days_to_exit"] == 40.0      # 100k / (0.25*10k)
    assert res["lvar_multiplier"] == pytest.approx(0.5 * np.sqrt(40) + 0.5, rel=1e-9)
    assert res["lvar_value_tl"] < -5_000      # LVaR daha derin


def test_ewma_fhs():
    r = _rets(600, seed=4)
    res = adv.ewma_fhs(r, 0.99)
    assert res is not None
    assert res["var_ewma_pct"] < 0 and res["var_fhs_pct"] < 0
    assert res["ewma_vol_ann"] > 0


def test_drawdown_known_series():
    r = pd.Series([np.log(2), np.log(0.5)] + [0.0] * 200,
                  index=pd.bdate_range("2024-01-01", periods=202))
    d = adv.drawdown_stats(r)
    assert d is not None
    assert d["max_drawdown"] == pytest.approx(-0.5, rel=1e-9)
    assert d["underwater_days_now"] == 201
    assert d["ulcer_index"] > 0


def test_concentration_equal_iid():
    rng = np.random.default_rng(5)
    idx = pd.bdate_range("2023-01-02", periods=500)
    rets = pd.DataFrame({f"A{i}": rng.normal(0, 0.02, 500) for i in range(4)}, index=idx)
    inv = {f"A{i}": 25_000 for i in range(4)}
    c = adv.concentration(rets, inv)
    assert c is not None
    assert c["hhi"] == pytest.approx(0.25, rel=1e-9)
    assert c["effective_positions"] == pytest.approx(4.0, rel=1e-9)
    assert c["effective_bets"] > 2.5          # bagimsiz varliklarda 4'e yakin


def test_evt_tail_heavy_tailed():
    rng = np.random.default_rng(6)
    r = pd.Series(rng.standard_t(3, 3000) * 0.01,
                  index=pd.bdate_range("2015-01-01", periods=3000))
    e = adv.evt_tail(r)
    assert e is not None
    assert e["exceedances"] >= 30
    assert e["var995_pct"] < 0 and e["es995_pct"] < e["var995_pct"]
    assert adv.evt_tail(r.head(300)) is None


def test_tail_dependence():
    rng = np.random.default_rng(8)
    idx = pd.bdate_range("2023-01-02", periods=600)
    a = pd.Series(rng.normal(0, 0.02, 600), index=idx)
    rets = pd.DataFrame({"X": a, "Y": a, "Z": pd.Series(rng.normal(0, 0.02, 600), index=idx)})
    td = adv.tail_dependence(rets)
    assert td is not None
    top = td["pairs"][0]
    assert top["pair"] == "X – Y" and top["lambda_lower"] == pytest.approx(1.0, abs=1e-9)


def test_hrp_weights():
    rng = np.random.default_rng(9)
    idx = pd.bdate_range("2023-01-02", periods=500)
    rets = pd.DataFrame({"Sakin": rng.normal(0, 0.005, 500),
                         "Orta": rng.normal(0, 0.02, 500),
                         "Vahsi": rng.normal(0, 0.05, 500)}, index=idx)
    h = adv.hrp_weights(rets)
    assert h is not None
    w = h["weights"]
    assert sum(w.values()) == pytest.approx(1.0, rel=1e-9)
    assert w["Sakin"] > w["Vahsi"]            # dusuk volatiliteye yuksek pay
    assert h["excluded_cash_like"] == []


def test_hrp_excludes_cash_like():
    # para piyasasi benzeri varlik dagilim disinda kalmali; aksi halde
    # ters-varyans tum agirligi nakite yigar
    rng = np.random.default_rng(14)
    idx = pd.bdate_range("2023-01-02", periods=500)
    rets = pd.DataFrame({"ParaPiyasasi": rng.normal(0.0015, 0.0003, 500),
                         "HisseFonu": rng.normal(0.001, 0.02, 500),
                         "Altin": rng.normal(0.001, 0.015, 500)}, index=idx)
    h = adv.hrp_weights(rets)
    assert h is not None
    assert h["excluded_cash_like"] == ["ParaPiyasasi"]
    assert set(h["weights"]) == {"HisseFonu", "Altin"}
    assert sum(h["weights"].values()) == pytest.approx(1.0, rel=1e-9)


def test_srri_class_bands():
    # gunluk sigma 0.02 -> haftalik ~0.045 -> yillik ~%32 -> sinif 7
    r = _rets(1000, mu=0, sig=0.02, seed=12)
    c = adv.srri_class(r)
    assert c is not None and c["risk_class"] == 7
    # cok stabil seri -> sinif 1
    calm = pd.Series(np.full(1000, 1e-5), index=pd.bdate_range("2022-01-03", periods=1000))
    assert adv.srri_class(calm)["risk_class"] == 1
    # gunluk sigma 0.005 -> yillik ~%8 -> sinif 4
    mid = _rets(1000, mu=0, sig=0.005, seed=13)
    assert adv.srri_class(mid)["risk_class"] == 4


def test_kuantile_score():
    blocks = {
        "concentration": {"n_assets": 4, "effective_bets": 4.0},
        "es": {"es_pct": -0.036},
        "_var_pct": -0.030,                      # ES/VaR = 1.2
        "backtest": {"basel_zone": "green"},
        "real": {"prob_real_loss_12m": 0.0},
        "drawdown": {"calmar": 2.0},
    }
    s = adv.kuantile_score(1.0, blocks)          # sharpe 1.0 -> 100p
    assert s is not None
    assert s["components"]["sharpe"] == 100.0
    assert s["components"]["diversification"] == 100.0
    assert s["components"]["tail"] == pytest.approx(75.0)
    assert s["components"]["model"] == 100.0
    assert 90 < s["score"] <= 100

    # daha kotu sharpe skoru dusurmeli; eksik bilesenler yeniden agirliklanmali
    s2 = adv.kuantile_score(-0.5, {"_var_pct": -0.03})
    assert s2["components"] == {"sharpe": 25.0}
    assert s2["score"] == 25.0
    assert adv.kuantile_score(None, {}) is None


def test_style_analysis_recovers_mix():
    rng = np.random.default_rng(10)
    idx = pd.bdate_range("2023-01-02", periods=500)
    f1 = pd.Series(rng.normal(0.001, 0.02, 500), index=idx)
    f2 = pd.Series(rng.normal(0.0005, 0.01, 500), index=idx)
    factors = pd.DataFrame({"F1": f1, "F2": f2})
    fund = 0.6 * f1 + 0.4 * f2
    s = adv.style_analysis(fund, factors)
    assert s is not None
    assert s["weights"]["F1"] == pytest.approx(0.6, abs=0.02)
    assert s["weights"]["F2"] == pytest.approx(0.4, abs=0.02)
    assert s["r2"] > 0.99
    assert s["tracking_error_ann"] < 0.01
    assert s["lag_days"] == 0


def test_style_analysis_detects_nav_lag():
    # TEFAS fiyati 1 gun gecikmeli ilan edilir: fon(t) = karisim(t-1).
    # Ayni gun regresyonu iliskiyi goremez, lag=1 hizalamasi gormeli.
    rng = np.random.default_rng(11)
    idx = pd.bdate_range("2023-01-02", periods=500)
    f1 = pd.Series(rng.normal(0.001, 0.02, 500), index=idx)
    f2 = pd.Series(rng.normal(0.0005, 0.01, 500), index=idx)
    factors = pd.DataFrame({"F1": f1, "F2": f2})
    fund = (0.7 * f1 + 0.3 * f2).shift(1).dropna()
    s = adv.style_analysis(fund, factors)
    assert s is not None
    assert s["lag_days"] == 1
    assert s["weights"]["F1"] == pytest.approx(0.7, abs=0.02)
    assert s["r2"] > 0.99
