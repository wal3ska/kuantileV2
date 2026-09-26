"""Veritabani modelleri. DATABASE_URL env ile Postgres, yoksa yerel SQLite."""

import os
from datetime import datetime, timezone

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Integer,
                        String, create_engine)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column,
                            relationship, sessionmaker)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./kuantile.db")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    nickname: Mapped[str | None] = mapped_column(String(30), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    lang: Mapped[str] = mapped_column(String(2), default="tr")
    mail_daily: Mapped[bool] = mapped_column(Boolean, default=True)
    mail_weekly: Mapped[bool] = mapped_column(Boolean, default=True)
    mail_monthly: Mapped[bool] = mapped_column(Boolean, default=True)
    mail_yearly: Mapped[bool] = mapped_column(Boolean, default=True)
    verification_token: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    portfolio: Mapped["Portfolio"] = relationship(back_populates="user", uselist=False,
                                                  cascade="all, delete-orphan")


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    name: Mapped[str] = mapped_column(String(100), default="Portföyüm")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc),
                                                 onupdate=lambda: datetime.now(timezone.utc))

    user: Mapped[User] = relationship(back_populates="portfolio")
    positions: Mapped[list["Position"]] = relationship(back_populates="portfolio",
                                                       cascade="all, delete-orphan")
    bonds: Mapped[list["Bond"]] = relationship(back_populates="portfolio",
                                               cascade="all, delete-orphan")


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    name: Mapped[str] = mapped_column(String(100))
    ticker: Mapped[str] = mapped_column(String(50))
    currency: Mapped[str] = mapped_column(String(3))
    source: Mapped[str] = mapped_column(String(10), default="yahoo")
    category: Mapped[str] = mapped_column(String(20), default="BIST")
    quantity: Mapped[float] = mapped_column(Float)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)

    portfolio: Mapped[Portfolio] = relationship(back_populates="positions")


class Bond(Base):
    __tablename__ = "bonds"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    name: Mapped[str] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3))
    nominal: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    coupon_rate: Mapped[float] = mapped_column(Float)
    frequency: Mapped[int] = mapped_column(Integer, default=2)
    years: Mapped[float] = mapped_column(Float)
    ytm: Mapped[float] = mapped_column(Float)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)

    portfolio: Mapped[Portfolio] = relationship(back_populates="bonds")


# ---------------------------------------------------------------------------
# Quant Lab (admin paneli) — BIST evreni. Ana site modellerinden bagimsiz;
# offline cron job'lari doldurur, panel yalnizca okur. Tum tablolar salt-analiz.
# ---------------------------------------------------------------------------


class BistSymbol(Base):
    """Hisse tanimi + haftalik hafif fundamentaller (SirketBilgileriBySektor)."""
    __tablename__ = "bist_symbols"

    ticker: Mapped[str] = mapped_column(String(12), primary_key=True)  # THYAO (borsa kodu, .IS'siz)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sector_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_financial: Mapped[bool] = mapped_column(Boolean, default=False)   # banka/sigorta/holding: Altman Z N/A
    market_segment: Mapped[str | None] = mapped_column(String(30), nullable=True)  # 'YAKIN_IZLEME' vb.
    is_watchlist: Mapped[bool] = mapped_column(Boolean, default=False)   # Gozalti/Yakin Izleme Pazari
    # SirketBilgileriBySektor'dan hazir gelen degerler (bin TL bazli):
    equity: Mapped[float | None] = mapped_column(Float, nullable=True)       # Ozsermaye
    net_profit: Mapped[float | None] = mapped_column(Float, nullable=True)   # Net_Kar (son donem)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)   # MARKET_CAP_TL
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)   # Fiyat_TL
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc),
                                                onupdate=lambda: datetime.now(timezone.utc))


class BistPrice(Base):
    """Gunluk duzeltilmis kapanis + hacim (Yahoo .IS). Incremental doldurulur."""
    __tablename__ = "bist_prices"

    ticker: Mapped[str] = mapped_column(String(12), primary_key=True)
    d: Mapped["Date"] = mapped_column(Date, primary_key=True)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)


class BistFundamental(Base):
    """MaliTablo'dan cekilen donem bazli bilanco/gelir kalemleri (Altman Z + zarar gecmisi)."""
    __tablename__ = "bist_fundamentals"

    ticker: Mapped[str] = mapped_column(String(12), primary_key=True)
    period: Mapped[str] = mapped_column(String(7), primary_key=True)  # '2024/12'
    current_assets: Mapped[float | None] = mapped_column(Float, nullable=True)       # 1A
    current_liabilities: Mapped[float | None] = mapped_column(Float, nullable=True)  # 2A
    total_assets: Mapped[float | None] = mapped_column(Float, nullable=True)         # 2ODB (Toplam Kaynak)
    equity: Mapped[float | None] = mapped_column(Float, nullable=True)               # 2N
    retained_earnings: Mapped[float | None] = mapped_column(Float, nullable=True)    # 2OCE
    ebit: Mapped[float | None] = mapped_column(Float, nullable=True)                 # 3HACA
    net_income: Mapped[float | None] = mapped_column(Float, nullable=True)           # 3J
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc),
                                                onupdate=lambda: datetime.now(timezone.utc))


class BistMetric(Base):
    """snapshot_build ciktisi: fiyat serisinden turetilen ham metrikler + eleme bayraklari.
    Esikler burada UYGULANMAZ; panel bunlari okuyup kullanicinin esikleriyle canli filtreler."""
    __tablename__ = "bist_metrics"

    ticker: Mapped[str] = mapped_column(String(12), primary_key=True)
    obs: Mapped[int] = mapped_column(Integer, default=0)                 # kullanilan gun sayisi
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    ann_vol: Mapped[float | None] = mapped_column(Float, nullable=True)          # yillik volatilite
    geo_return_ann: Mapped[float | None] = mapped_column(Float, nullable=True)   # yillik geometrik getiri
    mean_return_ann: Mapped[float | None] = mapped_column(Float, nullable=True)  # yillik aritmetik getiri
    adv_tl: Mapped[float | None] = mapped_column(Float, nullable=True)           # ort. gunluk TL hacim (medyan)
    altman_z: Mapped[float | None] = mapped_column(Float, nullable=True)         # Altman Z" (finansallarda None)
    neg_equity: Mapped[bool] = mapped_column(Boolean, default=False)
    persistent_loss: Mapped[bool] = mapped_column(Boolean, default=False)        # son 4 donem net zarar
    is_watchlist: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc),
                                                onupdate=lambda: datetime.now(timezone.utc))


def init_db():
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
