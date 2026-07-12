"""Kalici portfoy CRUD. Ucretsiz plan: kullanici basina 1 portfoy."""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_user
from db import Bond, Portfolio, Position, User, get_db

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


class PositionIn(BaseModel):
    name: str
    ticker: str
    currency: Literal["TRY", "USD"]
    source: Literal["yahoo", "tefas"] = "yahoo"
    category: str = "BIST"
    quantity: float = Field(gt=0)
    cost: Optional[float] = None


class BondIn(BaseModel):
    name: str
    currency: Literal["TRY", "USD"]
    nominal: float = Field(gt=0)
    price: float = Field(gt=0)
    coupon_rate: float = Field(ge=0)
    frequency: int = 2
    years: float = Field(gt=0)
    ytm: float = Field(gt=0)
    cost: Optional[float] = None


class PortfolioIn(BaseModel):
    positions: list[PositionIn] = []
    bonds: list[BondIn] = []


def _get_portfolio(user: User, db: Session) -> Portfolio:
    pf = db.query(Portfolio).filter(Portfolio.user_id == user.id).first()
    if pf is None:
        pf = Portfolio(user_id=user.id)
        db.add(pf)
        db.commit()
        db.refresh(pf)
    return pf


@router.get("")
def get_portfolio(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pf = _get_portfolio(user, db)
    return {
        "name": pf.name,
        "updated_at": pf.updated_at.isoformat() if pf.updated_at else None,
        "positions": [{"name": p.name, "ticker": p.ticker, "currency": p.currency,
                       "source": p.source, "category": p.category,
                       "quantity": p.quantity, "cost": p.cost} for p in pf.positions],
        "bonds": [{"name": b.name, "currency": b.currency, "nominal": b.nominal,
                   "price": b.price, "coupon_rate": b.coupon_rate, "frequency": b.frequency,
                   "years": b.years, "ytm": b.ytm, "cost": b.cost} for b in pf.bonds],
    }


@router.put("")
def save_portfolio(body: PortfolioIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    if len(body.positions) > 50 or len(body.bonds) > 10:
        raise HTTPException(422, "Pozisyon limiti aşıldı.")
    pf = _get_portfolio(user, db)
    pf.positions.clear()
    pf.bonds.clear()
    for p in body.positions:
        pf.positions.append(Position(**p.model_dump()))
    for b in body.bonds:
        pf.bonds.append(Bond(**b.model_dump()))
    db.commit()
    return {"message": "Portföy kaydedildi.",
            "positions": len(body.positions), "bonds": len(body.bonds)}
