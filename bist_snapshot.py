"""snapshot_build: fiyat serisi + fundamentallerden hisse basi metrik ureten offline is.

Ciktisi BistMetric tablosu (ham metrikler + eleme bayraklari). ESIKLER burada
uygulanmaz — panel bu ham degerleri okuyup kullanicinin (varsayilanli) esikleriyle
canli filtreler. Boylece esik degistirmek icin yeniden hesap gerekmez.
"""

import math
from datetime import date, timedelta

import numpy as np
from sqlalchemy import select

from db import (BistFundamental, BistMetric, BistPrice, BistSymbol,
                SessionLocal)

TRADING_DAYS = 252
ADV_WINDOW = 63          # ~3 ay, likidite icin
MIN_OBS = 60             # bu kadar gunu olmayan hisseye metrik uretme


def _altman_z(f: BistFundamental) -> float | None:
    """Altman Z" (gelismekte olan piyasa / imalat-disi varyant).
    Z" = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4. Finansal firmalarda cagirilmaz."""
    ta = f.total_assets
    if not ta or ta <= 0:
        return None
    ca, cl = f.current_assets, f.current_liabilities
    re, eq, ebit = f.retained_earnings, f.equity, f.ebit
    if ca is None or cl is None or eq is None:
        return None
    tl = ta - eq
    if tl <= 0:
        return None
    x1 = (ca - cl) / ta
    x2 = (re or 0.0) / ta
    x3 = (ebit or 0.0) / ta
    x4 = eq / tl
    return 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4


def _price_metrics(rows: list[tuple]) -> dict | None:
    """rows: (date, close, volume) artan tarih. Vol / geo getiri / ADV doner."""
    rows = sorted(rows, key=lambda r: r[0])
    closes = np.array([r[1] for r in rows], dtype=np.float64)
    closes = closes[closes > 0]
    if len(closes) < MIN_OBS:
        return None
    logret = np.diff(np.log(closes))
    if len(logret) < MIN_OBS - 1:
        return None
    ann_vol = float(np.std(logret, ddof=1) * math.sqrt(TRADING_DAYS))
    geo = float(math.exp(np.mean(logret) * TRADING_DAYS) - 1.0)
    simple = np.diff(closes) / closes[:-1]
    mean_ann = float(np.mean(simple) * TRADING_DAYS)
    # ADV: son ADV_WINDOW gunun close*volume medyani (TL)
    tail = rows[-ADV_WINDOW:]
    tl_vals = [r[1] * r[2] for r in tail if r[2] is not None and r[1] is not None]
    adv = float(np.median(tl_vals)) if tl_vals else None
    return {"obs": len(closes), "last_price": float(closes[-1]),
            "ann_vol": ann_vol, "geo_return_ann": geo, "mean_return_ann": mean_ann,
            "adv_tl": adv}


def build_metrics(db, window_years: int = 5) -> int:
    start = date.today() - timedelta(days=int(window_years * 365.25))
    symbols = {s.ticker: s for s in db.execute(select(BistSymbol)).scalars()}

    # Fundamentaller: hisse basi donemleri (yeni -> eski) topla
    funds: dict[str, list[BistFundamental]] = {}
    for f in db.execute(select(BistFundamental)).scalars():
        funds.setdefault(f.ticker, []).append(f)
    for lst in funds.values():
        lst.sort(key=lambda f: f.period, reverse=True)

    out = []
    for tk, sym in symbols.items():
        rows = db.execute(
            select(BistPrice.d, BistPrice.close, BistPrice.volume)
            .where(BistPrice.ticker == tk, BistPrice.d >= start)
        ).all()
        pm = _price_metrics([(d, c, v) for d, c, v in rows])
        if pm is None:
            continue

        flist = funds.get(tk, [])
        latest = flist[0] if flist else None

        # Altman Z" — finansal olmayan + bilanco varsa
        altman = None
        if not sym.is_financial and latest is not None:
            altman = _altman_z(latest)

        # Negatif ozkaynak: once hazir SirketBilgileri degeri, yoksa bilanco
        eq = sym.equity if sym.equity is not None else (latest.equity if latest else None)
        neg_equity = eq is not None and eq < 0

        # Surekli zarar: son 4 donem net zarar; yoksa guncel net kar proxy
        nis = [f.net_income for f in flist[:4] if f.net_income is not None]
        if len(nis) >= 4:
            persistent_loss = all(n < 0 for n in nis)
        elif sym.net_profit is not None:
            persistent_loss = sym.net_profit < 0
        else:
            persistent_loss = False

        out.append({
            "ticker": tk, **pm, "altman_z": altman,
            "neg_equity": bool(neg_equity),
            "persistent_loss": bool(persistent_loss),
            "is_watchlist": bool(sym.is_watchlist),
        })

    # Tam yenile: eski metrikleri temizleyip yeniden yaz
    db.query(BistMetric).delete()
    if out:
        db.bulk_insert_mappings(BistMetric, out)
    db.commit()
    return len(out)


def run() -> str:
    db = SessionLocal()
    try:
        return f"snapshot: {build_metrics(db)} hisse metrigi"
    finally:
        db.close()
