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
from db import BistMetric, BistPrice

TRADING_DAYS = 252
METHODS = ("max_sharpe", "min_variance", "risk_parity", "hrp", "equal", "mc_max_return")


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


def _mc_max_return(mu_ann: np.ndarray, sectors: list[str], max_weight: float,
                   sector_caps: dict | None, n_iter: int = 8000) -> np.ndarray:
    """Monte Carlo rastgele arama: kisitlar altinda (long-only, sum=1, poz. tavani,
    sektor tavani) beklenen yillik getiriyi (w·mu) EN YUKSEK yapan agirliklari arar.
    Varliklari ve oranlarini rastgele deneyip en iyisini tutar. Amac dogrusal
    oldugundan optimum ~ en yuksek getirili varliklarin tavana kadar doldurulmasidir;
    bu 'agresif' bir portfoydur (riski ayrica raporlanir)."""
    rng = np.random.default_rng(0)
    n = len(mu_ann)
    sec = np.array(sectors)
    # Tavanin uygulanabilmesi icin en az ceil(1/tavan) hisse gerekir; aksi halde
    # agirliklar tavani asar. k bu tabandan baslar.
    kmin = min(n, max(2, int(np.ceil(1.0 / max_weight))))
    kmax = min(n, kmin + 8)
    best_w, best = None, -np.inf
    for _ in range(n_iter):
        k = int(rng.integers(kmin, kmax + 1)) if kmax > kmin else kmin
        idx = rng.choice(n, size=k, replace=False)
        w = np.zeros(n)
        w[idx] = rng.random(k)
        w = _cap_project(w, max_weight)
        if sector_caps:
            if any(w[sec == s].sum() > cap + 1e-9 for s, cap in sector_caps.items()):
                continue
        obj = float(w @ mu_ann)
        if obj > best:
            best, best_w = obj, w
    return best_w if best_w is not None else _cap_project(np.ones(n), max_weight)


def solve_weights(rets: pd.DataFrame, sectors: list[str], method: str,
                  max_weight: float, sector_cap: float | None, rf_annual: float):
    """Bir getiri matrisinden secilen yontemle agirlik uretir.
    Doner: (w, mu_ann, cov_ann). build() ve backtest ayni mantigi kullanir."""
    n = rets.shape[1]
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
        cols = list(rets.columns)
        base = np.array([(hw["weights"].get(c, 0.0) if hw else 0.0) for c in cols])
        if base.sum() <= 0:
            base = np.full(n, 1 / n)
        w = _cap_project(base, max_weight)
    elif method == "mc_max_return":
        w = _mc_max_return(mu_ann, sectors, max_weight, sector_caps)
    else:
        raise ValueError(f"bilinmeyen yontem: {method}")
    return w, mu_ann, cov_ann


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

    w, mu_ann, cov_ann = solve_weights(rets, sectors, method, max_weight, sector_cap, rf_annual)

    # --- degerlendirme ---
    port = (rets.values @ w)
    rf_p = rf_annual / TRADING_DAYS
    summ = M.summary(port, rf=rf_p, periods_per_year=TRADING_DAYS)
    drag = M.volatility_drag(port, TRADING_DAYS)
    rc = PF.risk_contributions(w, cov_ann)
    eff_n = float(1.0 / np.sum(w ** 2))

    lp = {t: v for t, v in db.execute(
        select(BistMetric.ticker, BistMetric.last_price).where(BistMetric.ticker.in_(cols)))}
    weights = sorted(
        ({"ticker": cols[i], "sector": sectors[i], "weight": float(w[i]),
          "risk_contrib": float(rc[i]), "last_price": lp.get(cols[i])}
         for i in range(n) if w[i] > 1e-4),
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


def project(db, tickers: list[str], sector_map: dict[str, str], *,
            method: str = "max_sharpe", max_assets: int = 50, max_weight: float = 0.10,
            sector_cap: float | None = 0.30, rf_annual: float = 0.0,
            window_years: int = 5, horizon_months: int = 12, n_sims: int = 1000) -> dict:
    """Insa edilen portfoyu ileriye projekte eder. Her VARLIK icin GBM medyan yolu
    (exp((mu-0.5s^2)t)), PORTFOY icin Monte Carlo p5/p50/p95 bandi. Baslangic=1.0.
    Bellek dostu: portfoy gunluk getirisi Normal(mp, sp) olarak simule edilir."""
    rets = returns_matrix(db, tickers[: max_assets * 2], window_years)
    if rets.shape[1] < 2 or len(rets) < 120:
        return {"error": "Projeksiyon için yeterli fiyat geçmişi yok."}
    ordered = [t for t in tickers if t in rets.columns][:max_assets]
    rets = rets[ordered].dropna()
    cols = list(rets.columns)
    n = len(cols)
    sectors = [sector_map.get(c) or "Diğer" for c in cols]
    w, mu_ann, cov_ann = solve_weights(rets, sectors, method, max_weight, sector_cap, rf_annual)

    mu_d = mu_ann / TRADING_DAYS
    var_d = np.diag(cov_ann) / TRADING_DAYS
    H = int(horizon_months * 21)
    grid = np.unique(np.linspace(0, H, min(53, H + 1)).astype(int))

    # Varlik medyan yollari (yalnizca portfoyde yer alanlar)
    assets = []
    for i in range(n):
        if w[i] <= 1e-4:
            continue
        path = [float(np.exp((mu_d[i] - 0.5 * var_d[i]) * t)) for t in grid]
        assets.append({"ticker": cols[i], "weight": float(w[i]), "path": path})
    assets.sort(key=lambda a: a["weight"], reverse=True)

    # Portfoy Monte Carlo (gunluk Normal yaklasimi)
    mp = float(w @ mu_d)
    sp = float(np.sqrt(max(w @ (cov_ann / TRADING_DAYS) @ w, 1e-12)))
    rng = np.random.default_rng(42)
    daily = rng.normal(mp, sp, size=(n_sims, H))
    cum = np.cumprod(1.0 + daily, axis=1)
    cum = np.hstack([np.ones((n_sims, 1)), cum])          # t=0 -> 1.0
    p5 = np.percentile(cum[:, grid], 5, axis=0).tolist()
    p50 = np.percentile(cum[:, grid], 50, axis=0).tolist()
    p95 = np.percentile(cum[:, grid], 95, axis=0).tolist()

    return {
        "method": method, "n_assets": n, "horizon_months": horizon_months,
        "grid_days": [int(t) for t in grid],
        "assets": assets,
        "portfolio": {"p5": p5, "p50": p50, "p95": p95},
        "exp_return_ann": float(w @ mu_ann), "exp_vol_ann": float(np.sqrt(w @ cov_ann @ w)),
    }
