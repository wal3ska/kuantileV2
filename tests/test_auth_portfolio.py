import os, sys
os.environ["DATABASE_URL"] = "sqlite:///./test_kuantile.db"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import email_service

sent = {}
def fake_send(to, token, lang="tr"):
    sent["to"] = to
    sent["token"] = token
    sent["lang"] = lang
email_service.send_verification = fake_send

from fastapi.testclient import TestClient
from api import app
from db import init_db, Base, engine

Base.metadata.drop_all(engine)
init_db()
client = TestClient(app)

EMAIL, PW = "test@kuantile.com", "guclu-sifre-123"


def test_register_sends_verification():
    r = client.post("/auth/register", json={"email": EMAIL, "nickname": "testci",
                                            "password": PW, "lang": "en"})
    assert r.status_code == 201
    assert sent["lang"] == "en"
    assert sent["to"] == EMAIL and len(sent["token"]) > 20


def test_login_blocked_before_verification():
    r = client.post("/auth/login", json={"email": EMAIL, "password": PW})
    assert r.status_code == 403


def test_verify_then_login():
    r = client.get(f"/auth/verify?token={sent['token']}")
    assert r.status_code == 200
    r = client.post("/auth/login", json={"email": EMAIL, "password": PW})
    assert r.status_code == 200
    assert r.json()["nickname"] == "testci"
    global TOKEN
    TOKEN = r.json()["access_token"]


def test_wrong_password_rejected():
    r = client.post("/auth/login", json={"email": EMAIL, "password": "yanlis-sifre"})
    assert r.status_code == 401


def test_save_and_load_portfolio():
    hdr = {"Authorization": f"Bearer {TOKEN}"}
    body = {
        "positions": [
            {"name": "THYAO", "ticker": "THYAO.IS", "currency": "TRY",
             "category": "BIST", "quantity": 100, "cost": 250.5},
            {"name": "AFT (Fon)", "ticker": "AFT", "currency": "TRY",
             "source": "tefas", "category": "TEFAS Fon", "quantity": 5000, "cost": None},
        ],
        "bonds": [
            {"name": "Hazine 2Y", "currency": "TRY", "nominal": 100000, "price": 92.5,
             "coupon_rate": 0.35, "frequency": 2, "years": 2, "ytm": 0.42, "cost": 90.0}
        ],
    }
    r = client.put("/portfolio", json=body, headers=hdr)
    assert r.status_code == 200, r.text
    r = client.get("/portfolio", headers=hdr)
    data = r.json()
    assert len(data["positions"]) == 2 and len(data["bonds"]) == 1
    assert data["positions"][1]["cost"] is None
    assert data["bonds"][0]["ytm"] == 0.42


def test_portfolio_requires_auth():
    assert client.get("/portfolio").status_code == 401


def test_duplicate_email_rejected():
    r = client.post("/auth/register", json={"email": EMAIL, "nickname": "testci", "password": PW})
    assert r.status_code == 409


def test_register_requires_nickname():
    r = client.post("/auth/register", json={"email": "nick@kuantile.com", "password": PW})
    assert r.status_code == 422
