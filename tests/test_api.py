import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_bond_duration_endpoint():
    r = client.post("/bond/duration", json={"coupon_rate": 0.10, "ytm": 0.10, "years": 5, "frequency": 1})
    body = r.json()
    assert r.status_code == 200
    assert abs(body["fair_price"] - 100.0) < 1e-6


def test_analyze_rejects_empty():
    assert client.post("/portfolio/analyze", json={}).status_code == 400


def test_analyze_validates_negative_quantity():
    r = client.post("/portfolio/analyze", json={"positions": [
        {"name": "X", "ticker": "X.IS", "currency": "TRY", "quantity": -5}]})
    assert r.status_code == 422


def test_gram_gold_synthetic_series(monkeypatch):
    import pandas as pd
    import data_provider as dp

    idx = pd.to_datetime(["2026-07-09", "2026-07-10"])
    raw = pd.DataFrame({"GC=F": [3000.0, 3100.0], "TRY=X": [40.0, 41.0]}, index=idx)

    def fake_fetch(tickers, start=None, retries=3):
        assert "GC=F" in tickers and "TRY=X" in tickers
        return raw
    monkeypatch.setattr(dp, "fetch_yahoo_prices", fake_fetch)

    prices, fx, last, failed = dp.build_try_prices(
        [{"name": "Altın (Gram TL)", "ticker": "GRAMALTIN",
          "currency": "TRY", "source": "yahoo"}])
    assert failed == []
    assert fx == 41.0
    expected = 3100.0 * 41.0 / dp.OUNCE_TO_GRAM
    assert abs(last["Altın (Gram TL)"] - expected) < 1e-6
    assert abs(prices["Altın (Gram TL)"].iloc[0] - 3000.0 * 40.0 / dp.OUNCE_TO_GRAM) < 1e-6


def test_simulate_custom_range(monkeypatch):
    import numpy as np
    import pandas as pd
    import data_provider as dp

    idx = pd.date_range("2026-01-01", periods=40, freq="D")
    vals = np.linspace(100.0, 150.0, 40)          # +%50 pencere boyunca
    raw = pd.DataFrame({"X": vals, "TRY=X": np.full(40, 40.0)}, index=idx)

    monkeypatch.setattr(dp, "fetch_yahoo_prices", lambda t, start=None, retries=3: raw)

    body = {"positions": [{"name": "X", "ticker": "X", "currency": "TRY",
                           "source": "yahoo", "quantity": 10}],
            "start": "2026-01-01", "end": "2026-02-09"}
    r = client.post("/portfolio/simulate", json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert abs(d["cumulative_return"] - 0.5) < 1e-9
    assert d["base_value_try"] == 1500.0           # 10 adet * 150 (son fiyat)
    assert abs(d["final_value_try"] - 2250.0) < 1e-6
    assert d["series"][0]["value"] == 1500.0
    assert len(d["series"]) >= 30
    assert d["missing_assets"] == []


def test_simulate_rejects_bad_range():
    body = {"positions": [{"name": "X", "ticker": "X", "currency": "TRY",
                           "source": "yahoo", "quantity": 1}],
            "start": "2026-02-01", "end": "2026-01-01"}
    assert client.post("/portfolio/simulate", json=body).status_code == 400
