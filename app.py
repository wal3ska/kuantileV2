import os

import requests
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px

import data_provider as dp
import risk_engine as engine

# SAYFA VE TEMA AYARLARI

st.set_page_config(page_title="Risk Terminali | Global", layout="wide", initial_sidebar_state="expanded")
plt.style.use('dark_background')

st.title("Portföy & Risk Terminali")
st.markdown("---")

# VARLIK EVRENİ

BIST_100 = [
    "AEFES", "AGHOL", "AHGAZ", "AKBNK", "AKCNS", "AKFGY", "AKSA", "AKSEN", "ALARK", "ALBRK",
    "ALFAS", "ARCLK", "ASELS", "ASTOR", "BERA", "BIENY", "BIMAS", "BRSAN", "BRYAT", "BUCIM",
    "CANTE", "CCOLA", "CEMTS", "CIMSA", "CWENE", "DOAS", "DOHOL", "ECILC", "EGEEN", "EKGYO",
    "ENJSA", "ENKAI", "EREGL", "EUPWR", "EUREN", "FROTO", "GARAN", "GENIL", "GESAN", "GLYHO",
    "GUBRF", "GWIND", "HALKB", "HEKTS", "IMASM", "INDES", "INVEO", "ISCTR", "ISGYO", "ISMEN",
    "IZENR", "KALES", "KARSN", "KCAER", "KCHOL", "KLSER", "KMPUR", "KONTR", "KONYA", "KOZAA",
    "KOZAL", "KRDMD", "KZBGY", "MAVI", "MGROS", "MIATK", "ODAS", "OTKAR", "OYAKC", "PENTA",
    "PETKM", "PGSUS", "PNLSN", "QUAGR", "SAHOL", "SASA", "SAYAS", "SISE", "SKBNK", "SMRTG",
    "SOKM", "TABGD", "TAVHL", "TCELL", "THYAO", "TKFEN", "TOASO", "TSKB", "TTKOM", "TTRAK",
    "TUKAS", "TUPRS", "ULKER", "VAKBN", "VESBE", "VESTL", "YEOTK", "YKBNK", "YYLGD", "ZOREN"
]

CRYPTO = {
    "Bitcoin (BTC)": "BTC-USD", "Ethereum (ETH)": "ETH-USD", "Solana (SOL)": "SOL-USD",
    "XRP": "XRP-USD", "BNB": "BNB-USD", "Cardano (ADA)": "ADA-USD",
    "Dogecoin (DOGE)": "DOGE-USD", "Avalanche (AVAX)": "AVAX-USD",
    "Polkadot (DOT)": "DOT-USD", "Chainlink (LINK)": "LINK-USD"
}

US_STOCKS = {
    "Apple (AAPL)": "AAPL", "Microsoft (MSFT)": "MSFT", "Nvidia (NVDA)": "NVDA",
    "Alphabet (GOOGL)": "GOOGL", "Amazon (AMZN)": "AMZN", "Meta (META)": "META",
    "Tesla (TSLA)": "TSLA", "Berkshire (BRK-B)": "BRK-B", "JPMorgan (JPM)": "JPM",
    "Visa (V)": "V", "Johnson & Johnson (JNJ)": "JNJ", "Exxon (XOM)": "XOM",
    "Coca-Cola (KO)": "KO", "McDonald's (MCD)": "MCD", "Disney (DIS)": "DIS",
    "Netflix (NFLX)": "NFLX", "AMD": "AMD", "Intel (INTC)": "INTC",
    "Boeing (BA)": "BA", "Caterpillar (CAT)": "CAT", "Goldman Sachs (GS)": "GS",
    "Palantir (PLTR)": "PLTR", "Uber (UBER)": "UBER", "Coinbase (COIN)": "COIN"
}

COMMODITIES = {
    "Altın (ONS)": "GC=F", "Gümüş (ONS)": "SI=F", "Brent Petrol": "BZ=F",
    "WTI Petrol": "CL=F", "Doğalgaz": "NG=F", "Bakır": "HG=F"
}

INDICES = {
    "S&P 500": "^GSPC", "Nasdaq Composite": "^IXIC", "Nasdaq 100": "^NDX",
    "Dow Jones (DJIA)": "^DJI", "BIST 100": "XU100.IS", "BIST 30": "XU030.IS"
}

ASSET_INFO = {}
for h in BIST_100:
    ASSET_INFO[h] = {"ticker": f"{h}.IS", "cur": "TRY", "cat": "BIST"}
for n, t in CRYPTO.items():
    ASSET_INFO[n] = {"ticker": t, "cur": "USD", "cat": "Kripto"}
for n, t in US_STOCKS.items():
    ASSET_INFO[n] = {"ticker": t, "cur": "USD", "cat": "ABD Hisse"}
for n, t in COMMODITIES.items():
    ASSET_INFO[n] = {"ticker": t, "cur": "USD", "cat": "Emtia"}
for n, t in INDICES.items():
    ASSET_INFO[n] = {"ticker": t, "cur": "TRY" if t.endswith(".IS") else "USD", "cat": "Endeks"}

# 1. YAN MENÜ

API_URL = os.getenv("API_URL", "http://localhost:8000")

def api_call(method, path, json=None, auth=False):
    headers = {"Authorization": f"Bearer {st.session_state.get('token','')}"} if auth else {}
    try:
        return requests.request(method, f"{API_URL}{path}", json=json, headers=headers, timeout=20)
    except requests.RequestException:
        return None

BASE_ASSET_NAMES = set(ASSET_INFO.keys())

def _ensure_custom(state_key, code):
    lst = st.session_state.setdefault(state_key, [])
    if code not in lst:
        lst.append(code)
    st.session_state[f"keep_{state_key}"] = lst.copy()

def apply_loaded_portfolio(data):
    base_selected = []
    for p in data.get("positions", []):
        name = p["name"]
        if p.get("source") == "tefas":
            _ensure_custom("custom_tefas", p["ticker"])
        elif name in BASE_ASSET_NAMES:
            base_selected.append(name)
        elif p["currency"] == "TRY":
            _ensure_custom("custom_bist", p["ticker"].replace(".IS", ""))
        else:
            _ensure_custom("custom_global", p["ticker"])
        st.session_state[f"q_{name}"] = float(p["quantity"])
        st.session_state[f"u_{name}"] = p.get("cost") is None
        st.session_state[f"c_{name}"] = float(p.get("cost") or 0.0)
    st.session_state["asset_select"] = base_selected
    bonds = data.get("bonds", [])
    st.session_state["bond_count"] = len(bonds)
    for i, b in enumerate(bonds):
        st.session_state[f"bn_{i}"] = b["name"]
        st.session_state[f"bc_{i}"] = b["currency"]
        st.session_state[f"bnom_{i}"] = float(b["nominal"])
        st.session_state[f"bp_{i}"] = float(b["price"])
        st.session_state[f"bk_{i}"] = float(b["coupon_rate"]) * 100
        st.session_state[f"bf_{i}"] = int(b["frequency"])
        st.session_state[f"by_{i}"] = float(b["years"])
        st.session_state[f"bu_{i}"] = b.get("cost") is None
        st.session_state[f"bcost_{i}"] = float(b.get("cost") or 0.0)
        st.session_state[f"bytm_{i}"] = float(b["ytm"]) * 100

st.sidebar.subheader("Hesap")
if "token" not in st.session_state:
    with st.sidebar.expander("Giriş Yap / Kayıt Ol"):
        auth_mode = st.radio("Mod", ["Giriş", "Kayıt"], horizontal=True, label_visibility="collapsed", key="auth_mode")
        auth_email = st.text_input("E-posta", key="auth_email")
        auth_pw = st.text_input("Şifre (en az 8 karakter)", type="password", key="auth_pw")
        if auth_mode == "Kayıt":
            if st.button("Kayıt Ol", key="btn_register", use_container_width=True):
                r = api_call("POST", "/auth/register", {"email": auth_email, "password": auth_pw})
                if r is None:
                    st.error("Sunucuya ulaşılamadı.")
                elif r.status_code == 201:
                    st.success("Kayıt alındı! Doğrulama bağlantısı e-postanıza gönderildi.")
                else:
                    st.error(r.json().get("detail", "Kayıt başarısız."))
        else:
            if st.button("Giriş Yap", key="btn_login", use_container_width=True):
                r = api_call("POST", "/auth/login", {"email": auth_email, "password": auth_pw})
                if r is None:
                    st.error("Sunucuya ulaşılamadı.")
                elif r.status_code == 200:
                    st.session_state["token"] = r.json()["access_token"]
                    st.session_state["user_email"] = r.json()["email"]
                    pf = api_call("GET", "/portfolio", auth=True)
                    if pf is not None and pf.status_code == 200:
                        apply_loaded_portfolio(pf.json())
                    st.rerun()
                else:
                    st.error(r.json().get("detail", "Giriş başarısız."))
else:
    st.sidebar.caption(f"👤 {st.session_state['user_email']}")
    if "daily_mail" not in st.session_state:
        r = api_call("GET", "/auth/me", auth=True)
        st.session_state["daily_mail"] = (r.json().get("daily_mail", True)
                                          if r is not None and r.status_code == 200 else True)
    dm = st.sidebar.checkbox("📬 Günlük portföy özeti maili",
                             value=st.session_state["daily_mail"], key="dm_toggle")
    if dm != st.session_state["daily_mail"]:
        r = api_call("POST", "/auth/daily-mail", {"enabled": dm}, auth=True)
        if r is not None and r.status_code == 200:
            st.session_state["daily_mail"] = dm

st.sidebar.markdown("---")

st.sidebar.header("Portföy Yönetimi")

categories = ["BIST", "Kripto", "ABD Hisse", "Emtia", "Endeks"]
selected_cats = st.sidebar.multiselect("Kategori Filtresi:", categories, default=categories)

filtered_names = sorted([n for n, i in ASSET_INFO.items() if i["cat"] in selected_cats])

selected_display_names = st.sidebar.multiselect(
    "Varlık Seçiniz:",
    options=filtered_names,
    default=[],
    key="asset_select"
)

def custom_code_input(state_key, input_label, button_label, placeholder):
    if state_key not in st.session_state:
        st.session_state[state_key] = []
    text = st.text_input(input_label, placeholder=placeholder, key=f"in_{state_key}")
    if st.button(button_label, key=f"btn_{state_key}"):
        for code in [c.strip().upper() for c in text.split(",") if c.strip()]:
            if code not in st.session_state[state_key]:
                st.session_state[state_key].append(code)
        st.session_state[f"keep_{state_key}"] = st.session_state[state_key].copy()
    if st.session_state[state_key]:
        if f"keep_{state_key}" not in st.session_state:
            st.session_state[f"keep_{state_key}"] = st.session_state[state_key].copy()
        kept = st.multiselect("Eklenenler (kaldırmak için işareti silin):",
                              options=st.session_state[state_key],
                              key=f"keep_{state_key}")
        st.session_state[state_key] = list(kept)
    return st.session_state[state_key]

with st.sidebar.expander("Listede Olmayan Varlık Ekle"):
    bist_codes = custom_code_input("custom_bist", "BIST Kodu (virgülle ayırın)", "BIST Ekle", "ör: MPARK, EBEBK")
    global_codes = custom_code_input("custom_global", "Global Sembol (Yahoo formatı)", "Sembol Ekle", "ör: LLY, SHIB-USD")

for code in bist_codes:
    name = code.replace(".IS", "")
    if name not in ASSET_INFO:
        ASSET_INFO[name] = {"ticker": f"{name}.IS", "cur": "TRY", "cat": "BIST"}
    if name not in selected_display_names:
        selected_display_names.append(name)

for code in global_codes:
    if code not in ASSET_INFO:
        ASSET_INFO[code] = {"ticker": code, "cur": "USD", "cat": "Global"}
    if code not in selected_display_names:
        selected_display_names.append(code)

with st.sidebar.expander("TEFAS Fonu Ekle"):
    st.caption("Fon kodunu giriniz (ör: AFT, TCD, YAC). Veri TEFAS'tan çekilir, en fazla 5 yıl geriye gider.")
    fund_codes = custom_code_input("custom_tefas", "Fon Kodu (virgülle ayırın)", "Fon Ekle", "ör: AFT, MAC, TCD")

for code in fund_codes:
    name = f"{code} (Fon)"
    if name not in ASSET_INFO:
        ASSET_INFO[name] = {"ticker": code, "cur": "TRY", "cat": "TEFAS Fon"}
    if name not in selected_display_names:
        selected_display_names.append(name)

# POZİSYON GİRİŞİ

positions = {}
if selected_display_names:
    st.sidebar.markdown("---")
    st.sidebar.subheader("Pozisyon Girişi")
    st.sidebar.caption("Adet ve maliyeti varlığın kendi para biriminde giriniz.")

    for name in selected_display_names:
        cur = ASSET_INFO[name]["cur"]
        st.sidebar.markdown(f"**{name}** ({cur})")
        c1, c2 = st.sidebar.columns(2)
        qty = c1.number_input("Adet", min_value=0.0, value=0.0, step=1.0, format="%.6f", key=f"q_{name}")
        cost_unknown = st.sidebar.checkbox("Maliyeti bilmiyorum", key=f"u_{name}")
        cost = c2.number_input(f"Maliyet ({cur})", min_value=0.0, value=0.0, step=1.0,
                               format="%.4f", key=f"c_{name}", disabled=cost_unknown)
        positions[name] = {"qty": qty, "cost": cost, "cost_unknown": cost_unknown}

# TAHVİL / BONO GİRİŞİ

st.sidebar.markdown("---")
st.sidebar.subheader("Tahvil / Bono")
bond_count = st.sidebar.number_input("Tahvil sayısı", min_value=0, max_value=5, step=1, key="bond_count")

bond_inputs = []
for i in range(int(bond_count)):
    with st.sidebar.expander(f"Tahvil {i+1}", expanded=True):
        st.caption("Fiyatları 100 birim nominal başına giriniz. Örnek: 100 TL'lik tahvil 98,5 TL'den işlem görüyorsa 98.5 yazın.")
        b_name = st.text_input("İsim", value=f"Tahvil {i+1}", key=f"bn_{i}")
        b_cur = st.selectbox("Para Birimi", ["TRY", "USD"], key=f"bc_{i}")
        b_nominal = st.number_input(f"Nominal Tutar ({b_cur})", min_value=0.0, value=0.0, step=1000.0, key=f"bnom_{i}",
                                    help="Tahvilin üzerinde yazan anapara tutarı (vade sonunda geri alacağınız tutar).")
        b_price = st.number_input("Güncel Piyasa Fiyatı", min_value=0.0, value=100.0, step=0.1, format="%.3f", key=f"bp_{i}",
                                  help="Ekranda/aracı kurumda gördüğünüz kote fiyat. 100 nominal başına.")
        b_coupon = st.number_input("Yıllık Kupon Oranı (%)", min_value=0.0, value=0.0, step=0.25, format="%.2f", key=f"bk_{i}",
                                   help="Kuponsuz bono için 0 bırakın.")
        b_freq = st.selectbox("Kupon Sıklığı (yılda kaç ödeme)", [2, 1, 4], key=f"bf_{i}")
        b_years = st.number_input("Vadeye Kalan Süre (yıl)", min_value=0.05, value=2.0, step=0.25, format="%.2f", key=f"by_{i}")
        b_unknown = st.checkbox("Maliyeti bilmiyorum", key=f"bu_{i}")
        b_cost = st.number_input("Alış Fiyatınız", min_value=0.0, value=0.0, step=0.1,
                                 format="%.3f", key=f"bcost_{i}", disabled=b_unknown,
                                 help="Tahvili aldığınız fiyat, 100 nominal başına.")
        b_ytm = st.number_input("Vadeye Kadar Getiri - YTM (%)", min_value=0.0, value=40.0 if b_cur == "TRY" else 4.5,
                                step=0.25, format="%.2f", key=f"bytm_{i}",
                                help="Tahvilin güncel piyasa getirisi. Aracı kurum ekranında veya KAP'ta 'bileşik faiz' olarak görünür.")
        if b_nominal > 0:
            bond_inputs.append({
                "name": b_name, "cur": b_cur, "nominal": b_nominal, "price": b_price,
                "coupon": b_coupon / 100, "freq": b_freq, "years": b_years,
                "cost": b_cost, "cost_unknown": b_unknown,
                "ytm": b_ytm / 100
            })


if "token" in st.session_state:
    st.sidebar.markdown("---")
    sv_col, out_col = st.sidebar.columns(2)
    if sv_col.button("💾 Kaydet", use_container_width=True):
        payload = {
            "positions": [
                {"name": n, "ticker": ASSET_INFO[n]["ticker"],
                 "currency": ASSET_INFO[n]["cur"],
                 "source": "tefas" if ASSET_INFO[n]["cat"] == "TEFAS Fon" else "yahoo",
                 "category": ASSET_INFO[n]["cat"], "quantity": p["qty"],
                 "cost": None if (p["cost_unknown"] or p["cost"] <= 0) else p["cost"]}
                for n, p in positions.items() if p["qty"] > 0
            ],
            "bonds": [
                {"name": b["name"], "currency": b["cur"], "nominal": b["nominal"],
                 "price": b["price"], "coupon_rate": b["coupon"], "frequency": b["freq"],
                 "years": b["years"], "ytm": b["ytm"],
                 "cost": None if (b["cost_unknown"] or b["cost"] <= 0) else b["cost"]}
                for b in bond_inputs
            ],
        }
        r = api_call("PUT", "/portfolio", payload, auth=True)
        if r is not None and r.status_code == 200:
            st.sidebar.success("Portföy kaydedildi ✓")
        elif r is not None and r.status_code == 401:
            st.sidebar.error("Oturum süresi doldu, tekrar giriş yapın.")
            del st.session_state["token"]
        else:
            st.sidebar.error("Kaydedilemedi.")
    if out_col.button("Çıkış", use_container_width=True):
        for k in ["token", "user_email", "daily_mail"]:
            st.session_state.pop(k, None)
        st.rerun()

active_names = [n for n, p in positions.items() if p["qty"] > 0]

if not active_names and not bond_inputs:
    st.error("Lütfen en az bir varlık seçip adet giriniz veya bir tahvil tanımlayınız.")
    st.stop()

# 2. VERİ ÇEKME

yahoo_names = [n for n in active_names if ASSET_INFO[n]["cat"] != "TEFAS Fon"]
tefas_names = [n for n in active_names if ASSET_INFO[n]["cat"] == "TEFAS Fon"]

tickers_to_fetch = {ASSET_INFO[n]["ticker"] for n in yahoo_names} | {"TRY=X"}

@st.cache_data(ttl=900)
def fetch_data(ticker_list):
    return dp.fetch_yahoo_prices(ticker_list)

@st.cache_data(ttl=3600)
def fetch_tefas(fund_codes):
    return dp.fetch_tefas_funds(fund_codes)

def data_error(message):
    st.error(message)
    st.caption("Yahoo Finance, özellikle Streamlit Cloud gibi paylaşımlı sunucularda istekleri geçici olarak sınırlayabilir. Genellikle 1-2 dakika içinde düzelir.")
    if st.button("Yeniden Dene"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

try:
    raw_prices = fetch_data(tuple(sorted(tickers_to_fetch)))
except Exception:
    data_error("Piyasa verisi çekilemedi.")

if "TRY=X" not in raw_prices.columns or raw_prices["TRY=X"].dropna().empty:
    data_error("USD/TRY kuru çekilemedi. Kur olmadan TL bazlı analiz yapılamıyor.")

usdtry = raw_prices["TRY=X"].ffill()
fx_now = float(usdtry.dropna().iloc[-1])

prices_try = pd.DataFrame(index=raw_prices.index)
last_price_native = {}

valid_names = []
for name in yahoo_names:
    t = ASSET_INFO[name]["ticker"]
    if t not in raw_prices.columns or raw_prices[t].dropna().empty:
        st.warning(f"{name} için veri bulunamadı, analiz dışı bırakıldı.")
        continue
    series = raw_prices[t]
    last_price_native[name] = float(series.dropna().iloc[-1])
    if ASSET_INFO[name]["cur"] == "USD":
        prices_try[name] = series * usdtry
    else:
        prices_try[name] = series
    valid_names.append(name)

if tefas_names:
    try:
        fund_data = fetch_tefas(tuple(sorted(ASSET_INFO[n]["ticker"] for n in tefas_names)))
    except ImportError:
        fund_data = {}
        st.error("TEFAS fonları için 'tefas-crawler' kütüphanesi gerekli: pip install tefas-crawler")
    for name in tefas_names:
        s = fund_data.get(ASSET_INFO[name]["ticker"])
        if s is None or s.dropna().empty:
            st.warning(f"{name} için TEFAS'tan veri çekilemedi, analiz dışı bırakıldı. Fon kodunu kontrol edin.")
            continue
        last_price_native[name] = float(s.dropna().iloc[-1])
        prices_try = prices_try.join(s.rename(name), how="outer")
        valid_names.append(name)

current_returns = pd.DataFrame()
prices = pd.DataFrame()
if valid_names:
    prices = prices_try[valid_names]
    current_returns = engine.log_returns(prices)

# 3. TAHVİL DEĞERLEME

bonds = []
for b in bond_inputs:
    ytm = b["ytm"]
    fair_price, mac, mod = engine.bond_metrics(b["coupon"], ytm, b["years"], b["freq"])
    fx = fx_now if b["cur"] == "USD" else 1.0
    value_native = b["nominal"] * b["price"] / 100
    cost_native = np.nan if b["cost_unknown"] or b["cost"] <= 0 else b["nominal"] * b["cost"] / 100
    bonds.append({**b, "ytm_used": ytm, "fair_price": fair_price,
                  "macaulay": mac, "modified": mod, "fx": fx,
                  "value_native": value_native, "cost_native": cost_native,
                  "value_try": value_native * fx})

# 4. PORTFÖY DEĞERLEME (TRY BAZLI)

rows = []
for name in valid_names:
    info = ASSET_INFO[name]
    p = positions[name]
    fx = fx_now if info["cur"] == "USD" else 1.0
    value_native = p["qty"] * last_price_native[name]
    if p["cost_unknown"] or p["cost"] <= 0:
        cost_native, pnl_native, pnl_pct = np.nan, np.nan, np.nan
    else:
        cost_native = p["qty"] * p["cost"]
        pnl_native = value_native - cost_native
        pnl_pct = pnl_native / cost_native * 100
    rows.append({
        "Varlık": name, "Kategori": info["cat"], "PB": info["cur"],
        "Adet": p["qty"], "Ort. Maliyet": np.nan if p["cost_unknown"] else p["cost"],
        "Güncel Fiyat": last_price_native[name],
        "Maliyet Tutarı": cost_native, "Güncel Değer": value_native,
        "K/Z": pnl_native, "K/Z %": pnl_pct,
        "Değer (TRY)": value_native * fx,
        "K/Z (TRY)": pnl_native * fx if not np.isnan(pnl_native) else np.nan
    })

for b in bonds:
    pnl_native = np.nan if np.isnan(b["cost_native"]) else b["value_native"] - b["cost_native"]
    pnl_pct = np.nan if np.isnan(pnl_native) or b["cost_native"] <= 0 else pnl_native / b["cost_native"] * 100
    rows.append({
        "Varlık": b["name"], "Kategori": "Tahvil", "PB": b["cur"],
        "Adet": b["nominal"], "Ort. Maliyet": np.nan if b["cost_unknown"] else b["cost"],
        "Güncel Fiyat": b["price"],
        "Maliyet Tutarı": b["cost_native"], "Güncel Değer": b["value_native"],
        "K/Z": pnl_native, "K/Z %": pnl_pct,
        "Değer (TRY)": b["value_try"],
        "K/Z (TRY)": pnl_native * b["fx"] if not np.isnan(pnl_native) else np.nan
    })

pf = pd.DataFrame(rows).set_index("Varlık")
total_value_try = pf["Değer (TRY)"].sum()
pf["Ağırlık %"] = pf["Değer (TRY)"] / total_value_try * 100

market_value_try = pf.loc[pf["Kategori"] != "Tahvil", "Değer (TRY)"].sum()
bond_value_try = sum(b["value_try"] for b in bonds)

investments = pf["Değer (TRY)"].to_dict()
portfolio_daily_returns = pd.Series(dtype=float)
if not current_returns.empty and market_value_try > 0:
    weights_array = np.array([investments[n] / market_value_try for n in current_returns.columns])
    portfolio_daily_returns = current_returns.dot(weights_array)

# SEKMELİ YAPI

tab0, tab1, tab2, tab3 = st.tabs(["Portföy Takip", "VaR & Risk Profili", "Korelasyon & Çeşitlendirme", "Stres Testleri"])

# SEKME 0: PORTFÖY TAKİP

with tab0:
    known = pf.dropna(subset=["Maliyet Tutarı"])
    total_cost_try = (known["Maliyet Tutarı"] * known["PB"].map({"USD": fx_now, "TRY": 1.0})).sum()
    total_pnl_try = known["K/Z (TRY)"].sum()
    total_pnl_pct = (total_pnl_try / total_cost_try * 100) if total_cost_try > 0 else 0.0
    unknown_names = pf.index[pf["Maliyet Tutarı"].isna()].tolist()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Toplam Değer", f"₺ {total_value_try:,.0f}")
    m2.metric("Toplam Maliyet (bilinen)", f"₺ {total_cost_try:,.0f}")
    m3.metric("Kar / Zarar (bilinen)", f"₺ {total_pnl_try:,.0f}", f"{total_pnl_pct:+.2f}%")
    m4.metric("USD/TRY Kuru", f"{fx_now:.2f}")

    if unknown_names:
        st.caption(f"Maliyeti bilinmeyen pozisyonlar K/Z hesabına dahil edilmedi ama risk analizine dahil: {', '.join(unknown_names)}")
    st.caption("Not: Dolar bazlı varlıkların maliyeti güncel kur ile TL'ye çevrilir; kur farkı kazancı K/Z'ye dahil değildir.")

    st.markdown("---")

    left, right = st.columns([3, 2])

    with left:
        st.subheader("Pozisyonlar")
        display_df = pf[["Kategori", "PB", "Adet", "Ort. Maliyet", "Güncel Fiyat", "Güncel Değer", "K/Z", "K/Z %", "Değer (TRY)", "Ağırlık %"]]
        st.dataframe(
            display_df.style
            .format({
                "Adet": "{:,.4f}", "Ort. Maliyet": "{:,.2f}", "Güncel Fiyat": "{:,.2f}",
                "Güncel Değer": "{:,.2f}", "K/Z": "{:,.2f}", "K/Z %": "{:+.2f}%",
                "Değer (TRY)": "₺{:,.0f}", "Ağırlık %": "{:.1f}%"
            }, na_rep="—")
            .map(lambda v: "color: #00cc96" if isinstance(v, (int, float)) and v > 0 else ("color: #ff4b4b" if isinstance(v, (int, float)) and v < 0 else ""), subset=["K/Z", "K/Z %"]),
            use_container_width=True
        )

    with right:
        st.subheader("Portföy Dağılımı")
        fig_pie = px.pie(
            pf.reset_index(), values="Değer (TRY)", names="Varlık", hole=0.45,
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        fig_pie.update_traces(textinfo="percent+label")
        fig_pie.update_layout(paper_bgcolor="rgba(0,0,0,0)", showlegend=False, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig_pie, use_container_width=True)

        cat_alloc = pf.groupby("Kategori")["Değer (TRY)"].sum().reset_index()
        fig_cat = px.pie(cat_alloc, values="Değer (TRY)", names="Kategori", hole=0.45)
        fig_cat.update_traces(textinfo="percent+label")
        fig_cat.update_layout(paper_bgcolor="rgba(0,0,0,0)", showlegend=False, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig_cat, use_container_width=True)

# SEKME 1: VaR & RİSK PROFİLİ

with tab1:
    if not portfolio_daily_returns.empty:
        var_99_percentage = engine.historical_var(portfolio_daily_returns, 0.99)
        var_99_value = market_value_try * var_99_percentage

        col1, col2, col3 = st.columns(3)
        col1.metric("Piyasa Riskine Tabi Tutar", f"₺ {market_value_try:,.0f}")
        col2.metric("Maksimum Beklenen Kayıp (99% VaR)", f"₺ {var_99_value:,.0f}", f"{var_99_percentage*100:+.2f}%", delta_color="normal")
        col3.metric("Normal Gün İhtimali", "%99")

        st.caption("Not: Tarihsel VaR yalnızca piyasa fiyat serisi olan varlıkları kapsar. Dolar bazlı seriler USD/TRY ile TL'ye çevrildiğinden kur riski dahildir. Tahvil faiz riski aşağıda durasyon ile ayrıca ölçülür.")

        st.markdown("---")
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.hist(portfolio_daily_returns, bins=80, alpha=0.7, color='#1f77b4', edgecolor='black')
        ax.axvline(x=var_99_percentage, color='#ff4b4b', linestyle='dashed', linewidth=2, label=f'VaR (%1 Eşik): %{var_99_percentage*100:.2f}')
        ax.set_title("Günlük Portföy Getirileri Dağılımı (TRY Bazlı)", color='white')
        ax.set_xlabel("Günlük Getiri", color='white')
        ax.set_ylabel("Frekans", color='white')
        ax.legend()
        ax.grid(True, alpha=0.1)
        st.pyplot(fig)
    else:
        st.info("Portföyde piyasa fiyat serisi olan varlık bulunmadığı için tarihsel VaR hesaplanamadı.")

    if bonds:
        st.markdown("---")
        st.subheader("Tahvil Faiz Riski (Durasyon Analizi)")

        bond_rows = []
        for b in bonds:
            dv01 = b["modified"] * b["value_try"] * 0.0001
            bond_rows.append({
                "Tahvil": b["name"], "PB": b["cur"], "YTM %": b["ytm_used"] * 100,
                "Hesaplanan Fiyat": b["fair_price"],
                "Piyasa Fiyatı": b["price"], "Macaulay D.": b["macaulay"],
                "Modified D.": b["modified"], "DV01 (₺)": dv01, "Değer (TRY)": b["value_try"]
            })
        bond_df = pd.DataFrame(bond_rows).set_index("Tahvil")

        w_mod = (bond_df["Modified D."] * bond_df["Değer (TRY)"]).sum() / bond_value_try
        total_dv01 = bond_df["DV01 (₺)"].sum()
        pf_mod = w_mod * bond_value_try / total_value_try

        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Tahvil Sepeti Değeri", f"₺ {bond_value_try:,.0f}")
        b2.metric("Ağırlıklı Modified Duration", f"{w_mod:.2f} yıl")
        b3.metric("Toplam DV01", f"₺ {total_dv01:,.0f}")
        b4.metric("Portföy Düzeyi Duration Katkısı", f"{pf_mod:.2f} yıl")

        st.dataframe(
            bond_df.style.format({
                "YTM %": "{:.2f}", "Hesaplanan Fiyat": "{:.3f}", "Piyasa Fiyatı": "{:.3f}",
                "Macaulay D.": "{:.3f}", "Modified D.": "{:.3f}",
                "DV01 (₺)": "₺{:,.2f}", "Değer (TRY)": "₺{:,.0f}"
            }),
            use_container_width=True
        )

        st.markdown("**Faiz Şoku Senaryoları (paralel kayma, durasyon yaklaşımı)**")
        shocks = [-100, 100, 300, 500]
        s_cols = st.columns(len(shocks))
        for col, bps in zip(s_cols, shocks):
            impact = -w_mod * (bps / 10000) * bond_value_try
            col.metric(f"{bps:+d} bp", f"₺ {impact:,.0f}", f"{impact / bond_value_try * 100:+.2f}%", delta_color="normal")

        st.caption("DV01: faizde 1 baz puanlık (0,01%) artışın tahvil sepetinde yarattığı yaklaşık TL kaybı. Şok senaryoları basitleştirilmiş durasyon yaklaşımıdır; büyük şoklarda gerçek kayıp bir miktar daha düşük olur. Hesaplanan Fiyat, girdiğiniz YTM ile tahvilin olması gereken fiyatıdır — Piyasa Fiyatından belirgin sapıyorsa girdiğiniz YTM tahvilin gerçek getirisiyle uyumsuz demektir.")

# SEKME 2: KORELASYON VE ÇEŞİTLENDİRME

with tab2:
    if current_returns.shape[1] >= 2:
        st.subheader("Portföy Çeşitlendirme Analizi")
        div = engine.diversification(current_returns, investments, 0.99)
        sum_individual_var = div["sum_individual_var"]
        var_99_value = div["portfolio_var"]
        diversification_benefit = div["benefit"]

        d_col1, d_col2, d_col3 = st.columns(3)
        d_col1.metric("Ayrık Toplam Risk", f"-₺ {abs(sum_individual_var):,.0f}")
        d_col2.metric("Portföy Riski", f"-₺ {abs(var_99_value):,.0f}")
        d_col3.metric("Çeşitlendirme Faydası", f"+₺ {diversification_benefit:,.0f}", delta_color="normal")

        st.markdown("---")
        st.subheader("Varlık Korelasyon Matrisi")
        corr_matrix = current_returns.corr()
        st.dataframe(corr_matrix.style.background_gradient(cmap='coolwarm', axis=None).format("{:.2f}"), use_container_width=True)
    else:
        st.info("Korelasyon analizi için piyasa verisi olan en az 2 varlık gereklidir.")

# SEKME 3: STRES TESTLERİ

with tab3:
    if not current_returns.empty:
        st.subheader("Tarihsel Çöküş Senaryoları")

        crash_scenarios = engine.CRASH_SCENARIOS

        region_filter = st.multiselect("Senaryo Bölgesi:", ["Türkiye", "Uluslararası"], default=["Türkiye", "Uluslararası"])

        for scenario_name, dates in crash_scenarios.items():
            if dates["region"] not in region_filter:
                continue

            res = engine.stress_test(prices, investments, dates["start"], dates["end"])
            if res is None:
                st.warning(f"[{scenario_name}] Portföyünüzdeki varlıklar bu tarihte işleme açık değildi.")
                continue

            cumulative_percentage_loss = res["cumulative_return"]
            monetary_loss = market_value_try * cumulative_percentage_loss
            missing_names = res["missing_assets"]

            with st.expander(f"[{dates['region']}] {scenario_name} ({dates['start']} - {dates['end']})", expanded=False):
                st.metric("Portföy Etkisi (piyasa varlıkları)", f"₺ {monetary_loss:,.0f}", f"{cumulative_percentage_loss*100:+.2f}%", delta_color="normal")
                if missing_names:
                    st.caption(f"Bilgi: {', '.join(missing_names)} o dönemde piyasada olmadığı için teste dahil edilmedi.")
    else:
        st.info("Stres testi için piyasa fiyat serisi olan varlık gereklidir.")
