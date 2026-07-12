import os, sys
os.environ["DATABASE_URL"] = "sqlite:///./test_kuantile.db"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from fastapi.testclient import TestClient

import auth
import daily_mail
from api import app
from db import Bond, Portfolio, Position, SessionLocal, User, init_db

init_db()
client = TestClient(app)


def make_user(email, quantity=10, cost=100.0, with_bond=False):
    db = SessionLocal()
    u = User(email=email, password_hash=auth.hash_password("guclu-sifre"), is_verified=True)
    db.add(u)
    db.commit()
    pf = Portfolio(user_id=u.id)
    db.add(pf)
    db.commit()
    pf.positions.append(Position(name="THYAO", ticker="THYAO.IS", currency="TRY",
                                 source="yahoo", category="BIST", quantity=quantity, cost=cost))
    if with_bond:
        pf.bonds.append(Bond(name="Hazine 2Y", currency="TRY", nominal=10000, price=95.0,
                             coupon_rate=0.3, frequency=2, years=2, ytm=0.4, cost=None))
    db.commit()
    uid = u.id
    db.close()
    return uid


def test_unsubscribe_disables_daily_mail():
    uid = make_user("dm-unsub@kuantile.com")
    r = client.get(f"/auth/unsubscribe?token={auth.make_unsub_token(uid)}")
    assert r.status_code == 200
    db = SessionLocal()
    assert db.get(User, uid).daily_mail_enabled is False
    db.close()


def test_unsubscribe_rejects_login_token():
    uid = make_user("dm-unsub2@kuantile.com")
    r = client.get(f"/auth/unsubscribe?token={auth.make_token(uid)}")
    assert r.status_code == 400


def test_daily_mail_toggle_endpoint():
    uid = make_user("dm-toggle@kuantile.com")
    hdr = {"Authorization": f"Bearer {auth.make_token(uid)}"}
    r = client.post("/auth/daily-mail", json={"enabled": False}, headers=hdr)
    assert r.status_code == 200 and r.json()["daily_mail"] is False
    r = client.get("/auth/me", headers=hdr)
    assert r.json()["daily_mail"] is False


def test_run_sends_report(monkeypatch):
    make_user("dm-run@kuantile.com", quantity=10, cost=100.0, with_bond=True)
    key = "yahoo:THYAO.IS:TRY"
    prices = pd.DataFrame({key: [100.0, 110.0]},
                          index=pd.to_datetime(["2026-07-09", "2026-07-10"]))
    monkeypatch.setattr(daily_mail.dp, "build_try_prices",
                        lambda positions: (prices, 40.0, {key: 110.0}, []))
    sent = []
    monkeypatch.setattr(daily_mail.email_service, "send_email",
                        lambda to, subject, html: sent.append((to, subject, html)))
    assert daily_mail.run() == 0
    ours = [m for m in sent if m[0] == "dm-run@kuantile.com"]
    assert len(ours) == 1
    html = ours[0][2]
    assert "THYAO" in html and "Hazine 2Y" in html
    assert "1.100 TL" in html          # 10 adet * 110 TL
    assert "+10,00%" in html           # günlük değişim
    assert "/auth/unsubscribe?token=" in html


def test_run_skips_disabled_users(monkeypatch):
    uid = make_user("dm-skip@kuantile.com")
    client.get(f"/auth/unsubscribe?token={auth.make_unsub_token(uid)}")
    key = "yahoo:THYAO.IS:TRY"
    prices = pd.DataFrame({key: [100.0, 110.0]},
                          index=pd.to_datetime(["2026-07-09", "2026-07-10"]))
    monkeypatch.setattr(daily_mail.dp, "build_try_prices",
                        lambda positions: (prices, 40.0, {key: 110.0}, []))
    sent = []
    monkeypatch.setattr(daily_mail.email_service, "send_email",
                        lambda to, subject, html: sent.append(to))
    daily_mail.run()
    assert "dm-skip@kuantile.com" not in sent
