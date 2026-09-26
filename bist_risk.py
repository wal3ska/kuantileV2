"""Quant Lab — Risk Ayristirma: bilesen VaR/CVaR, yogunlasma, faktor maruziyeti.

Insa edilen portfoyu alir; Euler ayristirmasiyla riskin hisse/sektor dagilimini,
tarihsel & Cornish-Fisher VaR/CVaR'i, yogunlasma olculerini ve sistematik (PCA) +
altin faktor maruziyetini raporlar.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select

import qglib.metrics as M
import qglib.portfolio as PF
from advanced_risk import ledoit_wolf_cov
from bist_portfolio import TRADING_DAYS, returns_matrix, solve_weights
from db import BistPrice

NOTIONAL = 1_000_000.0


def _gold_beta(db, port: np.ndarray, dates) -> dict | None:
    """Portfoyun altin (XAUTRY) faktorune betasi (ortak tarihlerde)."""
    rows = db.execute(
        select(BistPrice.d, BistPrice.close).where(BistPrice.ticker == "XAUTRY")
    ).all()
    if len(rows) < 60:
        return None
    g = pd.Series({d: c for d, c in rows}).sort_index().pct_change().dropna()
    pr = pd.Series(port, index=pd.to_datetime(list(dates)))
    g.index = pd.to_datetime(g.index)
    j = pd.concat([pr.rename("p"), g.rename("g")], axis=1).dropna()
    if len(j) < 60:
        return None
    r = PF.capm_regression(j["p"].values, j["g"].values, periods_per_year=TRADING_DAYS)
    return {"beta": r["beta"], "r2": r["r2"]}


def risk_report(db, tickers: list[str], sector_map: dict[str, str], *,
                method: str = "max_sharpe", max_assets: int = 50, max_weight: float = 0.10,
                sector_cap: float | None = 0.30, rf_annual: float = 0.0,
                window_years: int = 5) -> dict:
    rets = returns_matrix(db, tickers[: max_assets * 2], window_years)
    if rets.shape[1] < 2 or len(rets) < 120:
        return {"error": "Risk analizi için yeterli fiyat geçmişi yok."}
    ordered = [t for t in tickers if t in rets.columns][:max_assets]
    rets = rets[ordered].dropna()
    cols = list(rets.columns)
    n = len(cols)
    sectors = [sector_map.get(c) or "Diğer" for c in cols]
    w, mu_ann, cov_ann = solve_weights(rets, sectors, method, max_weight, sector_cap, rf_annual)

    port = rets.values @ w
    # VaR / CVaR (gunluk, pozitif kayip; %95 ve %99)
    var = {
        "var95": M.var_historical(port, 0.95), "var99": M.var_historical(port, 0.99),
        "cvar95": M.cvar_historical(port, 0.95), "cvar99": M.cvar_historical(port, 0.99),
        "var99_cf": M.var_cornish_fisher(port, 0.99),
        "worst_day": float(port.min()),
    }
    var_tl = {k: v * NOTIONAL for k, v in var.items()}

    # Bilesen risk (Euler varyans paylari) -> bilesen VaR (rc * VaR99)
    rc = PF.risk_contributions(w, cov_ann)          # toplami 1
    comp = sorted(
        ({"ticker": cols[i], "sector": sectors[i], "weight": float(w[i]),
          "risk_share": float(rc[i]), "comp_var99_tl": float(rc[i] * var["var99"] * NOTIONAL)}
         for i in range(n) if w[i] > 1e-4),
        key=lambda x: x["risk_share"], reverse=True,
    )
    sec_risk: dict[str, float] = {}
    for i in range(n):
        sec_risk[sectors[i]] = sec_risk.get(sectors[i], 0.0) + float(rc[i])
    sector_risk = sorted(({"sector": k, "risk_share": v} for k, v in sec_risk.items()),
                         key=lambda x: x["risk_share"], reverse=True)

    # Yogunlasma
    hhi = float(np.sum(w ** 2))
    vols = np.sqrt(np.diag(cov_ann))
    port_vol = float(np.sqrt(w @ cov_ann @ w))
    div_ratio = float((w @ vols) / port_vol) if port_vol > 0 else None

    # Faktor: PCA sistematik pay + altin betasi
    factor = {}
    try:
        pc = PF.pca(rets.values, standardize=True)
        factor["pc1_explained"] = float(pc["explained_ratio"][0])
        reg = PF.capm_regression(port, pc["scores"][:, 0], periods_per_year=TRADING_DAYS)
        factor["systematic_share"] = float(reg["r2"])   # portfoyun PC1 ile aciklanan varyansi
    except Exception:
        pass
    gb = _gold_beta(db, port, rets.index)
    if gb:
        factor["gold_beta"] = gb["beta"]
        factor["gold_r2"] = gb["r2"]

    return {
        "method": method, "n_assets": n, "observations": len(rets),
        "notional": NOTIONAL,
        "var_pct": var, "var_tl": var_tl,
        "components": comp, "sector_risk": sector_risk,
        "concentration": {"hhi": hhi, "effective_n": 1.0 / hhi if hhi > 0 else None,
                          "diversification_ratio": div_ratio,
                          "port_vol_ann": port_vol * np.sqrt(TRADING_DAYS)},
        "tail": {"skew": M.summary(port)["skew"], "excess_kurtosis": M.summary(port)["excess_kurtosis"]},
        "factor": factor,
    }
