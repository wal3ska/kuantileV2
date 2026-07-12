"""Veri katmani soyutlamasi. Kaynak degisikligi (lisansli API'ye gecis)
yalnizca bu dosyayi degistirir; motor ve UI etkilenmez."""

import time
import pandas as pd
import yfinance as yf

YAHOO_START = "2000-01-01"
TEFAS_MAX_YEARS = 5


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
    yahoo = [p for p in positions if p.get("source", "yahoo") == "yahoo"]
    tefas = [p for p in positions if p.get("source") == "tefas"]

    tickers = tuple(sorted({p["ticker"] for p in yahoo} | {fx_ticker}))
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
