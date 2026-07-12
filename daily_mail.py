"""Donemsel portfoy raporu maili (gunluk / haftalik / aylik / yillik).
Dogrulanmis ve maili acik her kullaniciya portfoyunun guncel degerini,
donem getirisini, tarihsel yuzdelik dilimini ve VaR degisimini gonderir.
Calistirma (cron): docker compose exec -T api python daily_mail.py [daily|weekly|monthly|yearly]"""

import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import data_provider as dp
import email_service
import risk_engine as engine
from auth import make_unsub_token
from db import SessionLocal, User, init_db

APP_URL = "https://kuantile.com"
API_URL = "https://api.kuantile.com"

# n: donemin yaklasik islem gunu sayisi (pct_change penceresi)
PERIODS = {
    "daily":   {"label": "Günlük",   "n": 1,   "adj": "günlük"},
    "weekly":  {"label": "Haftalık", "n": 5,   "adj": "haftalık"},
    "monthly": {"label": "Aylık",    "n": 21,  "adj": "aylık"},
    "yearly":  {"label": "Yıllık",   "n": 252, "adj": "yıllık"},
}

CONFIDENCE = 0.99


def _key(p) -> str:
    return f"{p.source}:{p.ticker}:{p.currency}"


def fmt_money(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".") + " TL"


def fmt_pct(v: float) -> str:
    return f"{v * 100:+.2f}%".replace(".", ",")


def _colored(text: str, sign_of: float | None) -> str:
    if sign_of is None:
        return text
    color = "#2e7d32" if sign_of >= 0 else "#c62828"
    return f"<span style='color:{color}'>{text}</span>"


def portfolio_series(pf, prices_try) -> pd.Series | None:
    """Mevcut adetlerle portfoyun gunluk TL deger serisi. Tahviller haric
    (statik fiyat girildikleri icin zaman serisi olusturmazlar)."""
    cols = {}
    for p in pf.positions:
        k = _key(p)
        if prices_try is not None and k in prices_try.columns:
            cols[k] = prices_try[k] * p.quantity
    if not cols:
        return None
    df = pd.DataFrame(cols).ffill().dropna()
    if len(df) < 3:
        return None
    return df.sum(axis=1)


def period_stats(series: pd.Series, n: int) -> dict | None:
    """Donem getirisi, tarihsel yuzdelik dilim ve VaR degisimi."""
    if series is None or len(series) <= n + 2:
        return None
    rets = series.pct_change(n).dropna()
    if rets.empty:
        return None
    current = float(rets.iloc[-1])
    hist = rets.iloc[:-1]
    percentile = float((hist < current).mean() * 100) if len(hist) >= 20 else None

    daily = engine.log_returns(series.to_frame("v"))["v"]
    var_now = var_prev = None
    if len(daily) >= 60:
        var_now = float(np.percentile(daily, (1 - CONFIDENCE) * 100))
        prev = daily.iloc[:-n] if len(daily) > n + 60 else None
        if prev is not None:
            var_prev = float(np.percentile(prev, (1 - CONFIDENCE) * 100))
    return {"ret": current, "percentile": percentile, "var_now": var_now, "var_prev": var_prev}


def build_report_html(user, period: str, fx_now: float, prices_try,
                      last_native: dict, changes: dict) -> str | None:
    """Kullanicinin donemsel rapor HTML'i. Hicbir varligin verisi yoksa None."""
    cfg = PERIODS[period]
    n = cfg["n"]
    pf = user.portfolio
    rows_html = []
    total = 0.0
    priced = 0

    for p in pf.positions:
        k = _key(p)
        if k not in last_native:
            rows_html.append(
                f"<tr><td>{p.name}</td><td colspan='4' style='color:#888'>veri yok</td></tr>")
            continue
        priced += 1
        fx = fx_now if p.currency == "USD" else 1.0
        res = engine.position_pnl(p.quantity, last_native[k], p.cost, fx)
        total += res["value_try"]
        d = changes.get(k)
        day_cell = _colored(fmt_pct(d), d) if d is not None else "—"
        pnl_cell = _colored(fmt_pct(res["pnl_pct"] / 100), res["pnl"]) if res["pnl_pct"] is not None else "—"
        rows_html.append(
            f"<tr><td>{p.name}</td><td align='right'>{p.quantity:g}</td>"
            f"<td align='right'>{fmt_money(res['value_try'])}</td>"
            f"<td align='right'>{day_cell}</td><td align='right'>{pnl_cell}</td></tr>")

    bond_total = 0.0
    for b in pf.bonds:
        fx = fx_now if b.currency == "USD" else 1.0
        v = b.nominal / 100 * b.price * fx
        bond_total += v
        rows_html.append(
            f"<tr><td>{b.name} <span style='color:#888'>(tahvil)</span></td>"
            f"<td align='right'>{b.nominal:g}</td>"
            f"<td align='right'>{fmt_money(v)}</td><td align='right'>—</td><td align='right'>—</td></tr>")
    total += bond_total

    if priced == 0 and bond_total == 0:
        return None

    stats = period_stats(portfolio_series(pf, prices_try), n)
    stat_lines = []
    if stats is not None:
        line = f"{cfg['label']} değişim: {_colored(fmt_pct(stats['ret']), stats['ret'])}"
        if bond_total > 0:
            line += " <span style='color:#888;font-size:12px'>— tahviller hariç</span>"
        stat_lines.append(line)
        if stats["percentile"] is not None:
            pctl = stats["percentile"]
            yorum = "tarihsel ortalamanın üstünde" if pctl >= 50 else "tarihsel ortalamanın altında"
            stat_lines.append(
                f"Bu {cfg['adj']} getiri, portföyünüzün tarihsel {cfg['adj']} getirilerinin "
                f"<b>%{pctl:.0f}</b>'lik diliminde ({yorum}).")
        if stats["var_now"] is not None:
            var_txt = f"VaR (%{CONFIDENCE * 100:.0f}, 1 gün): <b>{fmt_pct(stats['var_now'])}</b>"
            if stats["var_prev"] is not None and period != "daily":
                delta = stats["var_now"] - stats["var_prev"]
                if abs(delta) < 0.00005:  # gosterimde 0,00% olacak degisim
                    var_txt += " — dönem başına göre sabit kaldı"
                else:
                    yon = "arttı" if delta < 0 else "azaldı"  # VaR negatif: daha negatif = daha riskli
                    var_txt += (f" — dönem başına göre risk {yon} "
                                f"({fmt_pct(abs(delta)).lstrip('+')})")
            stat_lines.append(var_txt)

    unsub = f"{API_URL}/auth/unsubscribe?token={make_unsub_token(user.id)}"
    date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    hitap = user.nickname or user.email.split("@")[0]
    stats_html = "".join(f"<p style='margin:2px 0'>{s}</p>" for s in stat_lines)

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto">
      <h2 style="color:#1f77b4">Kuantile — {cfg['label']} Portföy Raporu</h2>
      <p style="color:#888;margin-top:-8px">Merhaba {hitap} &middot; {date_str} &middot; USD/TRY: {fx_now:.2f}</p>
      <p style="font-size:22px;margin:16px 0 6px"><b>{fmt_money(total)}</b></p>
      <div style="margin:0 0 16px;font-size:14px">{stats_html}</div>
      <table width="100%" cellpadding="6" style="border-collapse:collapse;font-size:14px">
        <tr style="border-bottom:2px solid #1f77b4;text-align:left">
          <th>Varlık</th><th align="right">Adet</th><th align="right">Değer</th>
          <th align="right">{cfg['label']}</th><th align="right">Toplam K/Z</th>
        </tr>
        {''.join(rows_html)}
      </table>
      <p style="margin-top:20px"><a href="{APP_URL}" style="color:#1f77b4">Detaylı analiz için Kuantile'i açın →</a></p>
      <p style="color:#888;font-size:11px;margin-top:24px">
        Bu e-posta yatırım danışmanlığı değildir. Fiyatlar son işlem gününe aittir.<br>
        Özet maillerini almak istemiyorsanız <a href="{unsub}" style="color:#888">buradan kapatabilirsiniz</a>.
      </p>
    </div>
    """


def position_changes(prices_try, n: int) -> dict:
    """Anahtar -> donemlik yuzde degisim."""
    out = {}
    if prices_try is None:
        return out
    for col in prices_try.columns:
        s = prices_try[col].dropna()
        if len(s) > n and float(s.iloc[-1 - n]) > 0:
            out[col] = float(s.iloc[-1] / s.iloc[-1 - n] - 1)
    return out


def run(period: str = "daily") -> int:
    if period not in PERIODS:
        print(f"Bilinmeyen dönem: {period} (daily|weekly|monthly|yearly)")
        return 2
    cfg = PERIODS[period]
    init_db()
    db = SessionLocal()
    try:
        flag = {"daily": User.mail_daily, "weekly": User.mail_weekly,
                "monthly": User.mail_monthly, "yearly": User.mail_yearly}[period]
        users = [u for u in db.query(User)
                 .filter(User.is_verified.is_(True), flag.is_(True)).all()
                 if u.portfolio is not None and (u.portfolio.positions or u.portfolio.bonds)]
        if not users:
            print("Gönderilecek kullanıcı yok.")
            return 0

        uniq = {}
        for u in users:
            for p in u.portfolio.positions:
                uniq[_key(p)] = {"name": _key(p), "ticker": p.ticker,
                                 "currency": p.currency, "source": p.source}
        if uniq:
            prices_try, fx_now, last_native, failed = dp.build_try_prices(list(uniq.values()))
        else:
            raw = dp.fetch_yahoo_prices(("TRY=X",))
            prices_try, last_native, failed = None, {}, []
            fx_now = float(raw["TRY=X"].dropna().iloc[-1])
        changes = position_changes(prices_try, cfg["n"])

        date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y")
        sent = errors = 0
        for u in users:
            try:
                html = build_report_html(u, period, fx_now, prices_try, last_native, changes)
                if html is None:
                    print(f"ATLANDI {u.email}: fiyat verisi yok")
                    continue
                email_service.send_email(u.email, f"{cfg['label']} Portföy Raporu — {date_str}", html)
                sent += 1
            except Exception as exc:
                errors += 1
                print(f"HATA {u.email}: {exc}")
        print(f"[{period}] Gönderildi: {sent}, hata: {errors}, veri bulunamayan anahtarlar: {failed}")
        return 1 if errors else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else "daily"))
