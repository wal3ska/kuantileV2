"""Saf hesaplama motoru. UI ve veri kaynagindan tamamen bagimsiz:
DataFrame/dict alir, sayi/dict doner. Hem Streamlit hem FastAPI bunu kullanir."""

import numpy as np
import pandas as pd

CRASH_SCENARIOS = {
    "2008 Küresel Finans Krizi (Lehman)": {"start": "2008-09-12", "end": "2009-03-09", "region": "Uluslararası"},
    "2010-11 Avrupa Borç Krizi": {"start": "2011-07-01", "end": "2011-10-04", "region": "Uluslararası"},
    "2013 Fed Taper Tantrum": {"start": "2013-05-22", "end": "2013-06-24", "region": "Uluslararası"},
    "2015 Çin Devalüasyon Şoku": {"start": "2015-08-10", "end": "2015-08-25", "region": "Uluslararası"},
    "2018 Rahip Brunson Krizi": {"start": "2018-01-01", "end": "2018-08-31", "region": "Türkiye"},
    "2018 Q4 Fed Sıkılaşma Satışı": {"start": "2018-10-01", "end": "2018-12-24", "region": "Uluslararası"},
    "2020 Covid-19 Çöküşü": {"start": "2020-02-20", "end": "2020-03-23", "region": "Uluslararası"},
    "2021 KKM Döviz Krizi": {"start": "2021-11-18", "end": "2021-12-20", "region": "Türkiye"},
    "2022 Fed Faiz Şoku & Ayı Piyasası": {"start": "2022-01-03", "end": "2022-10-12", "region": "Uluslararası"},
    "2022 Kripto Kışı (LUNA/FTX)": {"start": "2022-04-01", "end": "2022-11-21", "region": "Uluslararası"},
    "2023 SVB Bankacılık Krizi": {"start": "2023-03-08", "end": "2023-03-24", "region": "Uluslararası"},
    "2023 Seçim Sonrası TL Ayarlaması": {"start": "2023-05-26", "end": "2023-06-23", "region": "Türkiye"},
    "2024 Yen Carry Trade Çöküşü": {"start": "2024-07-31", "end": "2024-08-05", "region": "Uluslararası"},
    "2025 Nisan Tarife Şoku": {"start": "2025-04-02", "end": "2025-04-08", "region": "Uluslararası"},
}

RATE_SHOCKS_BPS = [-100, 100, 300, 500]


def clean_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """Sifir/negatif fiyatlari veri hatasi sayip NaN'a cevirir."""
    return prices.where(prices > 0)


def log_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Ortak islem gunleri uzerinden logaritmik gunluk getiriler (inf temiz)."""
    common = clean_prices(prices).dropna()
    rets = np.log(common / common.shift(1))
    return rets.replace([np.inf, -np.inf], np.nan).dropna()


def portfolio_weights(investments: dict, names) -> np.ndarray:
    total = sum(investments[n] for n in names)
    if total <= 0:
        raise ValueError("Toplam yatırım tutarı pozitif olmalı.")
    return np.array([investments[n] / total for n in names])


def portfolio_returns(returns: pd.DataFrame, investments: dict) -> pd.Series:
    w = portfolio_weights(investments, returns.columns)
    return returns.dot(w)


def historical_var(port_returns: pd.Series, confidence: float = 0.99) -> float:
    """Tarihsel Simulasyon VaR: getiri dagiliminin (1-güven) yüzdeliği. Negatif döner."""
    if len(port_returns) == 0:
        raise ValueError("Getiri serisi boş.")
    return float(np.percentile(port_returns, (1 - confidence) * 100))


def diversification(returns: pd.DataFrame, investments: dict, confidence: float = 0.99) -> dict:
    port_var_pct = historical_var(portfolio_returns(returns, investments), confidence)
    total = sum(investments[n] for n in returns.columns)
    individual = sum(
        investments[n] * historical_var(returns[n], confidence) for n in returns.columns
    )
    portfolio_tl = total * port_var_pct
    return {
        "sum_individual_var": individual,
        "portfolio_var": portfolio_tl,
        "benefit": abs(individual) - abs(portfolio_tl),
    }


def correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    return returns.corr()


def stress_test(prices: pd.DataFrame, investments: dict, start: str, end: str) -> dict | None:
    """Senaryo penceresindeki gerceklesen getirileri mevcut agirliklara uygular."""
    mask = (prices.index >= pd.to_datetime(start)) & (prices.index <= pd.to_datetime(end))
    window = clean_prices(prices.loc[mask]).dropna(axis=1, how="all")
    if window.empty or window.shape[1] == 0:
        return None
    rets = np.log(window / window.shift(1)).replace([np.inf, -np.inf], np.nan).dropna()
    if rets.empty:
        return None
    active = rets.columns.tolist()
    w = portfolio_weights(investments, active)
    cum = float(np.exp(rets.dot(w).sum()) - 1)
    return {
        "active_assets": active,
        "missing_assets": [n for n in prices.columns if n not in active],
        "cumulative_return": cum,
    }


def run_stress_tests(prices: pd.DataFrame, investments: dict,
                     scenarios: dict = CRASH_SCENARIOS, regions=None) -> dict:
    out = {}
    for name, sc in scenarios.items():
        if regions and sc["region"] not in regions:
            continue
        res = stress_test(prices, investments, sc["start"], sc["end"])
        out[name] = {**sc, "result": res}
    return out


def bond_metrics(coupon_rate: float, ytm: float, years: float, freq: int) -> tuple:
    """Kupon akislarinin bugunku degerinden fiyat, Macaulay ve Modified Duration.
    coupon_rate/ytm ondalik (0.40 = %40). 100 nominal bazinda."""
    n = max(int(round(years * freq)), 1)
    c = coupon_rate / freq * 100
    y = ytm / freq
    periods = np.arange(1, n + 1)
    times = periods / freq
    cfs = np.full(n, c, dtype=float)
    cfs[-1] += 100.0
    pv = cfs * (1 + y) ** (-periods)
    fair_price = float(pv.sum())
    macaulay = float((times * pv).sum() / fair_price)
    modified = macaulay / (1 + y)
    return fair_price, macaulay, modified


def bond_risk_summary(bonds: list, total_portfolio_value: float | None = None) -> dict:
    """bonds: [{'name','value_try','modified',...}] -> sepet duzeyinde durasyon ozeti."""
    basket = sum(b["value_try"] for b in bonds)
    if basket <= 0:
        raise ValueError("Tahvil sepeti değeri pozitif olmalı.")
    w_mod = sum(b["modified"] * b["value_try"] for b in bonds) / basket
    dv01 = sum(b["modified"] * b["value_try"] * 1e-4 for b in bonds)
    shocks = {bps: -w_mod * (bps / 1e4) * basket for bps in RATE_SHOCKS_BPS}
    out = {"basket_value": basket, "weighted_modified_duration": w_mod,
           "total_dv01": dv01, "rate_shocks": shocks}
    if total_portfolio_value and total_portfolio_value > 0:
        out["portfolio_duration_contribution"] = w_mod * basket / total_portfolio_value
    return out


def position_pnl(quantity: float, last_price: float, cost: float | None, fx: float = 1.0) -> dict:
    """Tek pozisyonun kendi para biriminde ve TL'de degerleme sonucu."""
    value = quantity * last_price
    if cost is None or cost <= 0:
        cost_total = pnl = pnl_pct = None
    else:
        cost_total = quantity * cost
        pnl = value - cost_total
        pnl_pct = pnl / cost_total * 100
    return {
        "value": value, "cost_total": cost_total, "pnl": pnl, "pnl_pct": pnl_pct,
        "value_try": value * fx,
        "pnl_try": pnl * fx if pnl is not None else None,
    }
