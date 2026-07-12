import numpy as np
import pandas as pd
import pytest

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import risk_engine as engine


def test_par_bond_prices_at_100():
    fair, mac, mod = engine.bond_metrics(0.10, 0.10, 5, 1)
    assert fair == pytest.approx(100.0)
    assert mod == pytest.approx(mac / 1.10)


def test_zero_coupon_macaulay_equals_maturity():
    _, mac, _ = engine.bond_metrics(0.0, 0.08, 3, 1)
    assert mac == pytest.approx(3.0)


def test_semiannual_par_bond():
    fair, _, _ = engine.bond_metrics(0.06, 0.06, 2, 2)
    assert fair == pytest.approx(100.0)


def test_discount_bond_below_par():
    fair, _, _ = engine.bond_metrics(0.05, 0.10, 5, 1)
    assert fair < 100


def test_log_returns_cleans_zero_prices():
    idx = pd.bdate_range("2025-01-01", periods=6)
    prices = pd.DataFrame({"A": [100, 101, 0, 103, 104, 105],
                           "B": [50, 51, 52, 53, 54, 55]}, index=idx)
    rets = engine.log_returns(prices)
    assert not np.isinf(rets.values).any()
    assert not rets.isna().any().any()


def test_historical_var_on_known_distribution():
    rng = np.random.default_rng(42)
    rets = pd.Series(rng.normal(0, 0.01, 100_000))
    var99 = engine.historical_var(rets, 0.99)
    assert var99 == pytest.approx(-2.326 * 0.01, rel=0.05)


def test_portfolio_weights_normalize():
    w = engine.portfolio_weights({"A": 30_000, "B": 70_000}, ["A", "B"])
    assert w.sum() == pytest.approx(1.0)
    assert w[1] == pytest.approx(0.7)


def test_diversification_benefit_nonnegative_for_imperfect_corr():
    rng = np.random.default_rng(7)
    a = rng.normal(0, 0.02, 5000)
    b = 0.3 * a + rng.normal(0, 0.02, 5000)
    rets = pd.DataFrame({"A": a, "B": b})
    d = engine.diversification(rets, {"A": 50_000, "B": 50_000})
    assert d["benefit"] >= 0


def test_stress_test_window():
    idx = pd.date_range("2020-02-01", "2020-04-30", freq="B")
    prices = pd.DataFrame({"X": np.linspace(100, 60, len(idx))}, index=idx)
    res = engine.stress_test(prices, {"X": 10_000}, "2020-02-20", "2020-03-23")
    assert res is not None
    assert res["cumulative_return"] < 0


def test_stress_test_missing_asset_returns_none():
    idx = pd.date_range("2024-01-01", periods=50, freq="B")
    prices = pd.DataFrame({"NEW": np.linspace(10, 12, 50)}, index=idx)
    assert engine.stress_test(prices, {"NEW": 1000}, "2020-02-20", "2020-03-23") is None


def test_position_pnl_with_and_without_cost():
    known = engine.position_pnl(10, 110, 100, fx=1.0)
    assert known["pnl"] == pytest.approx(100)
    assert known["pnl_pct"] == pytest.approx(10)
    unknown = engine.position_pnl(10, 110, None, fx=40.0)
    assert unknown["pnl"] is None
    assert unknown["value_try"] == pytest.approx(44_000)


def test_bond_risk_summary_shocks_symmetry():
    bonds = [{"name": "T1", "value_try": 100_000, "modified": 4.0}]
    s = engine.bond_risk_summary(bonds, 200_000)
    assert s["weighted_modified_duration"] == pytest.approx(4.0)
    assert s["rate_shocks"][100] == pytest.approx(-4_000)
    assert s["rate_shocks"][-100] == pytest.approx(4_000)
    assert s["portfolio_duration_contribution"] == pytest.approx(2.0)
