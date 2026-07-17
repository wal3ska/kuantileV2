"""FastAPI backend. Calistirma: uvicorn api:app --host 0.0.0.0 --port 8000
Dokumantasyon otomatik: http://localhost:8000/docs"""

import os
from datetime import date
from typing import Literal, Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

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


class AnalyzeRequest(BaseModel):
    positions: list[Position] = []
    bonds: list[Bond] = []
    confidence: float = Field(default=0.99, gt=0.5, lt=1.0)
    stress_regions: Optional[list[str]] = None


class BondDurationRequest(BaseModel):
    coupon_rate: float = Field(ge=0)
    ytm: float = Field(gt=0)
    years: float = Field(gt=0)
    frequency: int = 2


@app.get("/health")
def health():
    return {"status": "ok"}


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
            market_value = sum(investments[n] for n in valid)
            risk = {
                "confidence": req.confidence,
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
                    }
                    for name, sc in engine.run_stress_tests(prices_try[valid], investments,
                                                            regions=req.stress_regions).items()
                },
            }

    return {
        "fx_usdtry": fx_now,
        "total_value_try": total_value_try,
        "valuation": valuation,
        "failed_assets": failed,
        "market_risk": risk,
        "bond_risk": bond_summary,
        "disclaimer": "Bu analiz yatırım danışmanlığı değildir.",
    }
