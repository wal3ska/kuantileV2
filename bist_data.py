"""BIST veri ingest (Quant Lab offline hatti).

Kaynaklar (hepsi sunucudan dogrulandi):
  - Universe + sektor + hafif fundamentaller: Is Yatirim `SirketBilgileriBySektor`
    (tek cagri, ~820 kayit) -> BistSymbol.
  - Bilanco/gelir kalemleri (Altman Z + zarar gecmisi): Is Yatirim `MaliTablo`
    (hisse basina) -> BistFundamental.
  - Gunluk fiyat/hacim: Yahoo Finance `.IS` (yfinance) -> BistPrice (incremental).

Bu modul yalnizca CANLI ISTEK DISINDA (cron) calisir; ana site/api istek yolunu
etkilemez. Bellek dostu: hisseler parti parti islenir.
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import httpx
import pandas as pd
import yfinance as yf
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from db import (DATABASE_URL, BistFundamental, BistMetric, BistPrice,
                BistSymbol, SessionLocal)

IS_BASE = "https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/Data.aspx"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Referer": "https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/Temel-Degerler-Ve-Oranlar.aspx",
    "Accept": "application/json, text/plain, */*",
}

# Gozalti / Yakin Izleme Pazari override listesi. Temiz bir API'si olmadigindan
# elle guncellenebilir; env ile de verilebilir (virgul ayrik). Bos ise diger 3
# finansal filtre distress'i yakalar.
_WATCHLIST = {t.strip().upper() for t in os.getenv("BIST_WATCHLIST", "").split(",") if t.strip()}

# Finansal sektor anahtar kelimeleri (Altman Z bunlara UYGULANMAZ).
_FIN_KEYS = ("banka", "sigorta", "holding", "finansal", "yatırım ortaklığı",
             "gayrimenkul yatırım", "aracı kurum", "faktoring", "leasing",
             "finansal kiralama", "portföy", "emeklilik")


def _num(x) -> float | None:
    """Is Yatirim sayilarini (US ondalik veya TR virgul) float'a cevir."""
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() in ("null", "nan", "-"):
        return None
    if "," in s and "." in s:          # 1.234,56 -> TR bin ayraci
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                     # 1234,56 -> TR ondalik
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _upsert(db, model, rows: list[dict], index_elements: list[str]):
    """Postgres/SQLite icin PK cakismasinda guncelleyen toplu upsert."""
    if not rows:
        return
    ins = pg_insert if DATABASE_URL.startswith("postgres") else sqlite_insert
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        stmt = ins(model).values(chunk)
        update_cols = {c: getattr(stmt.excluded, c) for c in chunk[0] if c not in index_elements}
        stmt = stmt.on_conflict_do_update(index_elements=index_elements, set_=update_cols)
        db.execute(stmt)
    db.commit()


# --------------------------------------------------------------------------- #
# 1) Universe + hafif fundamentaller
# --------------------------------------------------------------------------- #

def fetch_universe() -> list[dict]:
    url = f"{IS_BASE}/SirketBilgileriBySektor"
    r = httpx.get(url, headers=_HEADERS, timeout=40)
    r.raise_for_status()
    return r.json().get("value", []) or []


def sync_universe(db) -> int:
    rows = fetch_universe()
    out = []
    seen = set()
    for r in rows:
        tk = (r.get("Title") or "").strip().upper()
        # Gecerli borsa kodu: 4-6 harf/rakam. Endeks/uyari satirlarini ele.
        if not tk or not tk.isalnum() or len(tk) > 6 or tk in seen:
            continue
        seen.add(tk)
        sector = (r.get("AS_ALT_SEKTOR_TANIMI") or "").strip() or None
        is_fin = bool(sector and any(k in sector.lower() for k in _FIN_KEYS))
        out.append({
            "ticker": tk,
            "name": (r.get("Title") or "").strip() or None,
            "sector_code": (r.get("AS_ALT_SEKTOR_KODU") or "").strip() or None,
            "sector": sector,
            "is_financial": is_fin,
            "market_segment": "YAKIN_IZLEME" if tk in _WATCHLIST else None,
            "is_watchlist": tk in _WATCHLIST,
            "equity": _num(r.get("Ozsermaye")),
            "net_profit": _num(r.get("Net_Kar")),
            "market_cap": _num(r.get("MARKET_CAP_TL")),
            "last_price": _num(r.get("Fiyat_TL_Price_TL")),
        })
    _upsert(db, BistSymbol, out, ["ticker"])
    return len(out)


# --------------------------------------------------------------------------- #
# 2) Bilanco / gelir (MaliTablo) -> Altman Z girdileri + zarar gecmisi
# --------------------------------------------------------------------------- #

# Kalem eslemesi: once itemCode, tutmazsa itemDescTr icinden anahtar kelime.
_ITEM_CODE = {
    "current_assets": "1A", "current_liabilities": "2A", "total_assets": "2ODB",
    "equity": "2N", "retained_earnings": "2OCE", "ebit": "3HACA", "net_income": "3J",
}
_ITEM_DESC = {
    "current_assets": ["dönen varlıklar"],
    "current_liabilities": ["kısa vadeli yükümlülükler"],
    "total_assets": ["toplam kaynak", "toplam varlık"],
    "equity": ["özkaynaklar"],
    "retained_earnings": ["geçmiş yıllar kar"],
    "ebit": ["finansman gideri öncesi faaliyet kar", "esas faaliyet kar"],
    "net_income": ["dönem karı/zararı", "dönem kar"],
}


def fetch_maltablo(ticker: str, years: list[int], periods: list[int],
                   group: str = "XI_29") -> dict:
    """MaliTablo: verilen (yil,donem) ciftlerini (value1=ilk cift) {itemCode: row} doner."""
    parts = [f"year{i}={y}&period{i}={p}" for i, (y, p) in enumerate(zip(years, periods), 1)]
    url = f"{IS_BASE}/MaliTablo?companyCode={ticker}&exchange=TRY&financialGroup={group}&" + "&".join(parts)
    r = httpx.get(url, headers=_HEADERS, timeout=30)
    r.raise_for_status()
    return {row.get("itemCode"): row for row in (r.json().get("value") or [])}


def _pick(items: dict, field: str, vkey: str):
    code = _ITEM_CODE[field]
    if code in items:
        return _num(items[code].get(vkey))
    for row in items.values():
        desc = (row.get("itemDescTr") or "").strip().lower()
        if any(k in desc for k in _ITEM_DESC[field]):
            return _num(row.get(vkey))
    return None


def _fundamentals_for(ticker: str) -> list[dict]:
    """Son 4 TAMAMLANMIS mali yilin yillik (donem 12) kalemlerini tek cagriyla ceker.
    value1 = en yeni tamamlanmis yil (Altman Z bunun bilancosunu kullanir);
    net_income serisi de cok-yilli 'surekli zarar' testine girer.
    XI_29 bos donerse UFRS_K/UFRS denenir (banka/finansal)."""
    cy = date.today().year
    years = [cy - 1, cy - 2, cy - 3, cy - 4]   # ornek 2026 icin: 2025..2022
    for group in ("XI_29", "UFRS_K", "UFRS"):
        try:
            items = fetch_maltablo(ticker, years, [12, 12, 12, 12], group)
        except Exception:
            continue
        if not items:
            continue
        rows = []
        for idx, vkey in enumerate(("value1", "value2", "value3", "value4")):
            ni = _pick(items, "net_income", vkey)
            ta = _pick(items, "total_assets", vkey)
            if ni is None and ta is None:
                continue
            rows.append({
                "ticker": ticker, "period": f"{years[idx]}/12",
                "current_assets": _pick(items, "current_assets", vkey),
                "current_liabilities": _pick(items, "current_liabilities", vkey),
                "total_assets": ta,
                "equity": _pick(items, "equity", vkey),
                "retained_earnings": _pick(items, "retained_earnings", vkey),
                "ebit": _pick(items, "ebit", vkey),
                "net_income": ni,
            })
        if rows:
            return rows
    return []


def sync_fundamentals(db, tickers: list[str] | None = None, workers: int = 6) -> int:
    if tickers is None:
        tickers = [s.ticker for s in db.execute(select(BistSymbol)).scalars()]
    total = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fundamentals_for, tk): tk for tk in tickers}
        batch: list[dict] = []
        for fut in as_completed(futs):
            try:
                rows = fut.result()
            except Exception:
                rows = []
            batch.extend(rows)
            if len(batch) >= 400:
                _upsert(db, BistFundamental, batch, ["ticker", "period"])
                total += len(batch)
                batch = []
        if batch:
            _upsert(db, BistFundamental, batch, ["ticker", "period"])
            total += len(batch)
    return total


# --------------------------------------------------------------------------- #
# 3) Fiyat / hacim (Yahoo .IS) — incremental
# --------------------------------------------------------------------------- #

def _last_price_dates(db) -> dict[str, date]:
    from sqlalchemy import func
    q = db.execute(select(BistPrice.ticker, func.max(BistPrice.d)).group_by(BistPrice.ticker))
    return {tk: d for tk, d in q}


def sync_prices(db, tickers: list[str] | None = None, years: int = 5,
                chunk: int = 40) -> int:
    """Eksik gunleri Yahoo'dan cekip ekler. Ilk calismada `years` yillik backfill,
    sonrasinda sadece yeni gunler (PK cakismasi upsert ile idempotent)."""
    if tickers is None:
        tickers = [s.ticker for s in db.execute(select(BistSymbol)).scalars()]
    last = _last_price_dates(db)
    full_start = date.today() - timedelta(days=int(years * 365.25))
    total = 0
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        # Parti icin en erken gerekli baslangic (yeni hisse -> full backfill).
        starts = [last[t] + timedelta(days=1) if t in last else full_start for t in part]
        start = min(starts)
        symbols = [f"{t}.IS" for t in part]
        try:
            df = yf.download(symbols, start=start.isoformat(), auto_adjust=True,
                             group_by="ticker", threads=True, progress=False)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = []
        for t in part:
            sym = f"{t}.IS"
            try:
                sub = df[sym] if isinstance(df.columns, pd.MultiIndex) else df
            except KeyError:
                continue
            sub = sub.dropna(subset=["Close"])
            cutoff = last.get(t)
            for ts, r in sub.iterrows():
                d = ts.date()
                if cutoff and d <= cutoff:
                    continue
                close = float(r["Close"])
                vol = r.get("Volume")
                rows.append({"ticker": t, "d": d, "close": close,
                             "volume": None if pd.isna(vol) else float(vol)})
        _upsert(db, BistPrice, rows, ["ticker", "d"])
        total += len(rows)
        time.sleep(0.5)  # Yahoo'ya nazik ol
    return total


# --------------------------------------------------------------------------- #
# 4) Emtia (TL bazli) — Yahoo USD serisi * USDTRY, gerekirse gram'a cevrilir
# --------------------------------------------------------------------------- #

OUNCE_TO_GRAM = 31.1034768
# (kod, ad, yahoo sembol, bolen)  bolen=31.10 -> ons'tan grama.
# Yalnizca yatirimi kolay degerli metaller: gram altin + gram gumus.
# (platin/Brent/bakir cikarildi — bireysel yatirim araci degil.)
_COMMODITIES = [
    ("XAUTRY", "Gram Altın (TL)", "GC=F", OUNCE_TO_GRAM),
    ("XAGTRY", "Gram Gümüş (TL)", "SI=F", OUNCE_TO_GRAM),
]


def sync_commodities(db, years: int = 5) -> int:
    """Emtiaları TL bazinda BistPrice'a yazar; sektor='Emtia' (fundamental filtreler
    uygulanmaz, snapshot'ta likidite muaf). USD serisi * USDTRY, altin/gumus/platin gram."""
    start = date.today() - timedelta(days=int(years * 365.25))
    ysyms = ["TRY=X"] + [c[2] for c in _COMMODITIES]
    try:
        df = yf.download(ysyms, start=start.isoformat(), auto_adjust=True,
                         group_by="ticker", threads=True, progress=False)
    except Exception:
        return 0
    if df is None or df.empty:
        return 0
    try:
        fx = df["TRY=X"]["Close"].dropna()          # 1 USD kac TL
    except KeyError:
        return 0
    last = _last_price_dates(db)
    total = 0
    for code, name, ysym, div in _COMMODITIES:
        _upsert(db, BistSymbol, [{
            "ticker": code, "name": name, "sector": "Emtia", "sector_code": "EMTIA",
            "is_financial": False, "is_watchlist": False, "market_segment": None,
        }], ["ticker"])
        try:
            usd = df[ysym]["Close"].dropna()
        except KeyError:
            continue
        merged = pd.concat([usd.rename("u"), fx.rename("fx")], axis=1).dropna()
        tl = merged["u"] * merged["fx"] / div
        cutoff = last.get(code)
        rows = [{"ticker": code, "d": ts.date(), "close": float(v), "volume": None}
                for ts, v in tl.items() if (cutoff is None or ts.date() > cutoff)]
        _upsert(db, BistPrice, rows, ["ticker", "d"])
        total += len(rows)
    return total


# --------------------------------------------------------------------------- #
# 5) TEFAS fonlari (YAT + BYF) — NAV serisi, incremental
# --------------------------------------------------------------------------- #

def _tefas_fund_list() -> dict:
    """Tum aktif TEFAS fonlari: kod -> unvan. Son gunlerin snapshot'indan derlenir."""
    from tefas import Crawler
    end = date.today()
    start = end - timedelta(days=6)
    out: dict[str, str] = {}
    for kind in ("YAT", "BYF"):
        try:
            df = Crawler().fetch(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"),
                                 columns=["code", "title"], kind=kind)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        titles = df["title"] if "title" in df.columns else df["code"]
        for c, t in zip(df["code"], titles):
            code = str(c).strip().upper()
            if code:
                out[code] = str(t).strip()[:120]
    return out


def sync_tefas(db, years: int = 5, workers: int = 6) -> int:
    """TEFAS fonlarini BistPrice'a yazar; sektor='TEFAS Fon' (fundamental/likidite/taban
    filtrelerinden muaf, snapshot'ta). NAV serisi _fetch_one_tefas ile (YAT/EMK/BYF oto)."""
    from data_provider import _fetch_one_tefas
    funds = _tefas_fund_list()
    if not funds:
        return 0
    _upsert(db, BistSymbol, [{
        "ticker": code, "name": title or code, "sector": "TEFAS Fon", "sector_code": "TEFAS",
        "is_financial": False, "is_watchlist": False, "market_segment": None,
    } for code, title in funds.items()], ["ticker"])

    last = _last_price_dates(db)
    full_start = date.today() - timedelta(days=int(years * 365.25))
    end_str = date.today().strftime("%Y-%m-%d")

    def _one(code):
        start = (last[code] + timedelta(days=1)) if code in last else full_start
        if start > date.today():
            return code, None
        return code, _fetch_one_tefas(code, start.strftime("%Y-%m-%d"), end_str)

    total = 0
    batch: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for code, s in ex.map(_one, list(funds)):
            if s is None:
                continue
            cutoff = last.get(code)
            for ts, v in s.items():
                d = ts.date()
                if cutoff and d <= cutoff:
                    continue
                batch.append({"ticker": code, "d": d, "close": float(v), "volume": None})
            if len(batch) >= 2000:
                _upsert(db, BistPrice, batch, ["ticker", "d"])
                total += len(batch)
                batch = []
    if batch:
        _upsert(db, BistPrice, batch, ["ticker", "d"])
        total += len(batch)
    return total


# --------------------------------------------------------------------------- #
# Tekil calistirma yardimcisi
# --------------------------------------------------------------------------- #

def run(job: str) -> str:
    db = SessionLocal()
    try:
        if job == "universe":
            return f"universe: {sync_universe(db)} hisse"
        if job == "prices":
            n_stock = sync_prices(db)
            n_comm = sync_commodities(db)
            return f"prices: {n_stock} hisse + {n_comm} emtia yeni satir"
        if job == "commodities":
            return f"commodities: {sync_commodities(db)} yeni satir"
        if job == "tefas":
            return f"tefas: {sync_tefas(db)} yeni satir"
        if job == "fundamentals":
            return f"fundamentals: {sync_fundamentals(db)} donem satiri"
        raise ValueError(f"bilinmeyen job: {job}")
    finally:
        db.close()
