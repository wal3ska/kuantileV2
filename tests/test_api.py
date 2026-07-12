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
