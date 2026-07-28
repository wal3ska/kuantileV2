"""FastAPI backend. Calistirma: uvicorn api:app --host 0.0.0.0 --port 8000
Dokumantasyon otomatik: http://localhost:8000/docs"""

import math
import os
from datetime import date
from typing import Literal, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import advanced_risk as adv
import data_provider as dp
import risk_engine as engine
from auth import router as auth_router
from db import init_db
from portfolio_routes import router as portfolio_router

app = FastAPI(
    title="Portföy & Risk Terminali API",
    description="Çoklu varlık portföyleri için TL bazlı değerleme, VaR, durasyon ve stres testi motoru. Yatırım danışmanlığı değildir.",
    version="1.1.0",
)

app.include_router(auth_router)
app.include_router(portfolio_router)


@app.on_event("startup")
def _startup():
    init_db()


class Position(BaseModel):
    name: str
    ticker: str = Field(description="Yahoo sembolü (THYAO.IS, AAPL, BTC-USD) veya TEFAS fon kodu")
    currency: Literal["TRY", "USD"]
    source: Literal["yahoo", "tefas"] = "yahoo"
    quantity: float = Field(gt=0)
    cost: Optional[float] = Field(default=None, description="Birim maliyet (kendi para biriminde). Bilinmiyorsa boş bırakın.")


class Bond(BaseModel):
    name: str
    currency: Literal["TRY", "USD"]
    nominal: float = Field(gt=0)
    price: float = Field(gt=0, description="Güncel piyasa fiyatı, 100 nominal başına")
    coupon_rate: float = Field(ge=0, description="Yıllık kupon, ondalık (0.35 = %35)")
    frequency: int = Field(default=2, description="Yılda kupon sayısı")
    years: float = Field(gt=0, description="Vadeye kalan yıl")
    ytm: float = Field(gt=0, description="Vadeye kadar getiri, ondalık")
    cost: Optional[float] = Field(default=None, description="Alış fiyatı, 100 nominal başına")


class RiskFree(BaseModel):
    """Sharpe kiyasi. rate: kullanicinin girdigi sabit yillik oran;
    deposit/tlref: EVDS tarihsel faiz serisi (annual_rate yedek deger);
    usd/eur: kur getirisi."""
    kind: Literal["rate", "deposit", "tlref", "usd", "eur"] = "rate"
    annual_rate: float = Field(default=0.40, ge=0, le=3.0)


class AnalyzeRequest(BaseModel):
    positions: list[Position] = []
    bonds: list[Bond] = []
    confidence: float = Field(default=0.99, gt=0.5, lt=1.0)
    stress_regions: Optional[list[str]] = None
    risk_free: Optional[RiskFree] = None


class BondDurationRequest(BaseModel):
    coupon_rate: float = Field(ge=0)
    ytm: float = Field(gt=0)
    years: float = Field(gt=0)
    frequency: int = 2


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/rates")
def rates():
    """Guncel TCMB mevduat faizi (Sharpe kiyasi icin otomatik doldurma)."""
    try:
        return dp.fetch_deposit_rate()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


@app.post("/bond/duration")
def bond_duration(req: BondDurationRequest):
    fair, mac, mod = engine.bond_metrics(req.coupon_rate, req.ytm, req.years, req.frequency)
    return {"fair_price": fair, "macaulay_duration": mac, "modified_duration": mod,
            "dv01_per_100_nominal": mod * fair * 1e-4}


class ContactRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=200)
    message: str = Field(min_length=10, max_length=4000)


@app.post("/contact")
def contact(req: ContactRequest):
    """Iletisim formu: mesaji site sahibine e-postayla iletir."""
    import html as html_mod

    import email_service
    to = os.getenv("CONTACT_TO", "anilserdar.unal20@gmail.com")
    body = (f"<p><b>Gönderen:</b> {html_mod.escape(req.name)} "
            f"&lt;{html_mod.escape(req.email)}&gt;</p>"
            f"<p style='white-space:pre-wrap'>{html_mod.escape(req.message)}</p>")
    try:
        email_service.send_email(to, f"Kuantile iletişim formu: {req.name[:60]}", body)
    except Exception:
        raise HTTPException(502, "Mesaj iletilemedi, lütfen daha sonra tekrar deneyin.")
    return {"message": "ok"}


class SimulateRequest(BaseModel):
    positions: list[Position]
    start: date
    end: date


@app.post("/portfolio/simulate")
def simulate(req: SimulateRequest):
    """Ozel tarih araliginda, mevcut agirliklarla portfoyun gidisati.
    Stres testleriyle ayni mantik: pencere getirileri bugunku degere uygulanir."""
    if not req.positions:
        raise HTTPException(400, "En az bir pozisyon gerekli.")
    if req.start >= req.end:
        raise HTTPException(400, "Başlangıç tarihi bitişten önce olmalı.")
    if req.end > date.today():
        raise HTTPException(400, "Bitiş tarihi gelecekte olamaz.")

    try:
        prices_try, fx_now, last_native, failed = dp.build_try_prices(
            [p.model_dump() for p in req.positions]
        )
    except RuntimeError as exc:
        raise HTTPException(503, f"Veri kaynağı hatası: {exc}")

    investments = {}
    for p in req.positions:
        if p.name not in last_native:
            continue
        fx = fx_now if p.currency == "USD" else 1.0
        investments[p.name] = p.quantity * last_native[p.name] * fx
    valid = [n for n in investments if n in prices_try.columns]
    if not valid:
        raise HTTPException(400, "Hiçbir varlık için fiyat verisi bulunamadı.")

    res = engine.stress_test(prices_try[valid], investments,
                             str(req.start), str(req.end))
    if res is None:
        raise HTTPException(400, "Seçilen aralıkta yeterli fiyat verisi yok.")

    # Deger serisi: pencere getirileri, kapsanan varliklarin bugunku degerine uygulanir
    mask = (prices_try.index >= np.datetime64(req.start)) & (prices_try.index <= np.datetime64(req.end))
    window = engine.clean_prices(prices_try.loc[mask, res["active_assets"]]).dropna()
    rets = np.log(window / window.shift(1)).replace([np.inf, -np.inf], np.nan).dropna()
    w = engine.portfolio_weights(investments, res["active_assets"])
    base_value = sum(investments[n] for n in res["active_assets"])
    cum = np.exp(rets.dot(w).cumsum())
    series = [{"date": str(window.index[0].date()), "value": base_value}] + [
        {"date": str(ts.date()), "value": float(base_value * v)} for ts, v in cum.items()
    ]
    if len(series) > 300:  # grafik icin seyrelt (son nokta korunur)
        step = len(series) // 300 + 1
        series = series[::step] + [series[-1]]

    return {
        "start": str(req.start),
        "end": str(req.end),
        "cumulative_return": res["cumulative_return"],
        "impact_try": base_value * res["cumulative_return"],
        "base_value_try": base_value,
        "final_value_try": series[-1]["value"],
        "missing_assets": res["missing_assets"] + failed,
        "series": series,
    }


FACTOR_TICKERS = ("XU100.IS", "GC=F", "TRY=X", "^GSPC")
FACTOR_LABELS = {"XU100.IS": "BIST 100", "GOLDTL": "Altın (TL)",
                 "TRY=X": "USD/TRY", "SP500TL": "S&P 500 (TL)", "CASH": "Nakit/Mevduat"}


def _advanced_block(req, positions, returns, port_rets, investments, valid,
                    market_value, var_pct, prices_try, last_native, fx_now):
    """Gelismis metrikler: her biri bagimsiz try/except ile hesaplanir,
    veri/kaynak sorunu analizin geri kalanini asla bloklamaz."""
    out = {}

    def _safe(key, fn):
        try:
            out[key] = fn()
        except Exception:
            out[key] = None

    conf = req.confidence
    # Mevduat/risksiz oran: belirsizlik metrikleri (PSR, mevduati yenme) icin
    dep_annual = None
    if req.risk_free is not None and req.risk_free.kind in ("rate", "deposit", "tlref"):
        dep_annual = req.risk_free.annual_rate
    else:
        try:
            dep_annual = dp.fetch_deposit_rate()["deposit_net"]
        except Exception:
            dep_annual = None

    _safe("es", lambda: {
        "es_pct": adv.expected_shortfall(port_rets, conf),
        "es975_pct": adv.expected_shortfall(port_rets, 0.975),
    })
    _safe("backtest", lambda: adv.var_backtest(port_rets, conf))
    _safe("sharpe_ci", lambda: adv.sharpe_confidence(port_rets, dep_annual or 0.0))
    _safe("beat_deposit", lambda: adv.beat_deposit_probability(port_rets, dep_annual))
    _safe("attribution", lambda: adv.risk_attribution(returns, investments, conf, var_pct))
    _safe("ewma", lambda: adv.ewma_fhs(port_rets, conf))
    _safe("drawdown", lambda: adv.drawdown_stats(port_rets))
    _safe("concentration", lambda: adv.concentration(returns, investments))
    _safe("evt", lambda: adv.evt_tail(port_rets))
    _safe("tail_dependence", lambda: adv.tail_dependence(returns[valid]))
    _safe("hrp", lambda: adv.hrp_weights(returns[valid]))

    def _real():
        cpi = dp.fetch_cpi()  # EVDS anahtari yoksa RuntimeError -> None
        return adv.real_metrics(port_rets, cpi)
    _safe("real", _real)

    # Fakat serileri: kur ayristirmasi + stil analizi ayni cekimi paylasir
    factors_raw = None
    try:
        factors_raw = dp.fetch_yahoo_prices(FACTOR_TICKERS)
    except RuntimeError:
        pass

    def _style():
        funds = [p for p in positions if p.source == "tefas"
                 and p.name in (prices_try.columns if prices_try is not None else [])]
        if not funds or factors_raw is None:
            return None
        f = pd.DataFrame(index=factors_raw.index)
        fx_s = factors_raw["TRY=X"].ffill()
        if "XU100.IS" in factors_raw:
            f["BIST 100"] = factors_raw["XU100.IS"]
        if "GC=F" in factors_raw:
            f["Altın (TL)"] = factors_raw["GC=F"] * fx_s
        f["USD/TRY"] = factors_raw["TRY=X"]
        if "^GSPC" in factors_raw:
            f["S&P 500 (TL)"] = factors_raw["^GSPC"] * fx_s
        f_rets = np.log(f / f.shift(1)).replace([np.inf, -np.inf], np.nan)
        # nakit faktoru: TLREF gunluk getirisi (yoksa sabit yaklasik)
        try:
            cash = np.log(1 + dp.fetch_rf_history("tlref")) / 252
            f_rets["Nakit/Mevduat"] = cash.reindex(f_rets.index).ffill()
        except RuntimeError:
            f_rets["Nakit/Mevduat"] = math.log(1.40) / 252
        result = {}
        for p in funds:
            s = prices_try[p.name].dropna()
            fr = np.log(s / s.shift(1)).dropna()
            result[p.name] = adv.style_analysis(fr, f_rets)
        return result or None
    _safe("style", _style)   # fx'ten ONCE: fonlarin dolayli USD maruziyeti buradan

    def _fx():
        if factors_raw is None or "TRY=X" not in factors_raw.columns:
            return None
        fx_series = factors_raw["TRY=X"].dropna()
        fx_rets = np.log(fx_series / fx_series.shift(1)).dropna()
        usd_names = {p.name for p in positions
                     if p.currency == "USD" or p.ticker == dp.GRAM_GOLD_TICKER}
        # Fonlarin dolayli USD maruziyeti: stil analizinin USD/TRY agirligi
        # (gunluk gecikme duzeltilmis) x fonun portfoy payi
        fund_usd = 0.0
        style = out.get("style") or {}
        tot = sum(investments[c] for c in returns.columns if c in investments)
        if tot > 0:
            for fname, s in style.items():
                if s and fname in investments:
                    fund_usd += (investments[fname] / tot) * max(
                        0.0, s["weights"].get("USD/TRY", 0.0))
        return adv.fx_decomposition(returns, fx_rets, investments, usd_names, fund_usd)
    _safe("fx", _fx)

    def _liquidity():
        eq = [p for p in positions if p.name in investments and p.source == "yahoo"
              and p.ticker != dp.GRAM_GOLD_TICKER
              and "=" not in p.ticker and "-" not in p.ticker]
        vols = dp.fetch_yahoo_volumes(tuple(sorted({p.ticker for p in eq}))) if eq else {}
        info = []
        for p in positions:
            if p.name not in investments:
                continue
            if p.source == "tefas":
                kind, adv_tl = "fund", None
            elif p.ticker in vols:
                fx = fx_now if p.currency == "USD" else 1.0
                kind, adv_tl = "equity", vols[p.ticker] * last_native[p.name] * fx
            else:
                kind, adv_tl = "liquid", None
            info.append({"name": p.name, "value_tl": investments[p.name],
                         "adv_tl": adv_tl, "kind": kind})
        return adv.liquidity_var(info, market_value * var_pct)
    _safe("liquidity", _liquidity)

    return out


@app.post("/portfolio/analyze")
def analyze(req: AnalyzeRequest):
    if not req.positions and not req.bonds:
        raise HTTPException(400, "En az bir pozisyon veya tahvil gerekli.")

    fx_now, valuation, failed = 0.0, [], []
    prices_try, last_native = None, {}

    if req.positions:
        try:
            prices_try, fx_now, last_native, failed = dp.build_try_prices(
                [p.model_dump() for p in req.positions]
            )
        except RuntimeError as exc:
            raise HTTPException(503, f"Veri kaynağı hatası: {exc}")
    else:
        try:
            raw = dp.fetch_yahoo_prices(("TRY=X",))
            fx_now = float(raw["TRY=X"].dropna().iloc[-1])
        except RuntimeError as exc:
            raise HTTPException(503, f"Veri kaynağı hatası: {exc}")

    investments = {}
    for p in req.positions:
        if p.name not in last_native:
            continue
        fx = fx_now if p.currency == "USD" else 1.0
        res = engine.position_pnl(p.quantity, last_native[p.name], p.cost, fx)
        investments[p.name] = res["value_try"]
        valuation.append({"name": p.name, "type": "market", "currency": p.currency,
                          "last_price": last_native[p.name], **res})

    bond_details, bond_summary = [], None
    for b in req.bonds:
        fair, mac, mod = engine.bond_metrics(b.coupon_rate, b.ytm, b.years, b.frequency)
        fx = fx_now if b.currency == "USD" else 1.0
        res = engine.position_pnl(b.nominal / 100, b.price, b.cost, fx)
        bond_details.append({"name": b.name, "type": "bond", "currency": b.currency,
                             "fair_price": fair, "macaulay": mac, "modified": mod,
                             "ytm": b.ytm, **res})
        valuation.append(bond_details[-1])

    total_value_try = sum(v["value_try"] for v in valuation)
    if bond_details:
        bond_summary = engine.bond_risk_summary(bond_details, total_value_try)

    risk = None
    if prices_try is not None and investments:
        valid = [n for n in investments if n in prices_try.columns]
        returns = engine.log_returns(prices_try[valid])
        if not returns.empty:
            port_rets = engine.portfolio_returns(returns, investments)
            var_pct = engine.historical_var(port_rets, req.confidence)

            sharpe = None
            if req.risk_free is not None:
                if req.risk_free.kind == "rate":
                    rf_daily = np.log(1 + req.risk_free.annual_rate) / 252
                elif req.risk_free.kind in ("deposit", "tlref"):
                    # Tarihsel faiz serisi: 3-5 yillik Sharpe bugunun degil
                    # o gunun faiziyle hesaplanir. EVDS yoksa sabit orana dus.
                    try:
                        hist = dp.fetch_rf_history(req.risk_free.kind)
                        rf_daily = np.log(1 + hist) / 252
                    except RuntimeError:
                        rf_daily = np.log(1 + req.risk_free.annual_rate) / 252
                else:
                    fx_t = "TRY=X" if req.risk_free.kind == "usd" else "EURTRY=X"
                    try:
                        raw_fx = dp.fetch_yahoo_prices((fx_t,))
                        fx_series = raw_fx[fx_t].dropna()
                        rf_daily = np.log(fx_series / fx_series.shift(1)).dropna()
                    except (RuntimeError, KeyError):
                        rf_daily = None
                if rf_daily is not None:
                    sharpe = engine.sharpe_multi(port_rets, rf_daily)
            market_value = sum(investments[n] for n in valid)
            risk = {
                "confidence": req.confidence,
                "sharpe": sharpe,
                "var_pct": var_pct,
                "var_value_try": market_value * var_pct,
                "market_value_try": market_value,
                "observations": len(port_rets),
                "correlation": engine.correlation_matrix(returns).round(4).to_dict(),
                "diversification": engine.diversification(returns, investments, req.confidence),
                "stress_tests": {
                    name: {
                        "region": sc["region"], "start": sc["start"], "end": sc["end"],
                        "cumulative_return": sc["result"]["cumulative_return"] if sc["result"] else None,
                        "impact_try": market_value * sc["result"]["cumulative_return"] if sc["result"] else None,
                        "missing_assets": sc["result"]["missing_assets"] if sc["result"] else valid,
                        # kapsam: portfoy degerinin ne kadari o pencerede gercek veriye
                        # sahip (dususe fon 2008'de yoksa vekil/eksik oldugu anlasilir)
                        "coverage": (1 - sum(investments[m] for m in
                                     (sc["result"]["missing_assets"] if sc["result"] else valid)
                                     if m in investments) / market_value) if market_value else None,
                    }
                    for name, sc in engine.run_stress_tests(prices_try[valid], investments,
                                                            regions=req.stress_regions).items()
                },
            }
            risk["advanced"] = _advanced_block(
                req, req.positions, returns, port_rets, investments, valid,
                market_value, var_pct, prices_try, last_native, fx_now)
            try:
                risk["advanced"]["risk_class"] = adv.srri_class(port_rets)
                sh1 = sharpe.get("1y") if isinstance(sharpe, dict) else None
                risk["advanced"]["score"] = adv.kuantile_score(
                    sh1["sharpe"] if sh1 else None,
                    {**risk["advanced"], "_var_pct": var_pct})
            except Exception:
                risk["advanced"]["risk_class"] = None
                risk["advanced"]["score"] = None

    return {
        "fx_usdtry": fx_now,
        "total_value_try": total_value_try,
        "valuation": valuation,
        "failed_assets": failed,
        "market_risk": risk,
        "bond_risk": bond_summary,
        "disclaimer": "Bu analiz yatırım danışmanlığı değildir.",
    }
