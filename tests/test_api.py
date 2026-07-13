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
