"""Veri katmani soyutlamasi. Kaynak degisikligi (lisansli API'ye gecis)
yalnizca bu dosyayi degistirir; motor ve UI etkilenmez."""

import os
import time
from datetime import date, timedelta

import httpx
import pandas as pd
import yfinance as yf

YAHOO_START = "2000-01-01"
TEFAS_MAX_YEARS = 5

# Sentetik gram altin (TL): Yahoo'da dogrudan senedi yok.
# GC=F (ons/USD) * USDTRY / 31.1035 olarak turetilir.
GRAM_GOLD_TICKER = "GRAMALTIN"
GOLD_OUNCE_TICKER = "GC=F"
OUNCE_TO_GRAM = 31.1034768


# --- TCMB EVDS: mevduat faizi (haftalik) ve BIST TLREF (gunluk) ---
# Anahtar ucretsiz: evds3.tcmb.gov.tr -> kayit -> profil -> API Anahtari.
# Eski evds2 servisi kapatildi; yeni taban yol igmevdsms-dis.
EVDS_BASE_URL = os.getenv("EVDS_BASE_URL", "https://evds3.tcmb.gov.tr/igmevdsms-dis/")
EVDS_API_KEY = os.getenv("EVDS_API_KEY", "")
EVDS_DEPOSIT_SERIES = os.getenv("EVDS_DEPOSIT_SERIES", "TP.TRY.MT03")  # 3 aya kadar vadeli
EVDS_TLREF_SERIES = os.getenv("EVDS_TLREF_SERIES", "TP.BISTTLREF.ORAN")
DEPOSIT_STOPAJ = float(os.getenv("DEPOSIT_STOPAJ", "0.15"))
_RATES_TTL = 12 * 3600
_rates_cache: dict = {"t": 0.0, "data": None}
_rf_hist_cache: dict = {}  # kind -> {"t": ..., "data": pd.Series}


def fetch_evds_series(series_code: str, start: date, end: date) -> "pd.Series":
    """EVDS serisini gunluk/haftalik tarihli pd.Series (yuzde deger) olarak doner.
    Anahtar tanimsizsa veya EVDS cevap vermezse RuntimeError."""
    if not EVDS_API_KEY:
        raise RuntimeError("EVDS_API_KEY tanımlı değil.")
    url = (f"{EVDS_BASE_URL}series={series_code}"
           f"&startDate={start.strftime('%d-%m-%Y')}&endDate={end.strftime('%d-%m-%Y')}&type=json")
    resp = httpx.get(url, headers={"key": EVDS_API_KEY}, timeout=20)
    if resp.status_code >= 400:
        raise RuntimeError(f"EVDS hatası: {resp.status_code}")
    col = series_code.replace(".", "_")
    dates, vals = [], []
    try:
        items = resp.json().get("items", [])
    except ValueError:
        raise RuntimeError("EVDS beklenmeyen cevap döndü.")
    for item in items:
        v = item.get(col)
        if v not in (None, "", "null"):
            dates.append(pd.to_datetime(item["Tarih"], format="%d-%m-%Y"))
            vals.append(float(v))
    if not vals:
        raise RuntimeError(f"EVDS serisi boş döndü: {series_code}")
    return pd.Series(vals, index=dates).sort_index()


def fetch_deposit_rate() -> dict:
    """Guncel oranlar: TCMB haftalik agirlikli ortalama TRY mevduat faizi
    (brut ve stopaj sonrasi net) + BIST TLREF gecelik referans faizi."""
    if _rates_cache["data"] and time.time() - _rates_cache["t"] < _RATES_TTL:
        return _rates_cache["data"]
    end = date.today()
    dep = fetch_evds_series(EVDS_DEPOSIT_SERIES, end - timedelta(days=90), end)
    gross = float(dep.iloc[-1]) / 100
    data = {
        "deposit_gross": gross,
        "deposit_net": gross * (1 - DEPOSIT_STOPAJ),
        "stopaj": DEPOSIT_STOPAJ,
        "as_of": dep.index[-1].strftime("%d-%m-%Y"),
        "source": "TCMB EVDS",
    }
    try:
        tlref = fetch_evds_series(EVDS_TLREF_SERIES, end - timedelta(days=30), end)
        data["tlref"] = float(tlref.iloc[-1]) / 100
        data["tlref_as_of"] = tlref.index[-1].strftime("%d-%m-%Y")
    except RuntimeError:
        pass  # mevduat geldiyse TLREF'siz de cevap ver
    _rates_cache.update(t=time.time(), data=data)
    return data


def fetch_rf_history(kind: str, years: int = 6) -> "pd.Series":
    """Cok vadeli Sharpe icin gunluk yillik-oran serisi (ondalik, net).
    kind: 'deposit' (stopaj dusulmus mevduat, haftalik->gunluk ffill)
    veya 'tlref' (BIST TLREF gunluk)."""
    cached = _rf_hist_cache.get(kind)
    if cached and time.time() - cached["t"] < _RATES_TTL:
        return cached["data"]
    end = date.today()
    start = end - timedelta(days=365 * years)
    if kind == "deposit":
        s = fetch_evds_series(EVDS_DEPOSIT_SERIES, start, end) / 100 * (1 - DEPOSIT_STOPAJ)
    elif kind == "tlref":
        s = fetch_evds_series(EVDS_TLREF_SERIES, start, end) / 100
    else:
        raise RuntimeError(f"Bilinmeyen oran türü: {kind}")
    daily = s.resample("D").ffill()
    _rf_hist_cache[kind] = {"t": time.time(), "data": daily}
    return daily


def fetch_yahoo_prices(tickers: tuple, start: str = YAHOO_START, retries: int = 3) -> pd.DataFrame:
    """Kapanis fiyatlari (auto-adjusted). Bos sonucta RuntimeError firlatir ki
    cagiran taraf bos veriyi cache'lemesin."""
    data = None
    for attempt in range(retries):
        data = yf.download(list(tickers), start=start, progress=False, auto_adjust=True)
        if data is not None and not data.empty:
            break
        time.sleep(2 * (attempt + 1))
    if data is None or data.empty:
        raise RuntimeError("Yahoo Finance veri döndürmedi.")
    close = data["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame(name=tickers[0])
    close.index = pd.to_datetime(close.index)
    return close


def fetch_tefas_funds(fund_codes: tuple, years: int = TEFAS_MAX_YEARS) -> dict:
    """Fon kodu -> gunluk fiyat serisi (TRY). Bulunamayan fon None doner.
    YAT -> EMK -> BYF sirasiyla denenir."""
    from tefas import Crawler

    crawler = Crawler()
    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=years) + pd.DateOffset(days=1)
    result = {}
    for code in fund_codes:
        series = None
        for kind in ["YAT", "EMK", "BYF"]:
            try:
                df = crawler.fetch(start=start.strftime("%Y-%m-%d"),
                                   end=end.strftime("%Y-%m-%d"),
                                   name=code, columns=["date", "price"], kind=kind)
                if df is not None and not df.empty:
                    s = df.set_index("date")["price"].astype(float)
                    s.index = pd.to_datetime(s.index)
                    s = s[s > 0]
                    series = s[~s.index.duplicated(keep="last")].sort_index()
                    break
            except Exception:
                continue
        result[code] = series
    return result


def build_try_prices(positions: list, fx_ticker: str = "TRY=X") -> tuple:
    """positions: [{'name','ticker','currency','source'}] ->
    (TL bazli fiyat cercevesi, guncel kur, son yerel fiyatlar, veri bulunamayanlar)."""
    yahoo = [p for p in positions if p.get("source", "yahoo") == "yahoo"
             and p["ticker"] != GRAM_GOLD_TICKER]
    gram = [p for p in positions if p["ticker"] == GRAM_GOLD_TICKER]
    tefas = [p for p in positions if p.get("source") == "tefas"]

    needed = {p["ticker"] for p in yahoo} | {fx_ticker}
    if gram:
        needed.add(GOLD_OUNCE_TICKER)
    tickers = tuple(sorted(needed))
    raw = fetch_yahoo_prices(tickers)

    if fx_ticker not in raw.columns or raw[fx_ticker].dropna().empty:
        raise RuntimeError("USD/TRY kuru çekilemedi.")
    usdtry = raw[fx_ticker].ffill()
    fx_now = float(usdtry.dropna().iloc[-1])

    prices_try = pd.DataFrame(index=raw.index)
    last_native, failed = {}, []

    for p in yahoo:
        t = p["ticker"]
        if t not in raw.columns or raw[t].dropna().empty:
            failed.append(p["name"])
            continue
        last_native[p["name"]] = float(raw[t].dropna().iloc[-1])
        prices_try[p["name"]] = raw[t] * usdtry if p["currency"] == "USD" else raw[t]

    for p in gram:
        if GOLD_OUNCE_TICKER not in raw.columns or raw[GOLD_OUNCE_TICKER].dropna().empty:
            failed.append(p["name"])
            continue
        series = raw[GOLD_OUNCE_TICKER] * usdtry / OUNCE_TO_GRAM
        last_native[p["name"]] = float(series.dropna().iloc[-1])
        prices_try[p["name"]] = series

    if tefas:
        fund_data = fetch_tefas_funds(tuple(sorted(p["ticker"] for p in tefas)))
        for p in tefas:
            s = fund_data.get(p["ticker"])
            if s is None or s.dropna().empty:
                failed.append(p["name"])
                continue
            last_native[p["name"]] = float(s.dropna().iloc[-1])
            prices_try = prices_try.join(s.rename(p["name"]), how="outer")

    return prices_try, fx_now, last_native, failed
