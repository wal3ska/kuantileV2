import os, sys
os.environ["DATABASE_URL"] = "sqlite:///./test_kuantile.db"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

import auth
import daily_mail
from api import app
from db import Bond, Portfolio, Position, SessionLocal, User, init_db

init_db()
client = TestClient(app)

KEY = "yahoo:THYAO.IS:TRY"


def make_user(email, quantity=10, cost=100.0, with_bond=False, nickname="testci", lang="tr"):
    db = SessionLocal()
    u = User(email=email, nickname=nickname, lang=lang,
             password_hash=auth.hash_password("guclu-sifre"), is_verified=True)
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


def short_prices():
    return pd.DataFrame({KEY: [100.0, 110.0]},
                        index=pd.to_datetime(["2026-07-09", "2026-07-10"]))


def long_prices(rows=300):
    rng = np.random.default_rng(42)
    idx = pd.bdate_range("2025-05-01", periods=rows)
    vals = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, rows)))
    return pd.DataFrame({KEY: vals}, index=idx)


def patch_prices(monkeypatch, prices):
    last = float(prices[KEY].iloc[-1])
    monkeypatch.setattr(daily_mail.dp, "build_try_prices",
                        lambda positions: (prices, 40.0, {KEY: last}, []))
    sent = []
    monkeypatch.setattr(daily_mail.email_service, "send_email",
                        lambda to, subject, html: sent.append((to, subject, html)))
    return sent


def test_unsubscribe_disables_daily_mail():
    uid = make_user("dm-unsub@kuantile.com")
    r = client.get(f"/auth/unsubscribe?token={auth.make_unsub_token(uid)}")
    assert r.status_code == 200
    db = SessionLocal()
    assert db.get(User, uid).mail_daily is False
    db.close()


def test_unsubscribe_rejects_login_token():
    uid = make_user("dm-unsub2@kuantile.com")
    r = client.get(f"/auth/unsubscribe?token={auth.make_token(uid)}")
    assert r.status_code == 400


def test_mail_prefs_endpoint():
    uid = make_user("dm-toggle@kuantile.com")
    hdr = {"Authorization": f"Bearer {auth.make_token(uid)}"}
    body = {"daily": False, "weekly": True, "monthly": False, "yearly": True}
    r = client.post("/auth/mail-prefs", json=body, headers=hdr)
    assert r.status_code == 200 and r.json()["mail"] == body
    r = client.get("/auth/me", headers=hdr)
    assert r.json()["mail"] == body
    assert r.json()["nickname"] == "testci"


def test_weekly_respects_prefs(monkeypatch):
    uid = make_user("dm-noweek@kuantile.com")
    hdr = {"Authorization": f"Bearer {auth.make_token(uid)}"}
    client.post("/auth/mail-prefs", headers=hdr,
                json={"daily": True, "weekly": False, "monthly": True, "yearly": True})
    sent = patch_prices(monkeypatch, long_prices())
    daily_mail.run("weekly")
    assert all(m[0] != "dm-noweek@kuantile.com" for m in sent)
    sent2 = patch_prices(monkeypatch, short_prices())
    daily_mail.run("daily")
    assert any(m[0] == "dm-noweek@kuantile.com" for m in sent2)


def test_daily_run_sends_report(monkeypatch):
    make_user("dm-run@kuantile.com", quantity=10, cost=100.0, with_bond=True, nickname="anil")
    sent = patch_prices(monkeypatch, short_prices())
    assert daily_mail.run("daily") == 0
    ours = [m for m in sent if m[0] == "dm-run@kuantile.com"]
    assert len(ours) == 1
    subject, html = ours[0][1], ours[0][2]
    assert "Günlük Portföy Raporu" in subject
    assert "Merhaba anil" in html
    assert "THYAO" in html and "Hazine 2Y" in html
    assert "1.100 TL" in html          # 10 adet * 110 TL
    assert "+10,00%" in html           # günlük değişim (tabloda)
    assert "/auth/unsubscribe?token=" in html


def test_weekly_run_includes_percentile_and_var(monkeypatch):
    make_user("dm-week@kuantile.com", quantity=10, cost=None)
    sent = patch_prices(monkeypatch, long_prices())
    assert daily_mail.run("weekly") == 0
    ours = [m for m in sent if m[0] == "dm-week@kuantile.com"]
    assert len(ours) == 1
    subject, html = ours[0][1], ours[0][2]
    assert "Haftalık Portföy Raporu" in subject
    assert "Haftalık değişim:" in html
    assert "diliminde" in html          # yüzdelik dilim cümlesi
    assert "VaR (%99" in html
    assert "dönem başına göre" in html  # VaR değişim cümlesi (yön veya "sabit kaldı")


def test_period_stats_math():
    s = pd.Series(np.linspace(100, 200, 300),
                  index=pd.bdate_range("2025-05-01", periods=300))
    st = daily_mail.period_stats(s, "weekly")
    assert st is not None and st["ret"] > 0
    assert st["percentile"] is not None and 0 <= st["percentile"] <= 100
    assert st["var_now"] is not None


def test_weekly_old_price_is_seven_calendar_days_back():
    """Kripto gibi 7 gün işlem gören varlıkta haftalık pencere tam 7 takvim günü olmalı
    (eski satır-bazlı kod 5 gün geriye gidiyordu)."""
    idx = pd.date_range("2026-06-01", periods=60, freq="D")
    vals = np.linspace(100, 400, 60)
    df = pd.DataFrame({KEY: vals}, index=idx)
    ch = daily_mail.position_changes(df, "weekly")
    expected = vals[-1] / vals[-1 - 7] - 1
    assert abs(ch[KEY] - expected) < 1e-12
    wrong_5day = vals[-1] / vals[-1 - 5] - 1
    assert abs(ch[KEY] - wrong_5day) > 1e-9


def test_weekly_old_price_pure_bist_matches_friday_to_friday():
    """İş günü takvimli seride 7 takvim günü önce = önceki cuma kapanışı."""
    idx = pd.bdate_range("2026-06-01", periods=30)   # cuma biter
    vals = np.linspace(100, 200, 30)
    df = pd.DataFrame({KEY: vals}, index=idx)
    ch = daily_mail.position_changes(df, "weekly")
    expected = vals[-1] / vals[-1 - 5] - 1            # 5 iş günü = önceki cuma
    assert abs(ch[KEY] - expected) < 1e-12


def test_daily_change_is_last_two_closes():
    df = short_prices()                               # 100 -> 110
    ch = daily_mail.position_changes(df, "daily")
    assert abs(ch[KEY] - 0.10) < 1e-12


def test_run_skips_disabled_users(monkeypatch):
    uid = make_user("dm-skip@kuantile.com")
    client.get(f"/auth/unsubscribe?token={auth.make_unsub_token(uid)}")
    sent = patch_prices(monkeypatch, short_prices())
    daily_mail.run("daily")
    assert all(m[0] != "dm-skip@kuantile.com" for m in sent)


def test_unknown_period_rejected():
    assert daily_mail.run("hourly") == 2


def test_english_user_gets_english_report(monkeypatch):
    make_user("dm-en@kuantile.com", quantity=10, cost=100.0, with_bond=True,
              nickname="john", lang="en")
    sent = patch_prices(monkeypatch, long_prices())
    assert daily_mail.run("weekly") == 0
    ours = [m for m in sent if m[0] == "dm-en@kuantile.com"]
    assert len(ours) == 1
    subject, html = ours[0][1], ours[0][2]
    assert "Weekly Portfolio Report" in subject
    assert "Hello john" in html
    assert "Weekly change:" in html
    assert "percentile" in html
    assert "VaR (99%" in html
    assert "(bond)" in html
    assert "TRY" in html and " TL" not in html   # EN para birimi etiketi
    assert "turn them off here" in html
