"""Donemsel portfoy raporu maili (gunluk / haftalik / aylik / yillik).
Dogrulanmis ve ilgili donemi acik her kullaniciya, kullanicinin dilinde
(users.lang) portfoy degerini, donem getirisini, tarihsel yuzdelik dilimini
ve VaR degisimini gonderir.
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
    "daily": {"n": 1}, "weekly": {"n": 5}, "monthly": {"n": 21}, "yearly": {"n": 252},
}

CONFIDENCE = 0.99

L = {
    "tr": {
        "daily": "Günlük", "weekly": "Haftalık", "monthly": "Aylık", "yearly": "Yıllık",
        "subject": "{label} Portföy Raporu — {date}",
        "header": "Kuantile — {label} Portföy Raporu",
        "hello": "Merhaba",
        "change": "{label} değişim:",
        "exBonds": "— tahviller hariç",
        "pctl": "Bu dönemki getiri, portföyünüzün tarihsel {adj} getirilerinin <b>%{p}</b>'lik diliminde ({side}).",
        "adj_daily": "günlük", "adj_weekly": "haftalık", "adj_monthly": "aylık", "adj_yearly": "yıllık",
        "above": "tarihsel ortalamanın üstünde", "below": "tarihsel ortalamanın altında",
        "var": "VaR (%{c}, 1 gün): <b>{v}</b>",
        "varUp": " — dönem başına göre risk arttı ({d})",
        "varDown": " — dönem başına göre risk azaldı ({d})",
        "varFlat": " — dönem başına göre sabit kaldı",
        "colAsset": "Varlık", "colQty": "Adet", "colValue": "Değer", "colPnl": "Toplam K/Z",
        "bond": "tahvil", "noData": "veri yok",
        "cta": "Detaylı analiz için Kuantile'i açın →",
        "disclaimer": "Bu e-posta yatırım danışmanlığı değildir. Fiyatlar son işlem gününe aittir.",
        "unsub": "Rapor maillerini almak istemiyorsanız <a href=\"{url}\" style=\"color:#888\">buradan kapatabilirsiniz</a>.",
        "currency": "TL", "dec": ",", "thou": ".",
    },
    "en": {
        "daily": "Daily", "weekly": "Weekly", "monthly": "Monthly", "yearly": "Yearly",
        "subject": "{label} Portfolio Report — {date}",
        "header": "Kuantile — {label} Portfolio Report",
        "hello": "Hello",
        "change": "{label} change:",
        "exBonds": "— excluding bonds",
        "pctl": "This period's return sits in the <b>{p}th</b> percentile of your portfolio's historical {adj} returns ({side}).",
        "adj_daily": "daily", "adj_weekly": "weekly", "adj_monthly": "monthly", "adj_yearly": "yearly",
        "above": "above the historical average", "below": "below the historical average",
        "var": "VaR ({c}%, 1 day): <b>{v}</b>",
        "varUp": " — risk increased vs. the start of the period ({d})",
        "varDown": " — risk decreased vs. the start of the period ({d})",
        "varFlat": " — unchanged vs. the start of the period",
        "colAsset": "Asset", "colQty": "Qty", "colValue": "Value", "colPnl": "Total P/L",
        "bond": "bond", "noData": "no data",
        "cta": "Open Kuantile for detailed analysis →",
        "disclaimer": "This email is not investment advice. Prices are as of the last trading day.",
        "unsub": "If you no longer want report emails you can <a href=\"{url}\" style=\"color:#888\">turn them off here</a>.",
        "currency": "TRY", "dec": ".", "thou": ",",
    },
}


def _key(p) -> str:
    return f"{p.source}:{p.ticker}:{p.currency}"


def fmt_money(v: float, x: dict) -> str:
    return f"{v:,.0f}".replace(",", x["thou"]) + f" {x['currency']}"


def fmt_pct(v: float, x: dict) -> str:
    return f"{v * 100:+.2f}%".replace(".", x["dec"])


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
    """Kullanicinin dilinde donemsel rapor HTML'i. Hic veri yoksa None."""
    x = L.get(user.lang or "tr", L["tr"])
    label = x[period]
    n = PERIODS[period]["n"]
    pf = user.portfolio
    rows_html = []
    total = 0.0
    priced = 0

    for p in pf.positions:
        k = _key(p)
        if k not in last_native:
            rows_html.append(
                f"<tr><td>{p.name}</td><td colspan='4' style='color:#888'>{x['noData']}</td></tr>")
            continue
        priced += 1
        fx = fx_now if p.currency == "USD" else 1.0
        res = engine.position_pnl(p.quantity, last_native[k], p.cost, fx)
        total += res["value_try"]
        d = changes.get(k)
        day_cell = _colored(fmt_pct(d, x), d) if d is not None else "—"
        pnl_cell = _colored(fmt_pct(res["pnl_pct"] / 100, x), res["pnl"]) if res["pnl_pct"] is not None else "—"
        rows_html.append(
            f"<tr><td>{p.name}</td><td align='right'>{p.quantity:g}</td>"
            f"<td align='right'>{fmt_money(res['value_try'], x)}</td>"
            f"<td align='right'>{day_cell}</td><td align='right'>{pnl_cell}</td></tr>")

    bond_total = 0.0
    for b in pf.bonds:
        fx = fx_now if b.currency == "USD" else 1.0
        v = b.nominal / 100 * b.price * fx
        bond_total += v
        rows_html.append(
            f"<tr><td>{b.name} <span style='color:#888'>({x['bond']})</span></td>"
            f"<td align='right'>{b.nominal:g}</td>"
            f"<td align='right'>{fmt_money(v, x)}</td><td align='right'>—</td><td align='right'>—</td></tr>")
    total += bond_total

    if priced == 0 and bond_total == 0:
        return None

    stats = period_stats(portfolio_series(pf, prices_try), n)
    stat_lines = []
    if stats is not None:
        line = f"{x['change'].format(label=label)} {_colored(fmt_pct(stats['ret'], x), stats['ret'])}"
        if bond_total > 0:
            line += f" <span style='color:#888;font-size:12px'>{x['exBonds']}</span>"
        stat_lines.append(line)
        if stats["percentile"] is not None:
            pctl = stats["percentile"]
            side = x["above"] if pctl >= 50 else x["below"]
            stat_lines.append(x["pctl"].format(p=f"{pctl:.0f}", adj=x[f"adj_{period}"], side=side))
        if stats["var_now"] is not None:
            var_txt = x["var"].format(c=f"{CONFIDENCE * 100:.0f}", v=fmt_pct(stats["var_now"], x))
            if stats["var_prev"] is not None and period != "daily":
                delta = stats["var_now"] - stats["var_prev"]
                if abs(delta) < 0.00005:  # gosterimde 0,00% olacak degisim
                    var_txt += x["varFlat"]
                else:
                    key = "varUp" if delta < 0 else "varDown"  # VaR negatif: daha negatif = daha riskli
                    var_txt += x[key].format(d=fmt_pct(abs(delta), x).lstrip("+"))
            stat_lines.append(var_txt)

    unsub = f"{API_URL}/auth/unsubscribe?token={make_unsub_token(user.id)}"
    date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    hitap = user.nickname or user.email.split("@")[0]
    stats_html = "".join(f"<p style='margin:2px 0'>{s}</p>" for s in stat_lines)

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto">
      <h2 style="color:#1f77b4">{x['header'].format(label=label)}</h2>
      <p style="color:#888;margin-top:-8px">{x['hello']} {hitap} &middot; {date_str} &middot; USD/TRY: {fx_now:.2f}</p>
      <p style="font-size:22px;margin:16px 0 6px"><b>{fmt_money(total, x)}</b></p>
      <div style="margin:0 0 16px;font-size:14px">{stats_html}</div>
      <table width="100%" cellpadding="6" style="border-collapse:collapse;font-size:14px">
        <tr style="border-bottom:2px solid #1f77b4;text-align:left">
          <th>{x['colAsset']}</th><th align="right">{x['colQty']}</th><th align="right">{x['colValue']}</th>
          <th align="right">{label}</th><th align="right">{x['colPnl']}</th>
        </tr>
        {''.join(rows_html)}
      </table>
      <p style="margin-top:20px"><a href="{APP_URL}" style="color:#1f77b4">{x['cta']}</a></p>
      <p style="color:#888;font-size:11px;margin-top:24px">
        {x['disclaimer']}<br>
        {x['unsub'].format(url=unsub)}
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
    n = PERIODS[period]["n"]
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
        changes = position_changes(prices_try, n)

        date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y")
        sent = errors = 0
        for u in users:
            try:
                html = build_report_html(u, period, fx_now, prices_try, last_native, changes)
                if html is None:
                    print(f"ATLANDI {u.email}: fiyat verisi yok")
                    continue
                x = L.get(u.lang or "tr", L["tr"])
                subject = x["subject"].format(label=x[period], date=date_str)
                email_service.send_email(u.email, subject, html)
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
