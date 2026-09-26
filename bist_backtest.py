"""Quant Lab Faz 3 — walk-forward (OOS) backtest + reel getiri.

Dürüstlük ilkesi (qg-portfolio-risk): agirliklar YALNIZCA train bloguyla uretilir,
sonraki test bloguyla degerlendirilir, pencere kaydirilir. In-sample Sharpe yaniltir;
gercek beklenti OOS'tur. Sonuclar 1/N (esit agirlik) benchmark'iyla ve TUFE ile
enflasyondan arindirilmis reel getiriyle birlikte raporlanir.
"""

import numpy as np
import pandas as pd

import qglib.metrics as M
from bist_portfolio import TRADING_DAYS, returns_matrix, solve_weights


def _real(nom_cagr: float, dates: list) -> dict | None:
    """OOS penceresi boyunca TUFE ile reel CAGR. EVDS yoksa None."""
    try:
        from data_provider import fetch_cpi
        cpi = fetch_cpi()
    except Exception:
        return None
    if cpi is None or len(cpi) < 2:
        return None
    cpi = cpi.sort_index()
    t0, t1 = pd.Timestamp(dates[0]), pd.Timestamp(dates[-1])
    c0 = cpi[cpi.index <= t0]
    c1 = cpi[cpi.index <= t1]
    if c0.empty or c1.empty:
        return None
    years = (t1 - t0).days / 365.25
    if years <= 0:
        return None
    infl_cagr = float(c1.iloc[-1] / c0.iloc[-1]) ** (1 / years) - 1
    return {"real_cagr": (1 + nom_cagr) / (1 + infl_cagr) - 1, "inflation_cagr": infl_cagr}


def run_backtest(db, tickers: list[str], sector_map: dict[str, str], *,
                 method: str, max_assets: int = 30, max_weight: float = 0.10,
                 sector_cap: float | None = 0.30, rf_annual: float = 0.0,
                 window_years: int = 5, train_years: float = 3.0,
                 test_months: int = 3) -> dict:
    rets_full = returns_matrix(db, tickers[: max_assets * 2], window_years)
    if rets_full.shape[1] < 2 or len(rets_full) < 300:
        return {"error": "Backtest için yeterli fiyat geçmişi yok."}
    ordered = [t for t in tickers if t in rets_full.columns][:max_assets]
    R = rets_full[ordered].dropna()
    cols = list(R.columns)
    n = len(cols)
    sectors = [sector_map.get(c) or "Diğer" for c in cols]
    arr = R.values
    dates = list(R.index)

    train = int(train_years * TRADING_DAYS)
    test = max(21, int(test_months * 21))
    if len(arr) < train + test:
        train = max(TRADING_DAYS, len(arr) - test - 1)   # kisa gecmise uyarla
    ew = np.full(n, 1 / n)

    oos_dates, oos_port, oos_bench, rebs = [], [], [], 0
    for tr_idx, te_idx in M.walk_forward_splits(len(arr), train, test, step=test):
        train_df = pd.DataFrame(arr[tr_idx], columns=cols)
        try:
            w, _, _ = solve_weights(train_df, sectors, method, max_weight, sector_cap, rf_annual)
        except Exception:
            w = ew
        rebs += 1
        pr = arr[te_idx] @ w
        br = arr[te_idx] @ ew
        for k, i in enumerate(te_idx):
            oos_dates.append(dates[i]); oos_port.append(float(pr[k])); oos_bench.append(float(br[k]))

    if len(oos_port) < 30:
        return {"error": "Yeterli OOS gözlem üretilemedi; train/test penceresini küçültün."}

    port = np.array(oos_port)
    bench = np.array(oos_bench)
    rf_p = rf_annual / TRADING_DAYS
    s = M.summary(port, rf=rf_p, periods_per_year=TRADING_DAYS)
    b = M.summary(bench, rf=rf_p, periods_per_year=TRADING_DAYS)
    eq = np.cumprod(1 + port)
    beq = np.cumprod(1 + bench)
    idx = np.unique(np.linspace(0, len(eq) - 1, min(200, len(eq))).astype(int))
    curve = [{"date": oos_dates[i].isoformat(), "port": float(eq[i]), "bench": float(beq[i])}
             for i in idx]

    return {
        "method": method, "n_assets": n, "oos_days": len(port), "rebalances": rebs,
        "train_days": train, "test_days": test,
        "start": oos_dates[0].isoformat(), "end": oos_dates[-1].isoformat(),
        "metrics": {
            "cagr": s["cagr"], "ann_vol": s["ann_vol"], "sharpe": s["sharpe"],
            "sharpe_se": s["sharpe_se"], "psr_vs_0": s["psr_vs_0"], "sortino": s["sortino"],
            "max_drawdown": s["max_drawdown"], "calmar": s["calmar"],
        },
        "benchmark": {"cagr": b["cagr"], "sharpe": b["sharpe"], "max_drawdown": b["max_drawdown"]},
        "real": _real(s["cagr"], oos_dates),
        "curve": curve,
    }
