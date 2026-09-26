"""Admin paneli uclari. Yalnizca ADMIN_EMAIL sahibi erisebilir.

Kimlik dogrulama mevcut JWT akisini yeniden kullanir (auth.get_current_user);
tek fark, get_admin_user'in token sahibinin e-postasini ADMIN_EMAIL ile
karsilastirmasidir. QPC (kantitatif portfoy insasi) toollari buraya eklenecek.
"""

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth import get_current_user
from db import BistMetric, BistSymbol, User, get_db

# Panelin tek yetkili kullanicisi. Prod'da env ile ezilebilir.
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "anilserdar.unal20@gmail.com").lower()

router = APIRouter(prefix="/admin", tags=["admin"])


def get_admin_user(user: User = Depends(get_current_user)) -> User:
    """get_current_user'in ustune yetki katmani: sadece ADMIN_EMAIL gecer."""
    if (user.email or "").lower() != ADMIN_EMAIL:
        raise HTTPException(403, "Bu alana erişim yetkiniz yok.")
    return user


@router.get("/me")
def admin_me(user: User = Depends(get_admin_user)):
    """Panel acilisinda token + yetki dogrulamasi. Frontend bununla kapiyi acar."""
    return {"email": user.email, "nickname": user.nickname, "admin": True}


# --------------------------------------------------------------------------- #
# Quant Lab · Varlik Evreni — ham metrikler + canli (ayarlanabilir) eleme
# --------------------------------------------------------------------------- #

class UniverseFilters(BaseModel):
    watchlist: bool = True          # Gozalti/Yakin Izleme Pazari disla
    neg_equity: bool = True         # Negatif ozkaynak disla
    persistent_loss: bool = True    # Surekli zarar disla
    altman: bool = True             # Altman Z" distress disla
    liquidity: bool = True          # Likidite esigi altini disla
    limit_down: bool = True         # Taban serisi (ust uste sert dusus) disla


class UniverseRequest(BaseModel):
    filters: UniverseFilters = Field(default_factory=UniverseFilters)
    altman_min: float = 1.1                 # Z" bu esik altinda distress
    adv_min_tl: float = 5_000_000.0         # min ort. gunluk TL hacim
    loss_years_min: int = 3                 # bu kadar YIL ust uste zarar edeni ele (kronik)
    limit_down_days_min: int = 2            # bu kadar GUN ust uste taban (<=-%8) edeni ele
    vol_min: float | None = None            # opsiyonel yillik vol bandi
    vol_max: float | None = None
    geo_min: float | None = None            # opsiyonel min yillik geometrik getiri


@router.get("/universe/status")
def universe_status(user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    """Veri tazeligi: kac hisse, en son ne zaman guncellendi."""
    n = db.scalar(select(func.count()).select_from(BistMetric)) or 0
    as_of = db.scalar(select(func.max(BistMetric.updated_at)))
    n_sym = db.scalar(select(func.count()).select_from(BistSymbol)) or 0
    return {"metrics": n, "symbols": n_sym, "as_of": as_of.isoformat() if as_of else None}


def _eligible(rows, req: UniverseRequest):
    """(metric, symbol) satirlarini req esikleriyle filtreler. Bir hisse birden cok
    nedenle elenebilir; reason sayaclari bagimsizdir. Doner: (eligible, reasons)."""
    f = req.filters
    reasons = {"watchlist": 0, "neg_equity": 0, "persistent_loss": 0,
               "altman": 0, "liquidity": 0, "limit_down": 0, "vol_band": 0, "geo_min": 0}
    eligible = []
    for m, s in rows:
        fails = []
        if f.watchlist and m.is_watchlist:
            fails.append("watchlist")
        if f.neg_equity and m.neg_equity:
            fails.append("neg_equity")
        if f.persistent_loss and m.loss_streak >= req.loss_years_min:
            fails.append("persistent_loss")
        if f.limit_down and m.limit_down_streak >= req.limit_down_days_min:
            fails.append("limit_down")
        if f.altman and m.altman_z is not None and m.altman_z < req.altman_min:
            fails.append("altman")
        if f.liquidity and (m.adv_tl is None or m.adv_tl < req.adv_min_tl):
            fails.append("liquidity")
        if req.vol_min is not None and (m.ann_vol is None or m.ann_vol < req.vol_min):
            fails.append("vol_band")
        if req.vol_max is not None and (m.ann_vol is None or m.ann_vol > req.vol_max):
            fails.append("vol_band")
        if req.geo_min is not None and (m.geo_return_ann is None or m.geo_return_ann < req.geo_min):
            fails.append("geo_min")
        for r in fails:
            reasons[r] += 1
        if not fails:
            eligible.append((m, s))
    return eligible, reasons


@router.post("/universe")
def universe(req: UniverseRequest, user: User = Depends(get_admin_user),
             db: Session = Depends(get_db)):
    """Ham metrikleri kullanicinin esikleriyle canli filtreler; temizlenmis evreni,
    sektor dagilimini ve eleme nedenlerini doner."""
    rows = db.execute(
        select(BistMetric, BistSymbol).join(BistSymbol, BistSymbol.ticker == BistMetric.ticker)
    ).all()
    eligible, reasons = _eligible(rows, req)

    # Sektor dagilimi (yalnizca uygun hisseler)
    sec_counts: dict[str, int] = {}
    for m, s in eligible:
        key = s.sector or "Diğer"
        sec_counts[key] = sec_counts.get(key, 0) + 1
    n_elig = len(eligible)
    sectors = sorted(
        ({"sector": k, "count": v, "share": (v / n_elig if n_elig else 0)}
         for k, v in sec_counts.items()),
        key=lambda x: x["count"], reverse=True,
    )

    def _row(m, s):
        return {
            "ticker": m.ticker, "name": s.name, "sector": s.sector,
            "ann_vol": m.ann_vol, "geo_return_ann": m.geo_return_ann,
            "adv_tl": m.adv_tl, "altman_z": m.altman_z, "obs": m.obs,
            "market_cap": s.market_cap,
        }

    sample = sorted(eligible, key=lambda t: (t[0].adv_tl or 0), reverse=True)[:60]
    as_of = db.scalar(select(func.max(BistMetric.updated_at)))
    return {
        "as_of": as_of.isoformat() if as_of else None,
        "total": len(rows),
        "eligible_count": n_elig,
        "excluded_reasons": reasons,
        "sectors": sectors,
        "sample": [_row(m, s) for m, s in sample],
    }


# --------------------------------------------------------------------------- #
# Quant Lab · Portfoy Insasi (Faz 2)
# --------------------------------------------------------------------------- #

class PortfolioRequest(BaseModel):
    universe: UniverseRequest = Field(default_factory=UniverseRequest)  # eleme
    method: str = "max_sharpe"          # max_sharpe|min_variance|risk_parity|hrp|equal
    max_assets: int = Field(default=50, ge=5, le=120)
    max_weight: float = Field(default=0.10, gt=0, le=1)
    sector_cap: float | None = Field(default=0.30)   # sektor basi tavan (None=kapali)
    rf_annual: float = Field(default=0.0, ge=0, le=3)
    window_years: int = Field(default=5, ge=1, le=5)


@router.post("/portfolio")
def portfolio(req: PortfolioRequest, user: User = Depends(get_admin_user),
              db: Session = Depends(get_db)):
    """Uygun evrende (en likit `max_assets` hisse) secilen yontemle portfoy kurar
    ve degerlendirir. Agir hesaplama import'lari yalnizca burada yuklenir."""
    import bist_portfolio as PF

    if req.method not in PF.METHODS:
        raise HTTPException(400, f"Geçersiz yöntem. Seçenekler: {', '.join(PF.METHODS)}")

    rows = db.execute(
        select(BistMetric, BistSymbol).join(BistSymbol, BistSymbol.ticker == BistMetric.ticker)
    ).all()
    eligible, _ = _eligible(rows, req.universe)
    if len(eligible) < 2:
        raise HTTPException(400, "Uygun evren çok küçük; filtreleri gevşetin.")

    # Likiditeye gore sirala; en likit adaylari optimizasyona ver
    eligible.sort(key=lambda t: (t[0].adv_tl or 0), reverse=True)
    tickers = [m.ticker for m, s in eligible]
    sector_map = {s.ticker: s.sector for m, s in eligible}

    result = PF.build(
        db, tickers, sector_map, method=req.method, max_assets=req.max_assets,
        max_weight=req.max_weight, sector_cap=req.sector_cap, rf_annual=req.rf_annual,
        window_years=req.window_years,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    result["eligible_count"] = len(eligible)
    return result


# --------------------------------------------------------------------------- #
# Quant Lab · Backtest (Faz 3) — walk-forward OOS + reel getiri
# --------------------------------------------------------------------------- #

class BacktestRequest(BaseModel):
    universe: UniverseRequest = Field(default_factory=UniverseRequest)
    method: str = "max_sharpe"
    max_assets: int = Field(default=30, ge=5, le=80)
    max_weight: float = Field(default=0.10, gt=0, le=1)
    sector_cap: float | None = Field(default=0.30)
    rf_annual: float = Field(default=0.0, ge=0, le=3)
    window_years: int = Field(default=5, ge=1, le=5)
    train_years: float = Field(default=3.0, ge=0.5, le=5)
    test_months: int = Field(default=3, ge=1, le=12)


@router.post("/backtest")
def backtest(req: BacktestRequest, user: User = Depends(get_admin_user),
             db: Session = Depends(get_db)):
    """Uygun evrende walk-forward (OOS) backtest: agirliklar train'de uretilir,
    test'te degerlendirilir. 1/N benchmark ve TUFE reel getirisiyle raporlanir."""
    import bist_backtest as BT

    rows = db.execute(
        select(BistMetric, BistSymbol).join(BistSymbol, BistSymbol.ticker == BistMetric.ticker)
    ).all()
    eligible, _ = _eligible(rows, req.universe)
    if len(eligible) < 2:
        raise HTTPException(400, "Uygun evren çok küçük; filtreleri gevşetin.")
    eligible.sort(key=lambda t: (t[0].adv_tl or 0), reverse=True)
    tickers = [m.ticker for m, s in eligible]
    sector_map = {s.ticker: s.sector for m, s in eligible}

    result = BT.run_backtest(
        db, tickers, sector_map, method=req.method, max_assets=req.max_assets,
        max_weight=req.max_weight, sector_cap=req.sector_cap, rf_annual=req.rf_annual,
        window_years=req.window_years, train_years=req.train_years, test_months=req.test_months,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


class ProjectionRequest(PortfolioRequest):
    horizon_months: int = Field(default=12, ge=1, le=36)


@router.post("/projection")
def projection(req: ProjectionRequest, user: User = Depends(get_admin_user),
               db: Session = Depends(get_db)):
    """Insa edilen portfoyu ileriye Monte Carlo ile projekte eder: varlik medyan
    yollari + portfoy p5/p50/p95 bandi. Ayni PortfolioRequest'e baglidir."""
    import bist_portfolio as PF

    rows = db.execute(
        select(BistMetric, BistSymbol).join(BistSymbol, BistSymbol.ticker == BistMetric.ticker)
    ).all()
    eligible, _ = _eligible(rows, req.universe)
    if len(eligible) < 2:
        raise HTTPException(400, "Uygun evren çok küçük; filtreleri gevşetin.")
    eligible.sort(key=lambda t: (t[0].adv_tl or 0), reverse=True)
    tickers = [m.ticker for m, s in eligible]
    sector_map = {s.ticker: s.sector for m, s in eligible}

    result = PF.project(
        db, tickers, sector_map, method=req.method, max_assets=req.max_assets,
        max_weight=req.max_weight, sector_cap=req.sector_cap, rf_annual=req.rf_annual,
        window_years=req.window_years, horizon_months=req.horizon_months,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result
