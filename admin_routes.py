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


class UniverseRequest(BaseModel):
    filters: UniverseFilters = Field(default_factory=UniverseFilters)
    altman_min: float = 1.1                 # Z" bu esik altinda distress
    adv_min_tl: float = 5_000_000.0         # min ort. gunluk TL hacim
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


@router.post("/universe")
def universe(req: UniverseRequest, user: User = Depends(get_admin_user),
             db: Session = Depends(get_db)):
    """Ham metrikleri kullanicinin esikleriyle canli filtreler; temizlenmis evreni,
    sektor dagilimini ve eleme nedenlerini doner. Bir hisse birden cok nedenle
    elenebilir; reason sayaclari bagimsizdir (toplamlari elenen sayisini asabilir)."""
    f = req.filters
    rows = db.execute(
        select(BistMetric, BistSymbol).join(BistSymbol, BistSymbol.ticker == BistMetric.ticker)
    ).all()

    reasons = {"watchlist": 0, "neg_equity": 0, "persistent_loss": 0,
               "altman": 0, "liquidity": 0, "vol_band": 0, "geo_min": 0}
    eligible = []
    for m, s in rows:
        fails = []
        if f.watchlist and m.is_watchlist:
            fails.append("watchlist")
        if f.neg_equity and m.neg_equity:
            fails.append("neg_equity")
        if f.persistent_loss and m.persistent_loss:
            fails.append("persistent_loss")
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
