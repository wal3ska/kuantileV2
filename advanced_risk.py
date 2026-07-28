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
                 min_train: int = 150, max_window: int = 500) -> dict | None:
    """Kayan pencere 1 gunluk VaR backtest'i, UC MODEL icin ayri ayri:
    historical (esit agirlikli tarihsel), ewma (RiskMetrics normal),
    fhs (filtrelenmis tarihsel). Her model icin son N gunun ihlalleri sayilir;
    Kupiec POF + Christoffersen bagimsizlik + Basel trafik isigi hesaplanir.
    Az veride pencere kisaltilir; en az 75 test gunu gerekir."""
    r = port_rets.dropna()
    vals = r.values
    n = len(vals)
    test_days = min(250, n - min_train)
    if test_days < 75:
        return None
    p = 1 - confidence

    # Kosullu EWMA volatilite (nedensel, tek gecis)
    sig2 = np.empty(n)
    v0 = float(np.var(vals[:30]))
    sig2[0] = v0 if v0 > 0 else 1e-8
    lam = 0.94
    for i in range(1, n):
        sig2[i] = lam * sig2[i - 1] + (1 - lam) * vals[i - 1] ** 2
    sig = np.sqrt(np.maximum(sig2, 1e-12))
    z = vals / sig
    zq = _N.inv_cdf(p)

    start = n - test_days
    models = {}
    for name in ("historical", "ewma", "fhs"):
        viol = []
        for t in range(start, n):
            lo = max(0, t - max_window)
            if name == "historical":
                var_t = np.quantile(vals[lo:t], p)
            elif name == "ewma":
                var_t = zq * sig[t]
            else:  # fhs
                var_t = np.quantile(z[max(30, lo):t], p) * sig[t]
            viol.append(1 if vals[t] < var_t else 0)
        models[name] = _score_violations(viol, p)
    return {"days": test_days, "confidence": confidence, "models": models}


def _score_violations(viol: list, p: float) -> dict:
    """Ihlal dizisinden Kupiec POF + Christoffersen + Basel bolgesi."""
    n, x = len(viol), int(sum(viol))

    def _ll(prob, k, m):
        out = 0.0
        if m:
            out += m * math.log(max(1 - prob, 1e-12))
        if k:
            out += k * math.log(max(prob, 1e-12))
        return out

    lr_uc = -2 * (_ll(p, x, n - x) - _ll(x / n if n else 0, x, n - x))
    kupiec_p = _chi2_1_pvalue(lr_uc)

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

    scaled = x * 250 / n  # Basel esikleri 250 gune gore
    zone = "green" if scaled <= 4 else ("yellow" if scaled <= 9 else "red")
    return {"violations": x, "expected": round(n * p, 1),
            "kupiec_p": kupiec_p, "christoffersen_p": christ_p, "basel_zone": zone}


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
    port_sigma = math.sqrt(port_var)
    out = []
    for i, c in enumerate(cols):
        # Incremental VaR (standart): pozisyon satilir, parasi nakde cikar;
        # kalan pozisyonlar DOGAL buyuklugunde kalir (yeniden dagitim yok).
        # Kovaryans temelli, ampirik kuantil gurultusu yok. Isaret:
        #   -  kapatinca VaR duser (risk kaynagi)   +  kapatinca VaR artar (koruyucu)
        inc = None
        idx_o = [j for j in range(len(cols)) if j != i]
        if idx_o:
            w_o = w[idx_o]
            cov_o = cov[np.ix_(idx_o, idx_o)]
            sigma_o = math.sqrt(max(float(w_o @ cov_o @ w_o), 0.0))
            if port_sigma > 0:
                inc = total_var_tl * sigma_o / port_sigma - total_var_tl
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

def fx_decomposition(returns: pd.DataFrame, fx_rets: pd.Series, investments: dict,
                     usd_names: set | None = None, fund_usd: float = 0.0) -> dict | None:
    """Toplam varyansi yerel + kur + kovaryans olarak boler. Kur maruziyeti
    YAPISAL alinir: gram altin ve USD cinsi varliklarin TL getirisi
    = yerel + kur (beta=1). Fonlarin DOLAYLI kur maruziyeti (fund_usd) stil
    analizinden gelir - fonlarin gunluk fiyat gecikmesi betayi bozacagi icin
    dogrudan regresyon degil. Kur oynakligi VE surukleme (drift) raporlanir:
    yonetilen deger kaybi rejiminde kur riski varyansta degil sürüklenmede birikir."""
    cols = [c for c in returns.columns if c in investments]
    if not cols:
        return None
    df = returns[cols].join(fx_rets.rename("__fx__"), how="inner").dropna()
    if len(df) < 120:
        return None
    total = sum(investments[c] for c in cols)
    w = {c: investments[c] / total for c in cols}
    fx = df["__fx__"]
    if float(fx.var()) <= 0:
        return None
    usd_direct = sum(w[c] for c in cols if usd_names and c in usd_names)
    usd_share = min(usd_direct + max(fund_usd, 0.0), 1.0)  # dogrudan + fon dolayli
    port = sum(df[c] * w[c] for c in cols)
    fx_part = usd_share * fx
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
        "fx_vol_ann": float(fx.std()) * math.sqrt(252),
        "fx_drift_ann": float(fx.mean()) * 252,
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
    tail_n = int(q * len(rets))  # her kuyrukta ~ gozlem sayisi
    pairs = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            a, b = rets[cols[i]], rets[cols[j]]
            qa, qb = a.quantile(q), b.quantile(q)
            both = int(((a <= qa) & (b <= qb)).sum())
            lam = both / (q * len(rets))
            pairs.append({"pair": f"{cols[i]} – {cols[j]}",
                          "lambda_lower": float(lam),
                          "co_exceedances": both,
                          "pearson": float(a.corr(b))})
    pairs.sort(key=lambda d: -d["lambda_lower"])
    # bagimsizlikta beklenen ortak asim sayisi (lambda ~ q degil, q*tail_n gibi)
    return {"pairs": pairs[:5], "q": q, "tail_obs": tail_n,
            "expected_co": round(q * tail_n, 1)}


# ---------- 12) HRP ----------

HRP_MIN_ANN_VOL = 0.05  # bunun altindaki varliklar nakit benzeri sayilir


def hrp_weights(returns: pd.DataFrame) -> dict | None:
    """Hierarchical Risk Parity (Lopez de Prado): korelasyon uzakligiyla
    tek-baglanti kumeleme, seriasyon, ozyinelemeli ikiye bolme.
    Nakit benzeri (cok dusuk oynaklikli) varliklar dagilim disinda tutulur;
    aksi halde ters-varyans tahsisi tum agirligi nakite yigar ve cikti
    anlamsizlasir. Nakit orani ayri bir karardir."""
    rets = returns.dropna()
    if rets.shape[1] < 2 or len(rets) < 120:
        return None
    ann_vol = rets.std() * np.sqrt(252)
    cash_like = [c for c in rets.columns if ann_vol[c] < HRP_MIN_ANN_VOL]
    rets = rets.drop(columns=cash_like)
    if rets.shape[1] < 2:
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
    return {"weights": {cols[i]: float(w[i]) for i in range(len(cols))},
            "excluded_cash_like": cash_like}


# ---------- Belirsizlik: Sharpe guven araligi (Lo) + PSR + mevduati yenme ----------

def _moments(x: np.ndarray):
    n = len(x)
    m, s = float(x.mean()), float(x.std())
    if s <= 0:
        return None
    z = (x - m) / s
    return n, m, s, float((z ** 3).mean()), float((z ** 4).mean())


def sharpe_confidence(port_rets: pd.Series, rf_annual: float,
                      benchmark_sr: float = 0.0) -> dict | None:
    """Sharpe nokta tahmininin belirsizligi. Lo (2002) standart hatasiyla
    %95 guven araligi + Probabilistic Sharpe Ratio (Bailey & Lopez de Prado):
    getirilerin carpiklik/basikligini hesaba katarak Sharpe'in benchmark_sr
    esigini gercekten astigina dair olasilik. benchmark_sr=0 -> 'mevduati
    (risksiz orani) risk-ayarli gercekten yeniyor mu'."""
    r = port_rets.dropna()
    if len(r) < 120:
        return None
    rf_d = math.log(1 + max(rf_annual, -0.99)) / 252
    mo = _moments((r - rf_d).values)
    if mo is None:
        return None
    n, mu, sd, skew, kurt = mo
    sr_d = mu / sd
    sr_ann = sr_d * math.sqrt(252)
    # Lo (2002) standart hatasi GUNLUK Sharpe uzerinden, sonra yilliklandirilir
    se_ann = math.sqrt((1 + 0.5 * sr_d ** 2) / n) * math.sqrt(252)
    sr_star_d = benchmark_sr / math.sqrt(252)
    denom = math.sqrt(max(1 - skew * sr_d + (kurt - 1) / 4 * sr_d ** 2, 1e-9))
    psr = float(_N.cdf((sr_d - sr_star_d) * math.sqrt(n - 1) / denom))
    return {
        "sharpe_ann": sr_ann,
        "se_ann": se_ann,
        "ci_low": sr_ann - 1.96 * se_ann,
        "ci_high": sr_ann + 1.96 * se_ann,
        "psr": psr,
        "observations": n,
        "skew": skew,
        "excess_kurtosis": kurt - 3,
    }


def beat_deposit_probability(port_rets: pd.Series, deposit_annual: float | None,
                             horizon_days: int = 252) -> dict | None:
    """12 ay sonunda portfoyun mevduatin ALTINDA kalma olasiligi. Iki
    belirsizlik birlikte: gerceklesme (12 ay sonucu rastgele) + PARAMETRE
    (Sharpe'in kendi SE'si). Nokta tahminden Phi(-z) yerine, Lo SE ile
    genisletilmis Phi(-z/sqrt(1+se^2)) - skordaki dürüstlestirmenin aynisi."""
    r = port_rets.dropna()
    n = len(r)
    if n < 120 or deposit_annual is None:
        return None
    rf_d = math.log(1 + max(deposit_annual, -0.99)) / 252
    mo = _moments((r - rf_d).values)
    if mo is None:
        return None
    _n, mu, sd, skew, kurt = mo
    sr_ann = (mu / sd) * math.sqrt(252)
    se_ann = math.sqrt((1 + 0.5 * (mu / sd) ** 2) / n) * math.sqrt(252)
    scale = math.sqrt(horizon_days / 252)
    z_point = sr_ann * scale
    z_adj = z_point / math.sqrt(1 + (se_ann * scale) ** 2)   # parametre belirsizligi
    return {
        "prob_below_deposit": float(_N.cdf(-z_adj)),          # belirsizlik entegre
        "prob_below_point": float(_N.cdf(-z_point)),          # nokta tahmin (kiyas)
        "deposit_annual": deposit_annual,
        "horizon_days": horizon_days,
    }


def pick_headline_var(backtest: dict | None, model_vars: dict) -> dict:
    """Manset VaR: backtest'i EN IYI gecen modelin VaR'i (yesil > sari > kirmizi,
    esitlikte Kupiec p yuksek). Boylece manset testi gecen modeli gosterir;
    tarihsel VaR karsilastirma satirinda kalir."""
    if not backtest or not backtest.get("models"):
        return {"model": "historical", "var_pct": model_vars.get("historical"),
                "basel_zone": None, "kupiec_p": None}
    rank = {"green": 2, "yellow": 1, "red": 0}
    name = max(backtest["models"],
               key=lambda m: (rank[backtest["models"][m]["basel_zone"]],
                              backtest["models"][m]["kupiec_p"]))
    m = backtest["models"][name]
    return {"model": name, "var_pct": model_vars.get(name, model_vars.get("historical")),
            "basel_zone": m["basel_zone"], "kupiec_p": m["kupiec_p"]}


def vol_regime(port_rets: pd.Series, lam: float = 0.94) -> dict | None:
    """Guncel EWMA volatilitenin KENDI tarihsel dagilimindaki yuzdelik dilimi.
    'Su an oynaklik kendi 3 yillik dagiliminin %20'inci yuzdeliginde' - tum
    sayfadaki sayilarin hangi rejimden geldigini tek cumlede soyler."""
    r = port_rets.dropna()
    vals = r.values
    n = len(vals)
    if n < 250:
        return None
    sig2 = np.empty(n)
    v0 = float(np.var(vals[:30]))
    sig2[0] = v0 if v0 > 0 else 1e-8
    for i in range(1, n):
        sig2[i] = lam * sig2[i - 1] + (1 - lam) * vals[i - 1] ** 2
    sig = np.sqrt(sig2[30:])
    cur = float(sig[-1])
    pct = float((sig <= cur).mean())
    return {"current_vol_ann": cur * math.sqrt(252), "percentile": pct,
            "median_vol_ann": float(np.median(sig)) * math.sqrt(252),
            "observations": len(sig)}


# ---------- Faktor sok izgarasi (hipotetik parametrik stres) ----------

FACTOR_SHOCKS = [
    {"name": "USD/TRY +%15", "shocks": {"USD/TRY": 0.15}},
    {"name": "BIST −%20", "shocks": {"BIST 100": -0.20}},
    {"name": "Gram altın −%10", "shocks": {"Altın (TL)": -0.10}},
    {"name": "Kur şoku + BIST düşüşü", "shocks": {"USD/TRY": 0.15, "BIST 100": -0.20}},
    {"name": "Risk-off (kur↑ BIST↓ altın↑)",
     "shocks": {"USD/TRY": 0.20, "BIST 100": -0.25, "Altın (TL)": 0.10}},
    {"name": "Global satış (S&P −%15, kur +%10)",
     "shocks": {"S&P 500 (TL)": -0.15, "USD/TRY": 0.10}},
]


def factor_betas(asset_rets: pd.Series, factors: pd.DataFrame,
                 max_lag: int = 0) -> tuple | None:
    """Varligin faktorlere OLS betalari (sabit terimli). Fonlarda 1 gunluk
    fiyat gecikmesi icin 0..max_lag kaydirma denenir, R2'si en iyi secilir.
    Doner: (r2, {faktor: beta}, lag) veya None."""
    best = None
    for lag in range(max_lag + 1):
        y = asset_rets.shift(-lag) if lag else asset_rets
        df = factors.join(y.rename("__y__"), how="inner").dropna()
        if len(df) < 120:
            continue
        cols = list(factors.columns)
        X = np.column_stack([np.ones(len(df)), df[cols].values])
        yv = df["__y__"].values
        coef, _, _, _ = np.linalg.lstsq(X, yv, rcond=None)
        pred = X @ coef
        ss_res = float(((yv - pred) ** 2).sum())
        ss_tot = float(((yv - yv.mean()) ** 2).sum())
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        if best is None or r2 > best[0]:
            best = (r2, dict(zip(cols, coef[1:])), lag)
    return best


def factor_shock_grid(port_betas: dict, market_value: float,
                      scenarios: list = FACTOR_SHOCKS) -> dict:
    """Portfoy faktor betalarina hipotetik soklar uygulanir. Tarihsel pencereye
    sormaz ('peg kopsa ne olur'), fonlarin gecmiste var olmamasindan etkilenmez.
    Soklar faktorun kendi getiri uzayindadir; korele faktorler icin yaklasiktir."""
    out = []
    for sc in scenarios:
        imp = sum(port_betas.get(f, 0.0) * s for f, s in sc["shocks"].items())
        out.append({"name": sc["name"], "impact_pct": imp,
                    "impact_tl": market_value * imp, "shocks": sc["shocks"]})
    out.sort(key=lambda d: d["impact_tl"])
    return {"scenarios": out, "betas": {k: round(v, 3) for k, v in port_betas.items()}}


# ---------- Risk sinifi (SRRI/TEFAS 1-7) + Kuantile Skoru ----------

# SRRI bantlari: haftalik getirilerin yillik volatilitesi (AB/SPK metodolojisi,
# TEFAS fon risk degeri de ayni yaklasimla hesaplanir).
SRRI_BANDS = [(0.005, 1), (0.02, 2), (0.05, 3), (0.10, 4), (0.15, 5), (0.25, 6)]


def srri_class(port_rets: pd.Series) -> dict | None:
    """Portfoyun 1-7 risk sinifi: gunluk getiriler haftaliga cevrilir,
    yillik volatilite SRRI bantlarina oturtulur."""
    r = port_rets.dropna()
    if len(r) < 120:
        return None
    weekly = r.resample("W").sum().dropna()
    if len(weekly) < 24:
        return None
    ann_vol = float(weekly.tail(260).std()) * math.sqrt(52)
    cls = 7
    for bound, c in SRRI_BANDS:
        if ann_vol < bound:
            cls = c
            break
    return {"risk_class": cls, "ann_vol_weekly": ann_vol,
            "weeks": int(min(len(weekly), 260))}


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def kuantile_score(sharpe_1y: float | None, blocks: dict) -> dict | None:
    """Kuantile Skoru (0-100): risk sinifi verili kabul edilir, o riskin ne
    kadar verimli tasindigi puanlanir. Tum bilesenler risk-ayarli oldugundan
    siniflar arasi karsilastirilabilir. Eksik bilesenlerde agirliklar kalanlara
    yeniden dagitilir."""
    comps: dict = {}

    # Sharpe bileseni: varsa nokta tahmin yerine %95 ALT guven sinirini kullan
    # (donem sansina karsi dürüst; friend geri bildirimi). -1 -> 0p, +1 -> 100p.
    ci = blocks.get("sharpe_ci")
    sr_for_score = ci["ci_low"] if ci and ci.get("ci_low") is not None else sharpe_1y
    if sr_for_score is not None:
        comps["sharpe"] = _clamp(50 + 50 * sr_for_score)

    conc = blocks.get("concentration")
    if conc:
        n = min(conc["n_assets"], 5)
        if n >= 2:
            comps["diversification"] = _clamp(
                (conc["effective_bets"] - 1) / (n - 1) * 100)

    es_b, evt_b = blocks.get("es"), blocks.get("evt")
    var_ref = blocks.get("_var_pct")
    if es_b and es_b.get("es_pct") and var_ref:
        # ES/VaR orani kuyruk kalinligi: 1.0 -> 100p, 1.8+ -> 0p
        ratio = es_b["es_pct"] / var_ref if var_ref else None
        if ratio and ratio > 0:
            comps["tail"] = _clamp((1.8 - ratio) / 0.8 * 100)

    bt = blocks.get("backtest")
    if bt and bt.get("models"):
        zones = [m["basel_zone"] for m in bt["models"].values()]
        best = "green" if "green" in zones else ("yellow" if "yellow" in zones else "red")
        comps["model"] = {"green": 100.0, "yellow": 50.0, "red": 0.0}[best]

    real = blocks.get("real")
    if real and real.get("prob_real_loss_12m") is not None:
        # reel kayip olasiligi 0 -> 100p, %60+ -> 0p
        comps["real"] = _clamp((0.6 - real["prob_real_loss_12m"]) / 0.6 * 100)

    dd = blocks.get("drawdown")
    if dd and dd.get("calmar") is not None:
        comps["drawdown"] = _clamp(dd["calmar"] / 2 * 100)

    if not comps:
        return None
    weights = {"sharpe": 35, "diversification": 20, "tail": 15,
               "model": 10, "real": 10, "drawdown": 10}
    total_w = sum(weights[k] for k in comps)
    score = sum(comps[k] * weights[k] for k in comps) / total_w
    return {
        "score": round(score, 1),
        "components": {k: round(v, 1) for k, v in comps.items()},
        "weights_used": {k: weights[k] for k in comps},
    }


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
