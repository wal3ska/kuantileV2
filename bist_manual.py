"""Quant Lab — Manuel Test: kullanicinin kendi girdigi hisse+agirliklar icin
sabit-agirlik tarihsel backtest + Sharpe/PSR + Monte Carlo projeksiyon + VaR/bilesen risk.

Optimizasyon YOK; agirliklar kullanicinindir (normalize edilir). "Backtest" = sabit
agirlikli portfoyun tarihsel getiri egrisi (gunluk yeniden dengeli), 1/N ile kiyas.
"""

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select

import qglib.metrics as M
import qglib.portfolio as PF
from advanced_risk import ledoit_wolf_cov
from bist_portfolio import TRADING_DAYS, returns_matrix
from db import BistPrice, BistSymbol

NOTIONAL = 1_000_000.0


def _gold_beta(db, port: np.ndarray, dates) -> dict | None:
    rows = db.execute(select(BistPrice.d, BistPrice.close).where(BistPrice.ticker == "XAUTRY")).all()
    if len(rows) < 60:
        return None
    g = pd.Series({d: c for d, c in rows}).sort_index().pct_change().dropna()
    g.index = pd.to_datetime(g.index)
    pr = pd.Series(port, index=pd.to_datetime(list(dates)))
    j = pd.concat([pr.rename("p"), g.rename("g")], axis=1).dropna()
    if len(j) < 60:
        return None
    r = PF.capm_regression(j["p"].values, j["g"].values, periods_per_year=TRADING_DAYS)
    return {"beta": r["beta"], "r2": r["r2"]}


def manual_eval(db, holdings: list[dict], *, rf_annual: float = 0.0, window_years: int = 5,
                horizon_months: int = 9, notional: float = NOTIONAL, n_sims: int = 1000) -> dict:
    req_tickers = []
    wmap: dict[str, float] = {}
    for h in holdings:
        t = str(h.get("ticker", "")).strip().upper()
        if not t:
            continue
        wmap[t] = wmap.get(t, 0.0) + max(float(h.get("weight", 0) or 0), 0.0)
        req_tickers.append(t)
    if not wmap:
        return {"error": "En az bir hisse ve ağırlık girin."}

    rets = returns_matrix(db, list(wmap.keys()), window_years)
    used = [c for c in rets.columns if c in wmap]
    if len(used) < 1:
        return {"error": "Girilen kodların yeterli fiyat geçmişi yok (kod hatalı olabilir)."}
    rets = rets[used].dropna()
    missing = [t for t in wmap if t not in used]

    w = np.array([wmap[c] for c in used], dtype=float)
    if w.sum() <= 0:
        return {"error": "Ağırlık toplamı sıfır."}
    w = w / w.sum()

    secmap = {s.ticker: s.sector for s in
              db.execute(select(BistSymbol).where(BistSymbol.ticker.in_(used))).scalars()}
    sectors = [secmap.get(c) or "Diğer" for c in used]
    n = len(used)

    mu_ann = rets.mean().values * TRADING_DAYS
    cov_ann = ledoit_wolf_cov(rets) * TRADING_DAYS
    port = rets.values @ w
    ew = np.full(n, 1 / n)
    bench = rets.values @ ew
    rf_d = rf_annual / TRADING_DAYS

    s = M.summary(port, rf=rf_d, periods_per_year=TRADING_DAYS)
    b = M.summary(bench, rf=rf_d, periods_per_year=TRADING_DAYS)
    drag = M.volatility_drag(port, TRADING_DAYS)

    # Tarihsel egri (sabit agirlik, gunluk dengeli) + 1/N
    eqp = np.cumprod(1 + port)
    eqb = np.cumprod(1 + bench)
    dates = list(rets.index)
    idx = np.unique(np.linspace(0, len(eqp) - 1, min(200, len(eqp))).astype(int))
    curve = [{"date": dates[i].isoformat(), "port": float(eqp[i]), "bench": float(eqb[i])} for i in idx]

    # VaR / CVaR
    var = {"var95": M.var_historical(port, 0.95), "var99": M.var_historical(port, 0.99),
           "cvar95": M.cvar_historical(port, 0.95), "cvar99": M.cvar_historical(port, 0.99),
           "var99_cf": M.var_cornish_fisher(port, 0.99), "worst_day": float(port.min())}
    var_tl = {k: v * notional for k, v in var.items()}

    # Bilesen risk
    rc = PF.risk_contributions(w, cov_ann)
    comp = sorted(
        ({"ticker": used[i], "sector": sectors[i], "weight": float(w[i]),
          "risk_share": float(rc[i]), "comp_var99_tl": float(rc[i] * var["var99"] * notional)}
         for i in range(n)),
        key=lambda x: x["risk_share"], reverse=True)

    hhi = float(np.sum(w ** 2))
    vols = np.sqrt(np.diag(cov_ann))
    port_vol = float(np.sqrt(w @ cov_ann @ w))

    # Faktor
    factor = {}
    if n >= 2:
        try:
            pc = PF.pca(rets.values, standardize=True)
            factor["pc1_explained"] = float(pc["explained_ratio"][0])
            factor["systematic_share"] = float(PF.capm_regression(port, pc["scores"][:, 0],
                                                                  periods_per_year=TRADING_DAYS)["r2"])
        except Exception:
            pass
    gb = _gold_beta(db, port, rets.index)
    if gb:
        factor["gold_beta"] = gb["beta"]

    # Monte Carlo projeksiyon
    mu_d = mu_ann / TRADING_DAYS
    var_d = np.diag(cov_ann) / TRADING_DAYS
    H = int(horizon_months * 21)
    grid = np.unique(np.linspace(0, H, min(53, H + 1)).astype(int))
    assets = sorted(
        ({"ticker": used[i], "weight": float(w[i]),
          "path": [float(math.exp((mu_d[i] - 0.5 * var_d[i]) * t)) for t in grid]}
         for i in range(n)),
        key=lambda a: a["weight"], reverse=True)
    mp = float(w @ mu_d)
    sp = float(np.sqrt(max(w @ (cov_ann / TRADING_DAYS) @ w, 1e-12)))
    rng = np.random.default_rng(42)
    cum = np.cumprod(1.0 + rng.normal(mp, sp, size=(n_sims, H)), axis=1)
    cum = np.hstack([np.ones((n_sims, 1)), cum])
    mc = {"grid_days": [int(t) for t in grid], "assets": assets, "horizon_months": horizon_months,
          "exp_return_ann": float(w @ mu_ann), "exp_vol_ann": port_vol,
          "portfolio": {"p5": np.percentile(cum[:, grid], 5, axis=0).tolist(),
                        "p50": np.percentile(cum[:, grid], 50, axis=0).tolist(),
                        "p95": np.percentile(cum[:, grid], 95, axis=0).tolist()}}

    return {
        "used": used, "missing": missing, "n_assets": n, "observations": len(rets),
        "notional": notional, "start": dates[0].isoformat(), "end": dates[-1].isoformat(),
        "weights": [{"ticker": used[i], "sector": sectors[i], "weight": float(w[i])} for i in range(n)],
        "metrics": {"cagr": s["cagr"], "ann_vol": s["ann_vol"], "sharpe": s["sharpe"],
                    "sharpe_se": s["sharpe_se"], "psr_vs_0": s["psr_vs_0"], "sortino": s["sortino"],
                    "max_drawdown": s["max_drawdown"], "calmar": s["calmar"],
                    "skew": s["skew"], "excess_kurtosis": s["excess_kurtosis"],
                    "geo_growth": drag["log_growth"], "vol_drag": drag["drag"]},
        "benchmark": {"cagr": b["cagr"], "sharpe": b["sharpe"], "max_drawdown": b["max_drawdown"]},
        "curve": curve,
        "var_pct": var, "var_tl": var_tl, "components": comp,
        "concentration": {"hhi": hhi, "effective_n": 1.0 / hhi if hhi > 0 else None,
                          "diversification_ratio": float((w @ vols) / port_vol) if port_vol > 0 else None},
        "factor": factor,
        "mc": mc,
    }
