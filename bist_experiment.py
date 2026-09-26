"""Quant Lab — "Deney": kisit hiperparametre taramasi.

(max_assets × poz.tavani × sektor tavani × yontem) izgarasini rf=%35'te tarar;
gunluk VaR%99 > var_limit olanlari eler; hayatta kalanlari once ucuz (in-sample
Sharpe) siralar, en iyi K adayda TAM walk-forward OOS backtest + Monte Carlo
projeksiyon calistirip en yuksek OOS Sharpe'li portfoyu (tum agirliklariyla) doner.

Iki asama, cunku her kombinasyonda backtest cok pahali olurdu (1GB + istek timeout).
"""

import numpy as np

import qglib.metrics as M
from advanced_risk import hrp_weights
from bist_portfolio import TRADING_DAYS, _cap_project, returns_matrix

# Tarama izgarasi (makul ve sinirli tutuldu)
ASSETS_GRID = [20, 30, 40, 50]
WEIGHT_GRID = [0.10, 0.15, 0.20, 0.25]
SECTOR_GRID = [0.30, 0.50, None]          # None = sektor tavani yok
METHODS = ["max_sharpe", "min_variance", "risk_parity", "hrp"]  # Sharpe hedefli (mc_max_return haric)


def _sector_cap_project(w: np.ndarray, sec: np.ndarray, sc: float, mw: float) -> np.ndarray:
    """Hizli heuristik: sektor toplamini sc'ye kirp, fazlayi tavani dolmamis
    sektorlerdeki bos kapasiteye dagit. (Stage-1 elemesi icin yaklasik.)"""
    w = w.copy()
    for _ in range(30):
        over = [s for s in np.unique(sec) if w[sec == s].sum() > sc + 1e-9]
        if not over:
            break
        for s in over:
            idx = sec == s
            tot = w[idx].sum()
            if tot > 0:
                w[idx] *= sc / tot
        deficit = 1.0 - w.sum()
        if deficit <= 1e-9:
            break
        under = np.array([w[sec == sec[i]].sum() < sc - 1e-9 for i in range(len(w))])
        room = np.where(under, np.maximum(mw - w, 0.0), 0.0)
        if room.sum() <= 0:
            break
        w += deficit * room / room.sum()
    s = w.sum()
    return w / s if s > 0 else w


def _fast_weights(method: str, mu_ann, cov_ann, rets, sec, mw: float,
                  sc: float | None, rf: float) -> np.ndarray:
    """SLSQP'siz hizli yaklasik agirlik (yalnizca eleme/siralama icin). Stage-2
    en iyi adaylari solve_weights ile TAM cozer."""
    n = len(mu_ann)
    if method == "max_sharpe":
        raw = np.linalg.solve(cov_ann, mu_ann - rf)
    elif method == "min_variance":
        raw = np.linalg.solve(cov_ann, np.ones(n))
    elif method == "risk_parity":
        raw = 1.0 / np.sqrt(np.maximum(np.diag(cov_ann), 1e-12))   # ters-vol proxy
    else:  # hrp
        hw = hrp_weights(rets)
        cols = list(rets.columns)
        raw = np.array([(hw["weights"].get(c, 0.0) if hw else 0.0) for c in cols])
    raw = np.clip(raw, 0, None)
    if raw.sum() <= 0:
        raw = np.ones(n)
    w = _cap_project(raw / raw.sum(), mw)
    if sc is not None and sc < 1:
        w = _sector_cap_project(w, sec, sc, mw)
    return w


def run_experiment(db, tickers: list[str], sector_map: dict[str, str], *,
                   rf_annual: float = 0.35, var_limit: float = 0.03,
                   window_years: int = 5, train_years: float = 2.0, test_months: int = 3,
                   horizon_months: int = 9, top_k: int = 3) -> dict:
    kmax = max(ASSETS_GRID)
    rets_full = returns_matrix(db, tickers[: kmax * 2], window_years)
    if rets_full.shape[1] < 5 or len(rets_full) < 300:
        return {"error": "Deney için yeterli fiyat geçmişi yok."}
    ordered = [t for t in tickers if t in rets_full.columns][:kmax]
    rets_full = rets_full[ordered].dropna()
    cols_all = list(rets_full.columns)
    sectors_all = [sector_map.get(c) or "Diğer" for c in cols_all]
    rf_d = rf_annual / TRADING_DAYS

    # --- Asama 1: ucuz eleme (in-sample) ---
    total = 0
    var_elim = 0
    min_var = float("inf")
    survivors = []
    from advanced_risk import ledoit_wolf_cov
    for k in ASSETS_GRID:
        if k > len(cols_all):
            continue
        sub = rets_full.iloc[:, :k]
        cols = cols_all[:k]
        secs = sectors_all[:k]
        sec_arr = np.array(secs)
        mu_k = sub.mean().values * TRADING_DAYS
        cov_k = ledoit_wolf_cov(sub) * TRADING_DAYS
        subvals = sub.values
        for mw in WEIGHT_GRID:
            if k * mw < 1.0:            # tavanla toplam 1'e ulasilamaz -> atla
                continue
            for sc in SECTOR_GRID:
                for method in METHODS:
                    total += 1
                    try:
                        w = _fast_weights(method, mu_k, cov_k, sub, sec_arr, mw, sc, rf_annual)
                    except Exception:
                        continue
                    port = subvals @ w
                    var99 = M.var_historical(port, 0.99)
                    min_var = min(min_var, var99)
                    if var99 > var_limit:
                        var_elim += 1
                        continue
                    sr = M.sharpe(port, rf=rf_d, periods_per_year=TRADING_DAYS)
                    if not np.isfinite(sr):
                        continue
                    survivors.append({
                        "method": method, "max_assets": k, "max_weight": mw,
                        "sector_cap": sc, "in_sample_sharpe": float(sr), "var99": float(var99),
                        "weights": [{"ticker": cols[i], "sector": secs[i], "weight": float(w[i])}
                                    for i in range(k) if w[i] > 1e-4],
                    })

    if not survivors:
        mv = min_var * 100 if np.isfinite(min_var) else None
        msg = f"VaR%99 ≤ %{var_limit*100:.1f} koşulunu geçen kombinasyon yok."
        if mv is not None:
            msg += f" Bu evrende en düşük VaR%99 ≈ %{mv:.1f}; eşiği en az oraya çekin."
        return {"error": msg, "total": total, "var_eliminated": var_elim}

    survivors.sort(key=lambda s: s["in_sample_sharpe"], reverse=True)

    # --- Asama 2: en iyi K adayda TAM OOS backtest + MC ---
    import bist_backtest as BT
    import bist_portfolio as PF

    evaluated = []
    for cand in survivors[:top_k]:
        bt = BT.run_backtest(db, tickers, sector_map, method=cand["method"],
                             max_assets=cand["max_assets"], max_weight=cand["max_weight"],
                             sector_cap=cand["sector_cap"], rf_annual=rf_annual,
                             window_years=window_years, train_years=train_years,
                             test_months=test_months)
        if "error" in bt:
            continue
        rec = dict(cand)
        rec["oos_sharpe"] = bt["metrics"]["sharpe"]
        rec["oos_cagr"] = bt["metrics"]["cagr"]
        rec["oos_max_drawdown"] = bt["metrics"]["max_drawdown"]
        rec["real_cagr"] = bt["real"]["real_cagr"] if bt.get("real") else None
        rec["_bt"] = bt
        evaluated.append(rec)

    if not evaluated:
        return {"error": "Adaylarda OOS backtest üretilemedi.", "total": total,
                "var_eliminated": var_elim, "survivors": len(survivors)}

    evaluated.sort(key=lambda r: (r["oos_sharpe"] if r["oos_sharpe"] is not None else -1), reverse=True)
    best = evaluated[0]
    bt = best.pop("_bt")

    # En iyi kombinasyonda Monte Carlo projeksiyon (ozet)
    mc = PF.project(db, tickers, sector_map, method=best["method"],
                    max_assets=best["max_assets"], max_weight=best["max_weight"],
                    sector_cap=best["sector_cap"], rf_annual=rf_annual,
                    window_years=window_years, horizon_months=horizon_months)
    mc_summary = None
    if "error" not in mc:
        p = mc["portfolio"]
        mc_summary = {"exp_return_ann": mc["exp_return_ann"], "exp_vol_ann": mc["exp_vol_ann"],
                      "horizon_months": mc["horizon_months"],
                      "p5_end": p["p5"][-1], "p50_end": p["p50"][-1], "p95_end": p["p95"][-1]}

    # digerleri icin _bt at
    for r in evaluated:
        r.pop("_bt", None)

    return {
        "rf_annual": rf_annual, "var_limit": var_limit,
        "grid": {"assets": ASSETS_GRID, "weights": WEIGHT_GRID,
                 "sectors": [s if s is not None else 0 for s in SECTOR_GRID], "methods": METHODS},
        "total": total, "var_eliminated": var_elim, "survivors": len(survivors),
        "best": {
            "method": best["method"], "max_assets": best["max_assets"],
            "max_weight": best["max_weight"], "sector_cap": best["sector_cap"],
            "in_sample_sharpe": best["in_sample_sharpe"], "var99": best["var99"],
            "oos_sharpe": best["oos_sharpe"], "oos_cagr": best["oos_cagr"],
            "oos_max_drawdown": best["oos_max_drawdown"], "real_cagr": best["real_cagr"],
            "weights": best["weights"],
            "backtest": {"start": bt["start"], "end": bt["end"], "rebalances": bt["rebalances"],
                         "benchmark": bt["benchmark"], "curve": bt["curve"]},
            "mc": mc_summary,
        },
        "top": [{"method": r["method"], "max_assets": r["max_assets"], "max_weight": r["max_weight"],
                 "sector_cap": r["sector_cap"], "in_sample_sharpe": r["in_sample_sharpe"],
                 "var99": r["var99"], "oos_sharpe": r["oos_sharpe"], "oos_cagr": r["oos_cagr"]}
                for r in evaluated],
    }
