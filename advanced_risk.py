"""Gelismis risk metrikleri: ES, VaR backtest, risk atfi, reel getiri,
kur ayristirmasi, likidite, EWMA/FHS, drawdown, yogunlasma, EVT,
kuyruk bagimliligi, HRP, stil analizi.

Tasarim ilkesi: her fonksiyon veri yetersizse None doner, exception
firlatmaz (analiz asla gelismis metrik yuzunden bloklanmaz).
"""

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

_N = NormalDist()


# ---------- 1) Expected Shortfall + VaR backtest ----------

def expected_shortfall(port_rets: pd.Series, confidence: float) -> float | None:
    """Kosullu kayip beklentisi: VaR esigini asan gunlerin ortalamasi (negatif)."""
    r = port_rets.dropna()
    if len(r) < 60:
        return None
    q = float(np.quantile(r, 1 - confidence))
    tail = r[r <= q]
    if tail.empty:
        return None
    return float(tail.mean())


def _chi2_1_pvalue(lr: float) -> float:
    """1 serbestlik dereceli ki-kare icin p-degeri (scipy'siz)."""
    if lr <= 0:
        return 1.0
    return 1.0 - math.erf(math.sqrt(lr / 2))


def var_backtest(port_rets: pd.Series, confidence: float,
                 test_days: int = 250, min_window: int = 250) -> dict | None:
    """Kayan pencere 1 gunluk VaR backtest'i: son test_days gunun her biri icin
    onceki gozlemlerden (en fazla 500) VaR hesaplanir, ihlaller sayilir.
    Kupiec POF + Christoffersen bagimsizlik + Basel trafik isigi."""
    r = port_rets.dropna()
    if len(r) < min_window + test_days:
        return None
    p = 1 - confidence
    viol = []
    vals = r.values
    for t in range(len(vals) - test_days, len(vals)):
        window = vals[max(0, t - 500):t]
        var_t = np.quantile(window, p)
        viol.append(1 if vals[t] < var_t else 0)
    n, x = len(viol), int(sum(viol))

    # Kupiec POF (LR_uc)
    def _ll(prob, k, m):
        # k ihlal, m ihlal olmayan; 0*log0 = 0
        out = 0.0
        if m:
            out += m * math.log(max(1 - prob, 1e-12))
        if k:
            out += k * math.log(max(prob, 1e-12))
        return out
    lr_uc = -2 * (_ll(p, x, n - x) - _ll(x / n if n else 0, x, n - x))
    kupiec_p = _chi2_1_pvalue(lr_uc)

    # Christoffersen bagimsizlik (ihlaller kumeleniyor mu)
    n00 = n01 = n10 = n11 = 0
    for a, b in zip(viol[:-1], viol[1:]):
        if a == 0 and b == 0:
            n00 += 1
        elif a == 0 and b == 1:
            n01 += 1
        elif a == 1 and b == 0:
            n10 += 1
        else:
            n11 += 1
    christ_p = None
    if x >= 2 and (n00 + n01) and (n10 + n11):
        pi01 = n01 / (n00 + n01)
        pi11 = n11 / (n10 + n11)
        pi = (n01 + n11) / (n00 + n01 + n10 + n11)
        lr_ind = -2 * ((_ll(pi, n01 + n11, n00 + n10))
                       - (_ll(pi01, n01, n00) + _ll(pi11, n11, n10)))
        christ_p = _chi2_1_pvalue(lr_ind)

    # Basel trafik isigi (250 gun, %99 icin esikler)
    scaled = x * 250 / n
    zone = "green" if scaled <= 4 else ("yellow" if scaled <= 9 else "red")
    return {
        "days": n, "violations": x, "expected": round(n * p, 1),
        "kupiec_p": kupiec_p, "christoffersen_p": christ_p, "basel_zone": zone,
    }


# ---------- 7) Ledoit-Wolf daraltma (sabit korelasyon hedefi) ----------

def ledoit_wolf_cov(returns: pd.DataFrame) -> np.ndarray:
    """Ledoit-Wolf (2004) sabit-korelasyon hedefine daraltilmis kovaryans.
    sklearn bagimliligi olmadan; tek varlikta orneklem kovaryansi doner."""
    X = returns.dropna().values
    t, n = X.shape
    S = np.cov(X, rowvar=False, ddof=0)
    if n == 1:
        return np.atleast_2d(S)
    Xc = X - X.mean(axis=0)
    std = np.sqrt(np.diag(S))
    denom = np.outer(std, std)
    denom[denom == 0] = 1e-12
    R = S / denom
    rbar = (R.sum() - n) / (n * (n - 1))
    F = rbar * denom
    np.fill_diagonal(F, np.diag(S))
    # pi: orneklem kovaryansinin varyansi
    Y = Xc ** 2
    pi_mat = (Y.T @ Y) / t - S ** 2
    pi_hat = pi_mat.sum()
    # rho: hedefle kovaryans terimi (kosegen + kosegen disi yaklasik)
    rho_diag = np.trace(pi_mat)
    theta = ((Xc ** 3).T @ Xc) / t - np.outer(np.diag(S), np.ones(n)) * S
    np.fill_diagonal(theta, 0)
    rho_off = rbar * ((1 / np.outer(std, std + 1e-12)) * theta * std[None, :]).sum()
    rho_hat = rho_diag + rho_off
    gamma = ((F - S) ** 2).sum()
    kappa = (pi_hat - rho_hat) / gamma if gamma > 0 else 0
    delta = max(0.0, min(1.0, kappa / t))
    return delta * F + (1 - delta) * S


# ---------- 2) Risk atfi: component + incremental VaR ----------

def risk_attribution(returns: pd.DataFrame, investments: dict,
                     confidence: float, total_var_pct: float) -> dict | None:
    """Euler ayristirmasi (LW kovaryansla, tarihsel VaR'a olceklenmis) +
    incremental VaR (pozisyon tamamen kapatilirsa)."""
    cols = [c for c in returns.columns if c in investments]
    if len(cols) < 2:
        return None
    rets = returns[cols].dropna()
    if len(rets) < 60:
        return None
    w = np.array([investments[c] for c in cols], dtype=float)
    total = w.sum()
    if total <= 0:
        return None
    cov = ledoit_wolf_cov(rets)
    port_var = float(w @ cov @ w)
    if port_var <= 0:
        return None
    total_var_tl = abs(total_var_pct) * total
    comp = w * (cov @ w) / port_var * total_var_tl  # toplami tam VaR_TL
    out = []
    port_full = rets.dot(w / total)
    var_full = float(np.quantile(port_full, 1 - confidence))
    for i, c in enumerate(cols):
        inc = None
        others = [x for x in cols if x != c]
        w_o = np.array([investments[x] for x in others])
        if w_o.sum() > 0:
            port_wo = rets[others].dot(w_o / w_o.sum())
            var_wo = float(np.quantile(port_wo, 1 - confidence))
            # ayni sermayeyle digerlerine dagitilmis halde VaR degisimi (TL)
            inc = abs(var_full) * total - abs(var_wo) * total
        out.append({
            "name": c,
            "weight": float(w[i] / total),
            "cvar_tl": float(comp[i]),
            "cvar_share": float(comp[i] / total_var_tl) if total_var_tl else None,
            "incremental_tl": inc,
        })
    out.sort(key=lambda d: -d["cvar_tl"])
    return {"components": out, "total_var_tl": total_var_tl}


# ---------- 3) Reel getiri ----------

def real_metrics(port_rets: pd.Series, cpi: pd.Series) -> dict | None:
    """TUFE ile deflate edilmis 12 aylik getiri + reel kayip olasiligi.
    v1: enflasyon beklentisi = son 12 aylik gerceklesme (sabit)."""
    r = port_rets.dropna()
    c = cpi.dropna().sort_index()
    if len(r) < 120 or len(c) < 13:
        return None
    infl_12m = float(c.iloc[-1] / c.iloc[-13] - 1)
    nom_12m = float(np.exp(r.tail(252).sum()) - 1)
    real_12m = (1 + nom_12m) / (1 + infl_12m) - 1
    mu = float(r.tail(504).mean()) * 252
    sigma = float(r.tail(504).std()) * math.sqrt(252)
    prob = None
    if sigma > 0:
        prob = float(_N.cdf((math.log(1 + infl_12m) - mu) / sigma))
    return {
        "inflation_12m": infl_12m,
        "nominal_return_12m": nom_12m,
        "real_return_12m": real_12m,
        "prob_real_loss_12m": prob,
        "cpi_as_of": str(c.index[-1].date()),
    }


# ---------- 4) Kur ayristirmasi ----------

def fx_decomposition(returns: pd.DataFrame, fx_rets: pd.Series,
                     investments: dict, usd_names: set) -> dict | None:
    """Toplam varyansi yerel + kur + kovaryans olarak boler.
    USD'ye maruz varliklarin TL log getirisi = yerel log + kur log."""
    cols = [c for c in returns.columns if c in investments]
    if not cols:
        return None
    rets = returns[cols].join(fx_rets.rename("__fx__"), how="inner").dropna()
    if len(rets) < 120:
        return None
    total = sum(investments[c] for c in cols)
    w = {c: investments[c] / total for c in cols}
    usd_share = sum(w[c] for c in cols if c in usd_names)
    fx = rets["__fx__"]
    port = sum(rets[c] * w[c] for c in cols)
    fx_part = fx * usd_share
    local_part = port - fx_part
    v_p, v_l, v_f = float(port.var()), float(local_part.var()), float(fx_part.var())
    cov2 = v_p - v_l - v_f
    if v_p <= 0:
        return None
    return {
        "usd_exposure_share": usd_share,
        "local_share": v_l / v_p,
        "fx_share": v_f / v_p,
        "cov_share": cov2 / v_p,
    }


# ---------- 5) Likidite ayarli VaR ----------

def liquidity_var(positions_info: list, var_value_tl: float) -> dict | None:
    """Hacim bazli cikis suresi ve sqrt(T) olcekli LVaR.
    positions_info: [{name, value_tl, adv_tl|None, kind}] kind: equity|fund|liquid.
    Spread verisi olmadigi icin spread maliyeti dahil degildir (rehberde aciklanir)."""
    if not positions_info:
        return None
    total = sum(p["value_tl"] for p in positions_info)
    if total <= 0:
        return None
    rows, mult = [], 0.0
    for p in positions_info:
        if p["kind"] == "fund":
            t = 2.0  # TEFAS itfa suresi yaklasik
        elif p["kind"] == "liquid" or not p.get("adv_tl"):
            t = 1.0
        else:
            t = max(1.0, p["value_tl"] / (0.25 * p["adv_tl"]))
        share = p["value_tl"] / total
        mult += share * math.sqrt(t)
        rows.append({"name": p["name"], "days_to_exit": round(t, 1),
                     "value_share": share})
    rows.sort(key=lambda d: -d["days_to_exit"])
    return {"positions": rows, "lvar_multiplier": mult,
            "lvar_value_tl": var_value_tl * mult}


# ---------- 6) EWMA / FHS ----------

def ewma_fhs(port_rets: pd.Series, confidence: float, lam: float = 0.94) -> dict | None:
    """RiskMetrics EWMA volatilite + Filtered Historical Simulation VaR."""
    r = port_rets.dropna()
    if len(r) < 120:
        return None
    vals = r.values
    var0 = float(np.var(vals[:30]))
    sig2 = np.empty(len(vals))
    sig2[0] = var0 if var0 > 0 else 1e-8
    for i in range(1, len(vals)):
        sig2[i] = lam * sig2[i - 1] + (1 - lam) * vals[i - 1] ** 2
    sig = np.sqrt(np.maximum(sig2, 1e-12))
    sig_today = math.sqrt(lam * sig2[-1] + (1 - lam) * vals[-1] ** 2)
    z = vals / sig
    q = 1 - confidence
    var_ewma = _N.inv_cdf(q) * sig_today            # parametrik normal
    var_fhs = float(np.quantile(z[30:], q)) * sig_today  # dagilim-serbest
    return {
        "ewma_vol_ann": sig_today * math.sqrt(252),
        "var_ewma_pct": var_ewma,
        "var_fhs_pct": var_fhs,
        "lambda": lam,
    }


# ---------- 8) Drawdown seti ----------

def drawdown_stats(port_rets: pd.Series) -> dict | None:
    r = port_rets.dropna()
    if len(r) < 120:
        return None
    cum = np.exp(r.cumsum())
    peak = np.maximum.accumulate(cum)
    dd = cum / peak - 1
    max_dd = float(dd.min())
    years = len(r) / 252
    ann_ret = float(np.exp(r.sum()) ** (1 / years) - 1) if years > 0 else None
    calmar = ann_ret / abs(max_dd) if (ann_ret is not None and max_dd < 0) else None
    ulcer = float(np.sqrt((dd.values ** 2).mean()))
    # su altinda gecen sure (su anki) ve en uzun toparlanma
    under_now = 0
    for v in dd.values[::-1]:
        if v < 0:
            under_now += 1
        else:
            break
    longest = cur = 0
    for v in dd.values:
        cur = cur + 1 if v < 0 else 0
        longest = max(longest, cur)
    return {
        "max_drawdown": max_dd, "calmar": calmar, "ulcer_index": ulcer,
        "underwater_days_now": under_now, "longest_underwater_days": longest,
        "ann_return": ann_ret,
    }


# ---------- 9) Yogunlasma ----------

def concentration(returns: pd.DataFrame, investments: dict) -> dict | None:
    cols = [c for c in returns.columns if c in investments]
    if len(cols) < 2:
        return None
    rets = returns[cols].dropna()
    if len(rets) < 60:
        return None
    total = sum(investments[c] for c in cols)
    w = np.array([investments[c] / total for c in cols])
    hhi = float((w ** 2).sum())
    vols = rets.std().values
    cov = ledoit_wolf_cov(rets)
    port_vol = math.sqrt(max(float(w @ cov @ w), 1e-18))
    div_ratio = float((w * vols).sum() / port_vol)
    corr = rets.corr().values
    eig = np.linalg.eigvalsh(corr)
    eig = eig[eig > 1e-10]
    p = eig / eig.sum()
    enb = float(np.exp(-(p * np.log(p)).sum()))
    return {
        "hhi": hhi, "effective_positions": 1 / hhi,
        "diversification_ratio": div_ratio, "effective_bets": enb,
        "n_assets": len(cols),
    }


# ---------- 10) EVT: GPD kuyruk (PWM tahmini) ----------

def evt_tail(port_rets: pd.Series, threshold_q: float = 0.95) -> dict | None:
    """Kayiplarin %95 esigini asan kismina Genellestirilmis Pareto uydurur
    (Hosking-Wallis PWM). VaR/ES 99.5 ve kuyruk indeksi doner."""
    r = port_rets.dropna()
    if len(r) < 500:
        return None
    losses = -r.values
    u = float(np.quantile(losses, threshold_q))
    y = np.sort(losses[losses > u] - u)
    nu = len(y)
    if nu < 30:
        return None
    n = len(losses)
    pi = (np.arange(1, nu + 1) - 0.35) / nu
    a0 = float(y.mean())
    a1 = float(((1 - pi) * y).mean())
    if a0 - 2 * a1 <= 0:
        return None
    kappa = a0 / (a0 - 2 * a1) - 2
    xi = -kappa
    beta = 2 * a0 * a1 / (a0 - 2 * a1)
    if xi >= 0.95 or beta <= 0:
        return None
    q = 0.995
    var995 = u + (beta / xi) * (((n / nu) * (1 - q)) ** (-xi) - 1) if abs(xi) > 1e-6 \
        else u + beta * math.log((n / nu) / (1 - q))
    es995 = (var995 + beta - xi * u) / (1 - xi)
    return {
        "tail_index": xi, "threshold_pct": u, "exceedances": nu,
        "var995_pct": -var995, "es995_pct": -es995,
    }


# ---------- 11) Ampirik kuyruk bagimliligi ----------

def tail_dependence(returns: pd.DataFrame, q: float = 0.05) -> dict | None:
    """Cift bazinda alt kuyruk bagimliligi: iki varligin ayni gun en kotu
    %5'lik dilimde olma olasiligi (bagimsizlikta ~%5). t-copula'nin
    parametrik varsayimlari yerine dogrudan ampirik olcum."""
    rets = returns.dropna()
    if len(rets) < 300 or rets.shape[1] < 2:
        return None
    cols = list(rets.columns)
    pairs = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            a, b = rets[cols[i]], rets[cols[j]]
            qa, qb = a.quantile(q), b.quantile(q)
            both = int(((a <= qa) & (b <= qb)).sum())
            lam = both / (q * len(rets))
            pairs.append({"pair": f"{cols[i]} – {cols[j]}",
                          "lambda_lower": float(lam),
                          "pearson": float(a.corr(b))})
    pairs.sort(key=lambda d: -d["lambda_lower"])
    return {"pairs": pairs[:5], "q": q}


# ---------- 12) HRP ----------

def hrp_weights(returns: pd.DataFrame) -> dict | None:
    """Hierarchical Risk Parity (Lopez de Prado): korelasyon uzakligiyla
    tek-baglanti kumeleme, seriasyon, ozyinelemeli ikiye bolme."""
    rets = returns.dropna()
    if rets.shape[1] < 3 or len(rets) < 120:
        return None
    cols = list(rets.columns)
    corr = rets.corr().values
    cov = np.cov(rets.values, rowvar=False)
    dist = np.sqrt(np.maximum(0.5 * (1 - corr), 0))

    # tek-baglanti kumeleme -> yaprak sirasi
    clusters = [[i] for i in range(len(cols))]
    d = dist.copy()
    np.fill_diagonal(d, np.inf)
    active = list(range(len(cols)))
    merged = {i: [i] for i in range(len(cols))}
    while len(active) > 1:
        best, bi, bj = np.inf, None, None
        for ii in range(len(active)):
            for jj in range(ii + 1, len(active)):
                a, b = active[ii], active[jj]
                m = min(dist[x][y] for x in merged[a] for y in merged[b])
                if m < best:
                    best, bi, bj = m, a, b
        merged[bi] = merged[bi] + merged[bj]
        del merged[bj]
        active.remove(bj)
    order = merged[active[0]]

    # ozyinelemeli ikiye bolme, ters-varyans tahsisi
    w = np.ones(len(cols))

    def _cluster_var(idx):
        sub = cov[np.ix_(idx, idx)]
        iv = 1 / np.maximum(np.diag(sub), 1e-12)
        iv = iv / iv.sum()
        return float(iv @ sub @ iv)

    def _bisect(idx):
        if len(idx) <= 1:
            return
        half = len(idx) // 2
        left, right = idx[:half], idx[half:]
        v_l, v_r = _cluster_var(left), _cluster_var(right)
        alpha = 1 - v_l / (v_l + v_r) if (v_l + v_r) > 0 else 0.5
        for i in left:
            w[i] *= alpha
        for i in right:
            w[i] *= 1 - alpha
        _bisect(left)
        _bisect(right)

    _bisect(order)
    w = w / w.sum()
    return {"weights": {cols[i]: float(w[i]) for i in range(len(cols))}}


# ---------- 13) TEFAS stil analizi ----------

def style_analysis(fund_rets: pd.Series, factors: pd.DataFrame,
                   max_lag: int = 1) -> dict | None:
    """Sharpe stil analizi: kisitli regresyon (agirliklar >=0, toplam 1).
    TEFAS fiyati bir gun gecikmeli ilan edilir (T gunu fiyati T-1 degerlemesi);
    bu yuzden 0..max_lag gun kaydirma denenir, R2'si yuksek olan secilir.
    Projeksiyonlu gradyan inisiyle cozulur; R2, tracking error, IR doner."""
    best = None
    for lag in range(max_lag + 1):
        shifted = fund_rets.shift(-lag) if lag else fund_rets
        res = _style_fit(shifted.dropna(), factors)
        if res is not None:
            res["lag_days"] = lag
            if best is None or (res["r2"] or 0) > (best["r2"] or 0):
                best = res
    return best


def _style_fit(fund_rets: pd.Series, factors: pd.DataFrame) -> dict | None:
    df = factors.join(fund_rets.rename("__f__"), how="inner").dropna()
    if len(df) < 120:
        return None
    y = df["__f__"].values
    X = df.drop(columns="__f__").values
    names = [c for c in df.columns if c != "__f__"]
    k = X.shape[1]

    def _proj_simplex(v):
        u = np.sort(v)[::-1]
        css = np.cumsum(u)
        rho = np.nonzero(u * np.arange(1, k + 1) > (css - 1))[0]
        if len(rho) == 0:
            return np.ones(k) / k
        theta = (css[rho[-1]] - 1) / (rho[-1] + 1)
        return np.maximum(v - theta, 0)

    w = np.ones(k) / k
    lr = 1.0 / max(float(np.linalg.norm(X.T @ X, 2)), 1e-8)
    for _ in range(2000):
        grad = X.T @ (X @ w - y)
        w = _proj_simplex(w - lr * grad)
    resid = y - X @ w
    ss_res = float((resid ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
    te = float(resid.std()) * math.sqrt(252)
    alpha_ann = float(resid.mean()) * 252
    ir = alpha_ann / te if te > 0 else None
    return {
        "weights": {names[i]: float(w[i]) for i in range(k)},
        "r2": r2, "tracking_error_ann": te,
        "alpha_ann": alpha_ann, "information_ratio": ir,
        "observations": len(df),
    }
