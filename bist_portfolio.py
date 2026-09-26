"""Quant Lab Faz 2 — portfoy insasi.

Uygun (elenmis) evren uzerinde farkli yontemlerle agirlik uretir ve portfoyu
degerlendirir. qglib (Quant Guild) + advanced_risk'in Ledoit-Wolf kovaryansi ve
HRP'si yeniden kullanilir.

Onemli (qg-portfolio-risk dersleri): orneklem-ortalamali max-Sharpe (tangency)
girdi gurultusune asiri duyarlidir; bu yuzden LW shrinkage + long-only + pozisyon
ve sektor tavanlari uygulanir, ve daha kararli alternatifler (min-var, risk-parity,
HRP) da sunulur. Getiriler her zaman belirsizligiyle raporlanir (Sharpe SE, PSR).

Bellek notu: online istekte tum evren degil, likiditeye gore secilen `max_assets`
(varsayilan 50) hisse optimize edilir — hem 350MB api limiti hem de asiri-uyum icin.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sqlalchemy import select

import qglib.metrics as M
import qglib.portfolio as PF
from advanced_risk import hrp_weights, ledoit_wolf_cov
from db import BistPrice

TRADING_DAYS = 252
METHODS = ("max_sharpe", "min_variance", "risk_parity", "hrp", "equal")


def returns_matrix(db, tickers: list[str], window_years: int = 5) -> pd.DataFrame:
    """tickers icin gunluk basit getiri matrisi (ortak tarihlerde hizalanmis)."""
    start = date.today() - timedelta(days=int(window_years * 365.25))
    rows = db.execute(
        select(BistPrice.ticker, BistPrice.d, BistPrice.close)
        .where(BistPrice.ticker.in_(tickers), BistPrice.d >= start)
    ).all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["ticker", "d", "close"])
    wide = df.pivot(index="d", columns="ticker", values="close").sort_index()
    rets = wide.pct_change()
    # Yeterli gecmisi olmayan kolonlari at, sonra ortak tarihlerde hizala
    keep = rets.columns[rets.notna().sum() >= int(0.8 * len(rets))]
    rets = rets[keep].dropna()
    return rets


def _cap_project(w: np.ndarray, max_w: float, iters: int = 100) -> np.ndarray:
    """Long-only + sum=1 koruyarak agirliklari max_w'ye kirp (ERC/HRP sonrasi)."""
    w = np.clip(np.asarray(w, float), 0, None)
    if w.sum() <= 0:
        return np.full(len(w), 1 / len(w))
    w = w / w.sum()
    if max_w >= 1:
        return w
    for _ in range(iters):
        over = w > max_w + 1e-12
        if not over.any():
            break
        excess = (w[over] - max_w).sum()
        w[over] = max_w
        under = ~over
        if w[under].sum() <= 0:
            break
        w[under] += excess * w[under] / w[under].sum()
    return w / w.sum()


def _constrained(obj, n: int, max_w: float, sectors=None, sector_caps=None) -> np.ndarray:
    """SLSQP: long-only, sum=1, per-asset <= max_w, opsiyonel sektor tavanlari."""
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    if sectors and sector_caps:
        for sec, cap in sector_caps.items():
            idx = [i for i, s in enumerate(sectors) if s == sec]
            if idx:
                cons.append({"type": "ineq",
                             "fun": lambda w, idx=idx, cap=cap: cap - w[idx].sum()})
    bounds = [(0.0, max_w)] * n
    res = minimize(obj, np.full(n, 1 / n), bounds=bounds, constraints=cons,
                   method="SLSQP", options={"maxiter": 500, "ftol": 1e-10})
    w = np.clip(res.x, 0, None)
    return w / w.sum() if w.sum() > 0 else np.full(n, 1 / n)


def build(db, tickers: list[str], sector_map: dict[str, str], *,
          method: str = "max_sharpe", max_assets: int = 50, max_weight: float = 0.10,
          sector_cap: float | None = None, rf_annual: float = 0.0,
          window_years: int = 5) -> dict:
    if method not in METHODS:
        raise ValueError(f"bilinmeyen yontem: {method}")

    rets = returns_matrix(db, tickers[: max_assets * 2], window_years)
    if rets.shape[1] < 2 or len(rets) < 120:
        return {"error": "Yeterli fiyat gecmisi yok (en az 2 hisse, 120 gun)."}

    # Likiditeye gore verilen sirayi koru; ortak-tarih matrisinden ilk max_assets
    ordered = [t for t in tickers if t in rets.columns][:max_assets]
    rets = rets[ordered].dropna()
    cols = list(rets.columns)
    n = len(cols)
    sectors = [sector_map.get(c) or "Diğer" for c in cols]

    mu_ann = rets.mean().values * TRADING_DAYS
    cov_ann = ledoit_wolf_cov(rets) * TRADING_DAYS
    sector_caps = None
    if sector_cap is not None and sector_cap < 1:
        sector_caps = {s: sector_cap for s in set(sectors)}

    if method == "equal":
        w = np.full(n, 1 / n)
    elif method == "min_variance":
        w = _constrained(lambda w: w @ cov_ann @ w, n, max_weight, sectors, sector_caps)
    elif method == "max_sharpe":
        def neg_sharpe(w):
            v = np.sqrt(w @ cov_ann @ w)
            return -(w @ mu_ann - rf_annual) / v if v > 0 else 0.0
        w = _constrained(neg_sharpe, n, max_weight, sectors, sector_caps)
    elif method == "risk_parity":
        w = _cap_project(PF.risk_parity_weights(cov_ann), max_weight)
    elif method == "hrp":
        hw = hrp_weights(rets)
        base = np.array([(hw["weights"].get(c, 0.0) if hw else 0.0) for c in cols])
        if base.sum() <= 0:
            base = np.full(n, 1 / n)
        w = _cap_project(base, max_weight)

    # --- degerlendirme ---
    port = (rets.values @ w)
    rf_p = rf_annual / TRADING_DAYS
    summ = M.summary(port, rf=rf_p, periods_per_year=TRADING_DAYS)
    drag = M.volatility_drag(port, TRADING_DAYS)
    rc = PF.risk_contributions(w, cov_ann)
    eff_n = float(1.0 / np.sum(w ** 2))

    weights = sorted(
        ({"ticker": cols[i], "sector": sectors[i], "weight": float(w[i]),
          "risk_contrib": float(rc[i])} for i in range(n) if w[i] > 1e-4),
        key=lambda x: x["weight"], reverse=True,
    )
    sec_alloc: dict[str, float] = {}
    for i in range(n):
        sec_alloc[sectors[i]] = sec_alloc.get(sectors[i], 0.0) + float(w[i])
    sectors_out = sorted(({"sector": k, "weight": v} for k, v in sec_alloc.items()),
                         key=lambda x: x["weight"], reverse=True)

    # etkin sinir (max-Sharpe/min-var icin anlamli); hafif tut
    frontier = None
    if method in ("max_sharpe", "min_variance") and n <= 60:
        try:
            vols, frets, _ = PF.efficient_frontier(mu_ann, cov_ann, n_points=22, long_only=True)
            frontier = [{"vol": float(v), "ret": float(r)} for v, r in zip(vols, frets)]
        except Exception:
            frontier = None

    return {
        "method": method, "n_assets": n, "observations": len(rets),
        "as_of": rets.index[-1].isoformat() if len(rets) else None,
        "weights": weights,
        "sectors": sectors_out,
        "effective_n": eff_n,
        "metrics": {
            "cagr": summ["cagr"], "ann_vol": summ["ann_vol"], "sharpe": summ["sharpe"],
            "sharpe_se": summ["sharpe_se"], "psr_vs_0": summ["psr_vs_0"],
            "sortino": summ["sortino"], "max_drawdown": summ["max_drawdown"],
            "calmar": summ["calmar"], "skew": summ["skew"],
            "excess_kurtosis": summ["excess_kurtosis"],
            "geo_growth": drag["log_growth"], "vol_drag": drag["drag"],
        },
        "port_point": {"vol": float(np.sqrt(w @ cov_ann @ w)), "ret": float(w @ mu_ann)},
        "frontier": frontier,
    }
