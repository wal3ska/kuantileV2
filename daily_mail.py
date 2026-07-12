"""Gunluk portfoy ozeti maili. Dogrulanmis ve maili acik her kullaniciya
portfoyunun guncel TL degerini ve gunluk degisimi gonderir.
Calistirma (cron): docker compose exec -T api python daily_mail.py"""

import sys
from datetime import datetime, timezone

import data_provider as dp
import email_service
import risk_engine as engine
from auth import make_unsub_token
from db import SessionLocal, User, init_db

APP_URL = "https://kuantile.com"
API_URL = "https://api.kuantile.com"


def _key(p) -> str:
    return f"{p.source}:{p.ticker}:{p.currency}"


def fmt_money(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".") + " TL"


def fmt_pct(v: float) -> str:
    return f"{v * 100:+.2f}%".replace(".", ",")


def daily_changes(prices_try) -> dict:
    """Anahtar -> (son TL fiyat, onceki TL fiyat). Tek gozlemli seriler atlanir."""
    out = {}
    if prices_try is None:
        return out
    for col in prices_try.columns:
        s = prices_try[col].dropna()
        if len(s) >= 2 and float(s.iloc[-2]) > 0:
            out[col] = (float(s.iloc[-1]), float(s.iloc[-2]))
    return out


def build_report_html(user, fx_now: float, last_native: dict, changes: dict) -> str | None:
    """Kullanicinin portfoy ozeti HTML'i. Fiyati bulunamayan pozisyonlar tabloda
    'veri yok' olarak isaretlenir; hicbir varligin verisi yoksa None doner."""
    pf = user.portfolio
    rows_html = []
    total = day_change = prev_total = 0.0
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
        if d:
            last_try, prev_try = d
            day_change += p.quantity * (last_try - prev_try)
            prev_total += p.quantity * prev_try
            day_cell = _colored(fmt_pct(last_try / prev_try - 1), last_try - prev_try)
        else:
            day_cell = "—"
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

    if prev_total > 0:
        day_line = (f"Günlük değişim: {_colored(fmt_money(day_change), day_change)} "
                    f"({_colored(fmt_pct(day_change / prev_total), day_change)})")
        if bond_total > 0:
            day_line += " <span style='color:#888;font-size:12px'>— tahviller hariç</span>"
    else:
        day_line = ""

    unsub = f"{API_URL}/auth/unsubscribe?token={make_unsub_token(user.id)}"
    date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto">
      <h2 style="color:#1f77b4">Kuantile — Günlük Portföy Özeti</h2>
      <p style="color:#888;margin-top:-8px">{date_str} &middot; USD/TRY: {fx_now:.2f}</p>
      <p style="font-size:22px;margin:16px 0 4px"><b>{fmt_money(total)}</b></p>
      <p style="margin:0 0 16px">{day_line}</p>
      <table width="100%" cellpadding="6" style="border-collapse:collapse;font-size:14px">
        <tr style="border-bottom:2px solid #1f77b4;text-align:left">
          <th>Varlık</th><th align="right">Adet</th><th align="right">Değer</th>
          <th align="right">Günlük</th><th align="right">Toplam K/Z</th>
        </tr>
        {''.join(rows_html)}
      </table>
      <p style="margin-top:20px"><a href="{APP_URL}" style="color:#1f77b4">Detaylı analiz için Kuantile'i açın →</a></p>
      <p style="color:#888;font-size:11px;margin-top:24px">
        Bu e-posta yatırım danışmanlığı değildir. Fiyatlar son işlem gününe aittir.<br>
        Günlük özeti almak istemiyorsanız <a href="{unsub}" style="color:#888">buradan kapatabilirsiniz</a>.
      </p>
    </div>
    """


def _colored(text: str, sign_of: float | None) -> str:
    if sign_of is None:
        return text
    color = "#2e7d32" if sign_of >= 0 else "#c62828"
    return f"<span style='color:{color}'>{text}</span>"


def run() -> int:
    init_db()
    db = SessionLocal()
    try:
        users = [u for u in db.query(User)
                 .filter(User.is_verified.is_(True), User.daily_mail_enabled.is_(True)).all()
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
        changes = daily_changes(prices_try)

        date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y")
        sent = errors = 0
        for u in users:
            try:
                html = build_report_html(u, fx_now, last_native, changes)
                if html is None:
                    print(f"ATLANDI {u.email}: fiyat verisi yok")
                    continue
                email_service.send_email(u.email, f"Günlük Portföy Özeti — {date_str}", html)
                sent += 1
            except Exception as exc:
                errors += 1
                print(f"HATA {u.email}: {exc}")
        print(f"Gönderildi: {sent}, hata: {errors}, veri bulunamayan anahtarlar: {failed}")
        return 1 if errors else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(run())
