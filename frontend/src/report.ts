/* PDF raporu: markali, tum verileri asagi dogru duzenli sekilde iceren tam
   rapor HTML'i uretir ve tarayicinin "PDF olarak kaydet" motoruyla yazdirir.
   jsPDF yerine print kullanilir; Turkce karakterler ve tipografi kusursuz. */

import type { AnalyzeResponse, PositionIn } from "./api";
import { fmtNum, fmtPct, fmtTL } from "./api";
import type { Lang } from "./i18n";

type L = Record<keyof typeof LABELS["tr"], string>;

const LABELS = {
  tr: {
    subtitle: "Portföy & Risk Raporu",
    generated: "Oluşturulma",
    disclaimer: "Bu rapor yatırım danışmanlığı değildir. Fiyatlar son işlem gününe aittir.",
    page: "Sayfa",
    summary: "Özet",
    totalValue: "Toplam Değer",
    score: "Kuantile Skoru",
    riskClass: "Risk Sınıfı (TEFAS/SRRI)",
    valuation: "Varlıklar",
    colAsset: "Varlık", colLast: "Son Fiyat", colValue: "Değer (TL)",
    colPnl: "K/Z (TL)", colPnlPct: "K/Z %", colWeight: "Ağırlık",
    marketRisk: "Piyasa Riski",
    varHeadline: "VaR (manşet, FHS)", varHist: "VaR (tarihsel, karşılaştırma)",
    es: "Expected Shortfall", es975: "ES (%97,5, Basel)",
    obs: "gözlem", conf: "güven",
    sharpe: "Sharpe & Belirsizlik",
    sharpe1y: "Sharpe (1Y)", sharpe3y: "Sharpe (3Y)", sharpe5y: "Sharpe (5Y)",
    sharpeCI: "%95 güven aralığı", psr: "PSR (edge gerçek mi)",
    beatDep: "Bu yıl mevduatı geçme olasılığı",
    models: "Risk Modelleri & Backtest",
    colModel: "Model", colVaR: "VaR", colViol: "İhlal", colExp: "Beklenen",
    colKupiec: "Kupiec p", colZone: "Basel",
    mHist: "Tarihsel", mEwma: "EWMA", mFhs: "FHS", headlineTag: "(manşet)",
    attrib: "Risk Atfı (Component VaR)",
    colMoneyShare: "Para payı", colRiskShare: "Risk payı", colInc: "Kapatınca VaR Δ",
    concentration: "Yoğunlaşma & Çeşitlendirme",
    effPos: "Efektif pozisyon", effBets: "Efektif bağımsız bahis",
    divRatio: "Çeşitlendirme oranı", hhi: "HHI", divBenefit: "Çeşitlendirme faydası",
    volRegime: "Volatilite Rejimi",
    curVol: "Güncel oynaklık (yıllık)", volPct: "Tarihsel yüzdelik", medVol: "Medyan oynaklık",
    real: "Reel Getiri (enflasyon sonrası)",
    period: "Dönem", infl: "TÜFE", nom: "Nominal getiri", realRet: "Reel getiri",
    realLoss: "Reel kayıp olasılığı (12 ay)",
    fx: "Kur Ayrıştırması",
    fxExp: "USD'ye maruz pay", fxLocal: "Yerel varlık riski",
    fxCur: "Kur (USDTRY) riski", fxCov: "Kovaryans terimi",
    liquidity: "Likidite (çıkış süresi)",
    colExitDays: "Çıkış süresi (gün)", lvar: "Likidite ayarlı VaR", lvarMult: "çarpan",
    drawdown: "Drawdown",
    maxDd: "Maksimum drawdown", calmar: "Calmar", ulcer: "Ulcer endeksi",
    underwater: "Su altında (şu an / en uzun)", days: "gün",
    tail: "Kuyruk Riski",
    evtVar: "EVT VaR (%99,5)", evtEs: "EVT ES (%99,5)", tailIndex: "Kuyruk indeksi ξ",
    tailDep: "Kuyruk bağımlılığı (en yüksek çiftler)",
    colPair: "Çift", colLambda: "λ (alt kuyruk)", colPearson: "ρ (Pearson)",
    stress: "Tarihsel Stres Testleri",
    colScenario: "Senaryo", colImpact: "Etki (TL)", colReturn: "Getiri", colCoverage: "Kapsam",
    factorShock: "Faktör Şok Izgarası (hipotetik)",
    colNom: "Nominal", colReal: "Reel",
    betas: "Portföy faktör betaları",
    hrp: "HRP Önerilen Ağırlıklar",
    hrpExcluded: "Nakit benzeri (dağılım dışı)",
    style: "Fon Stil Analizi (TEFAS)",
    styleR2: "R²", styleTE: "İzleme hatası", styleIR: "Bilgi oranı", styleLag: "gecikme",
    styleLow: "düşük açıklama gücü",
    bond: "Tahvil Riski",
    bondDv01: "Toplam DV01", bondDur: "Ağırlıklı modified durasyon",
    colShock: "Şok", noData: "veri yok",
  },
  en: {
    subtitle: "Portfolio & Risk Report",
    generated: "Generated",
    disclaimer: "This report is not investment advice. Prices are as of the last trading day.",
    page: "Page",
    summary: "Summary",
    totalValue: "Total Value",
    score: "Kuantile Score",
    riskClass: "Risk Class (TEFAS/SRRI)",
    valuation: "Holdings",
    colAsset: "Asset", colLast: "Last Price", colValue: "Value (TRY)",
    colPnl: "P/L (TRY)", colPnlPct: "P/L %", colWeight: "Weight",
    marketRisk: "Market Risk",
    varHeadline: "VaR (headline, FHS)", varHist: "VaR (historical, comparison)",
    es: "Expected Shortfall", es975: "ES (97.5%, Basel)",
    obs: "obs", conf: "confidence",
    sharpe: "Sharpe & Uncertainty",
    sharpe1y: "Sharpe (1Y)", sharpe3y: "Sharpe (3Y)", sharpe5y: "Sharpe (5Y)",
    sharpeCI: "95% confidence interval", psr: "PSR (is the edge real)",
    beatDep: "Probability of beating the deposit this year",
    models: "Risk Models & Backtest",
    colModel: "Model", colVaR: "VaR", colViol: "Violations", colExp: "Expected",
    colKupiec: "Kupiec p", colZone: "Basel",
    mHist: "Historical", mEwma: "EWMA", mFhs: "FHS", headlineTag: "(headline)",
    attrib: "Risk Attribution (Component VaR)",
    colMoneyShare: "Money share", colRiskShare: "Risk share", colInc: "VaR if closed",
    concentration: "Concentration & Diversification",
    effPos: "Effective positions", effBets: "Effective independent bets",
    divRatio: "Diversification ratio", hhi: "HHI", divBenefit: "Diversification benefit",
    volRegime: "Volatility Regime",
    curVol: "Current volatility (annual)", volPct: "Historical percentile", medVol: "Median volatility",
    real: "Real Return (after inflation)",
    period: "Period", infl: "CPI", nom: "Nominal return", realRet: "Real return",
    realLoss: "Prob. of real loss (12m)",
    fx: "Currency Decomposition",
    fxExp: "USD-exposed share", fxLocal: "Local asset risk",
    fxCur: "FX (USDTRY) risk", fxCov: "Covariance term",
    liquidity: "Liquidity (days to exit)",
    colExitDays: "Days to exit", lvar: "Liquidity-adjusted VaR", lvarMult: "multiplier",
    drawdown: "Drawdown",
    maxDd: "Maximum drawdown", calmar: "Calmar", ulcer: "Ulcer index",
    underwater: "Underwater (now / longest)", days: "days",
    tail: "Tail Risk",
    evtVar: "EVT VaR (99.5%)", evtEs: "EVT ES (99.5%)", tailIndex: "Tail index ξ",
    tailDep: "Tail dependence (top pairs)",
    colPair: "Pair", colLambda: "λ (lower tail)", colPearson: "ρ (Pearson)",
    stress: "Historical Stress Tests",
    colScenario: "Scenario", colImpact: "Impact (TRY)", colReturn: "Return", colCoverage: "Coverage",
    factorShock: "Factor Shock Grid (hypothetical)",
    colNom: "Nominal", colReal: "Real",
    betas: "Portfolio factor betas",
    hrp: "HRP Suggested Weights",
    hrpExcluded: "Cash-like (excluded)",
    style: "Fund Style Analysis (TEFAS)",
    styleR2: "R²", styleTE: "Tracking error", styleIR: "Information ratio", styleLag: "lag",
    styleLow: "low explanatory power",
    bond: "Bond Risk",
    bondDv01: "Total DV01", bondDur: "Weighted modified duration",
    colShock: "Shock", noData: "no data",
  },
} as const;

/* ---------- yardimcilar ---------- */

const esc = (s: unknown) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));

const dc = (v: number | null | undefined, text: string) =>
  v == null ? `<span class="dim">—</span>` : `<span class="${v >= 0 ? "up" : "down"}">${text}</span>`;

const pctNS = (v: number) => fmtPct(v).replace("+", "");   // isaretsiz yuzde

function section(title: string, inner: string): string {
  return `<section><h2>${esc(title)}</h2>${inner}</section>`;
}

function kv(rows: [string, string][]): string {
  return `<table class="kv">${rows.map(
    ([k, v]) => `<tr><td class="k">${esc(k)}</td><td class="v">${v}</td></tr>`).join("")}</table>`;
}

function table(headers: string[], rows: string[][], right: number[] = []): string {
  const th = headers.map((h, i) =>
    `<th class="${right.includes(i) ? "r" : ""}">${esc(h)}</th>`).join("");
  const tr = rows.map((r) =>
    `<tr>${r.map((c, i) => `<td class="${right.includes(i) ? "r" : ""}">${c}</td>`).join("")}</tr>`).join("");
  return `<table class="grid"><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
}

async function loadLogo(): Promise<string> {
  try {
    const r = await fetch("/logo.png");
    const b = await r.blob();
    return await new Promise((res) => {
      const fr = new FileReader();
      fr.onload = () => res(fr.result as string);
      fr.onerror = () => res("");
      fr.readAsDataURL(b);
    });
  } catch {
    return "";
  }
}

/* ---------- rapor govdesi ---------- */

function buildBody(data: AnalyzeResponse, L: L, lang: Lang): string {
  const parts: string[] = [];
  const r = data.market_risk;
  const adv = r?.advanced;
  const zoneWord = (z: string | null) =>
    z ? ({ green: lang === "en" ? "green" : "yeşil", yellow: lang === "en" ? "yellow" : "sarı", red: lang === "en" ? "red" : "kırmızı" }[z] ?? z) : "—";

  // 1) Ozet
  const sumRows: [string, string][] = [
    [L.totalValue, `<b>${fmtTL(data.total_value_try)}</b>`],
    ["USD/TRY", fmtNum(data.fx_usdtry)],
  ];
  if (adv?.score) sumRows.push([L.score, `<b>${fmtNum(adv.score.score)}</b> / 100`]);
  if (adv?.risk_class) sumRows.push([L.riskClass, `<b>${adv.risk_class.risk_class}</b> / 7`]);
  parts.push(section(L.summary, kv(sumRows)));

  // 2) Varliklar
  const vrows = data.valuation.map((v) => [
    esc(v.name) + ` <span class="dim">${v.type === "bond" ? L.bond : v.currency}</span>`,
    v.last_price != null ? fmtNum(v.last_price) : "—",
    fmtTL(v.value_try),
    dc(v.pnl_try, v.pnl_try != null ? fmtTL(v.pnl_try) : ""),
    dc(v.pnl_pct, v.pnl_pct != null ? fmtPct(v.pnl_pct / 100) : ""),
  ]);
  parts.push(section(L.valuation, table(
    [L.colAsset, L.colLast, L.colValue, L.colPnl, L.colPnlPct], vrows, [1, 2, 3, 4])));

  if (!r) return parts.join("");

  // 3) Piyasa riski
  const mrRows: [string, string][] = [
    [`${L.varHeadline} (%${(r.confidence * 100).toFixed(0)})`,
      dc(-1, `${fmtTL(r.var_value_try)} · ${fmtPct(r.var_pct)}`)],
  ];
  if (r.var_pct_historical != null)
    mrRows.push([L.varHist, `<span class="dim">${fmtPct(r.var_pct_historical)}</span>`]);
  if (adv?.es?.es_pct != null) mrRows.push([L.es, dc(-1, fmtPct(adv.es.es_pct))]);
  if (adv?.es?.es975_pct != null) mrRows.push([L.es975, dc(-1, fmtPct(adv.es.es975_pct))]);
  mrRows.push([L.obs, `${r.observations.toLocaleString()} · %${(r.confidence * 100).toFixed(0)} ${L.conf}`]);
  parts.push(section(L.marketRisk, kv(mrRows)));

  // 4) Sharpe & belirsizlik
  if (r.sharpe?.["1y"] || adv?.sharpe_ci) {
    const s = r.sharpe;
    const sr: [string, string][] = [];
    if (s?.["1y"]) sr.push([L.sharpe1y, dc(s["1y"].sharpe, fmtNum(s["1y"].sharpe))]);
    if (s?.["3y"]) sr.push([L.sharpe3y, dc(s["3y"].sharpe, fmtNum(s["3y"].sharpe))]);
    if (s?.["5y"]) sr.push([L.sharpe5y, dc(s["5y"].sharpe, fmtNum(s["5y"].sharpe))]);
    if (adv?.sharpe_ci) {
      sr.push([L.sharpeCI, `[${fmtNum(adv.sharpe_ci.ci_low)} – ${fmtNum(adv.sharpe_ci.ci_high)}]`]);
      sr.push([L.psr, pctNS(adv.sharpe_ci.psr)]);
    }
    if (adv?.beat_deposit)
      sr.push([L.beatDep, `<b>${pctNS(1 - adv.beat_deposit.prob_below_deposit)}</b>`]);
    parts.push(section(L.sharpe, kv(sr)));
  }

  // 5) Modeller & backtest
  if (adv?.backtest) {
    const bt = adv.backtest;
    const hm = adv.headline_var?.model;
    const mv: Record<string, number | undefined> = {
      historical: r.var_pct_historical,
      ewma: adv.ewma?.var_ewma_pct, fhs: adv.ewma?.var_fhs_pct,
    };
    const rowFor = (key: "historical" | "ewma" | "fhs", label: string) => {
      const m = bt.models[key];
      return [
        esc(label) + (hm === key ? ` <span class="dim">${L.headlineTag}</span>` : ""),
        mv[key] != null ? fmtPct(mv[key]!) : "—",
        String(m.violations), String(m.expected),
        (m.kupiec_p * 100).toFixed(0) + "%",
        `<span class="zone-${m.basel_zone}">${zoneWord(m.basel_zone)}</span>`,
      ];
    };
    parts.push(section(`${L.models} (${bt.days} ${L.days})`, table(
      [L.colModel, L.colVaR, L.colViol, L.colExp, L.colKupiec, L.colZone],
      [rowFor("historical", L.mHist), rowFor("ewma", L.mEwma), rowFor("fhs", L.mFhs)],
      [1, 2, 3, 4])));
  }

  // 6) Risk atfi
  if (adv?.attribution) {
    const rows = adv.attribution.components.map((c) => [
      esc(c.name),
      pctNS(c.weight),
      c.cvar_share != null ? pctNS(c.cvar_share) : "—",
      c.incremental_tl != null ? dc(c.incremental_tl, fmtTL(c.incremental_tl)) : "—",
    ]);
    parts.push(section(L.attrib, table(
      [L.colAsset, L.colMoneyShare, L.colRiskShare, L.colInc], rows, [1, 2, 3])));
  }

  // 7) Yogunlasma & cesitlendirme
  if (adv?.concentration) {
    const c = adv.concentration;
    parts.push(section(L.concentration, kv([
      [L.effPos, `${fmtNum(c.effective_positions)} / ${c.n_assets}`],
      [L.effBets, fmtNum(c.effective_bets)],
      [L.divRatio, fmtNum(c.diversification_ratio)],
      [L.hhi, fmtNum(c.hhi)],
      ...(r.diversification ? [[L.divBenefit, dc(1, fmtTL(r.diversification.benefit))]] as [string, string][] : []),
    ])));
  }

  // 8) Volatilite rejimi
  if (adv?.vol_regime) {
    const v = adv.vol_regime;
    parts.push(section(L.volRegime, kv([
      [L.curVol, pctNS(v.current_vol_ann)],
      [L.volPct, `${(v.percentile * 100).toFixed(0)}.`],
      [L.medVol, pctNS(v.median_vol_ann)],
    ])));
  }

  // 9) Reel getiri
  if (adv?.real) {
    const rl = adv.real;
    parts.push(section(L.real, kv([
      [L.period, `${rl.period_start ?? ""} → ${rl.cpi_as_of}`],
      [L.infl, pctNS(rl.inflation_12m)],
      [L.nom, dc(rl.nominal_return_12m, fmtPct(rl.nominal_return_12m))],
      [L.realRet, dc(rl.real_return_12m, fmtPct(rl.real_return_12m))],
      ...(rl.prob_real_loss_12m != null ? [[L.realLoss, pctNS(rl.prob_real_loss_12m)]] as [string, string][] : []),
    ])));
  }

  // 10) Kur ayristirmasi
  if (adv?.fx) {
    const f = adv.fx;
    parts.push(section(L.fx, kv([
      [L.fxExp, pctNS(f.usd_exposure_share)],
      [L.fxLocal, pctNS(f.local_share)],
      [L.fxCur, pctNS(f.fx_share)],
      [L.fxCov, fmtPct(f.cov_share)],
    ])));
  }

  // 11) Likidite
  if (adv?.liquidity) {
    const rows = adv.liquidity.positions.map((p) => [esc(p.name), fmtNum(p.days_to_exit)]);
    parts.push(section(L.liquidity,
      table([L.colAsset, L.colExitDays], rows, [1]) +
      kv([[L.lvar, `${dc(adv.liquidity.lvar_value_tl, fmtTL(adv.liquidity.lvar_value_tl))} (${L.lvarMult} ${fmtNum(adv.liquidity.lvar_multiplier)})`]])));
  }

  // 12) Drawdown
  if (adv?.drawdown) {
    const d = adv.drawdown;
    parts.push(section(L.drawdown, kv([
      [L.maxDd, dc(d.max_drawdown, fmtPct(d.max_drawdown))],
      ...(d.calmar != null ? [[L.calmar, fmtNum(d.calmar)]] as [string, string][] : []),
      [L.ulcer, fmtNum(d.ulcer_index * 100)],
      [L.underwater, `${d.underwater_days_now} / ${d.longest_underwater_days} ${L.days}`],
    ])));
  }

  // 13) Kuyruk riski
  if (adv?.evt || adv?.tail_dependence) {
    let inner = "";
    if (adv.evt) {
      inner += kv([
        [L.evtVar, dc(adv.evt.var995_pct, fmtPct(adv.evt.var995_pct))],
        [L.evtEs, dc(adv.evt.es995_pct, fmtPct(adv.evt.es995_pct))],
        [L.tailIndex, `${fmtNum(adv.evt.tail_index)} (${adv.evt.exceedances} ${L.obs})`],
      ]);
    }
    if (adv.tail_dependence?.pairs.length) {
      inner += `<p class="sub">${esc(L.tailDep)}</p>` + table(
        [L.colPair, L.colLambda, L.colPearson],
        adv.tail_dependence.pairs.map((p) => [esc(p.pair), fmtNum(p.lambda_lower), fmtNum(p.pearson)]),
        [1, 2]);
    }
    parts.push(section(L.tail, inner));
  }

  // 14) Stres testleri
  const st = Object.entries(r.stress_tests || {});
  if (st.length) {
    const rows = st.map(([name, s]) => [
      esc(name) + ` <span class="dim">${esc(s.region)}</span>`,
      s.impact_try != null ? dc(s.impact_try, fmtTL(s.impact_try)) : "—",
      s.cumulative_return != null ? dc(s.cumulative_return, fmtPct(s.cumulative_return)) : "—",
      s.coverage != null ? pctNS(s.coverage) : "—",
    ]);
    parts.push(section(L.stress, table(
      [L.colScenario, L.colImpact, L.colReturn, L.colCoverage], rows, [1, 2, 3])));
  }

  // 15) Faktor sok izgarasi
  if (adv?.factor_shock) {
    const rows = adv.factor_shock.scenarios.map((s) => [
      esc(s.name),
      dc(s.impact_pct, fmtPct(s.impact_pct)),
      dc(s.impact_real_pct, fmtPct(s.impact_real_pct)),
      dc(s.impact_tl, fmtTL(s.impact_tl)),
    ]);
    const betas = Object.entries(adv.factor_shock.betas)
      .map(([k, v]) => `${esc(k)} ${fmtNum(v)}`).join(" · ");
    parts.push(section(L.factorShock,
      table([L.colScenario, L.colNom, L.colReal, L.colImpact], rows, [1, 2, 3]) +
      `<p class="sub">${esc(L.betas)}: ${betas}</p>`));
  }

  // 16) HRP
  if (adv?.hrp) {
    const rows = Object.entries(adv.hrp.weights)
      .sort((a, b) => b[1] - a[1])
      .map(([n, w]) => [esc(n), pctNS(w)]);
    let inner = table([L.colAsset, L.colWeight], rows, [1]);
    if (adv.hrp.excluded_cash_like?.length)
      inner += `<p class="sub">${esc(L.hrpExcluded)}: ${esc(adv.hrp.excluded_cash_like.join(", "))}</p>`;
    parts.push(section(L.hrp, inner));
  }

  // 17) Stil analizi
  if (adv?.style && Object.values(adv.style).some((s) => s)) {
    let inner = "";
    for (const [fund, s] of Object.entries(adv.style)) {
      if (!s) continue;
      const w = Object.entries(s.weights).filter(([, x]) => x > 0.01).sort((a, b) => b[1] - a[1])
        .map(([n, x]) => `${esc(n)} ${pctNS(x)}`).join(" · ");
      const lowR2 = s.r2 == null || s.r2 < 0.30;
      const stats = lowR2
        ? `${L.styleR2} ${s.r2 != null ? pctNS(s.r2) : "—"} · <span class="dim">${esc(L.styleLow)}</span>`
        : `${L.styleR2} ${pctNS(s.r2!)} · ${L.styleTE} ${pctNS(s.tracking_error_ann)}/y · ${L.styleIR} ${s.information_ratio != null ? fmtNum(s.information_ratio) : "—"}`;
      inner += `<div class="style-item"><b>${esc(fund)}</b><div>${w}</div><div class="sub">${stats}${s.lag_days ? ` · ${L.styleLag} ${s.lag_days}g` : ""}</div></div>`;
    }
    parts.push(section(L.style, inner));
  }

  // 18) Tahvil riski
  if (data.bond_risk) {
    const b = data.bond_risk;
    const shocks = Object.entries(b.rate_shocks)
      .map(([bps, v]) => [`${+bps > 0 ? "+" : ""}${bps} bp`, dc(v, fmtTL(v))]);
    parts.push(section(L.bond,
      kv([[L.bondDv01, fmtTL(b.total_dv01)], [L.bondDur, fmtNum(b.weighted_modified_duration)]]) +
      table([L.colShock, L.colImpact], shocks, [1])));
  }

  return parts.join("");
}

/* ---------- sablon + yazdirma ---------- */

function buildHtml(data: AnalyzeResponse, L: L,
                   lang: Lang, logo: string, nickname?: string | null): string {
  const now = new Date();
  const dateStr = now.toLocaleString(lang === "en" ? "en-US" : "tr-TR",
    { dateStyle: "long", timeStyle: "short" });
  const who = nickname ? ` · ${esc(nickname)}` : "";
  return `<!doctype html><html lang="${lang}"><head><meta charset="utf-8">
<title>Kuantile — ${esc(L.subtitle)}</title>
<style>
  @page { size: A4; margin: 16mm 14mm 18mm; }
  * { box-sizing: border-box; }
  body { font: 12px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; color: #1a1a1a; margin: 0; }
  .head { display: flex; align-items: center; gap: 12px; border-bottom: 3px solid #2a78d6;
          padding-bottom: 12px; margin-bottom: 8px; }
  .head img { width: 40px; height: 40px; object-fit: contain; }
  .head .brand { font-size: 22px; font-weight: 800; color: #2a78d6; letter-spacing: -.3px; }
  .head .sub { font-size: 12px; color: #666; margin-top: 2px; }
  .head .meta { margin-left: auto; text-align: right; font-size: 11px; color: #888; }
  section { break-inside: avoid; margin: 14px 0 0; }
  h2 { font-size: 13.5px; color: #2a78d6; margin: 0 0 6px; padding-bottom: 3px;
       border-bottom: 1px solid #e2e2dd; }
  table { width: 100%; border-collapse: collapse; }
  table.kv td { padding: 3px 0; border-bottom: 1px dashed #ececec; vertical-align: top; }
  table.kv td.k { color: #666; width: 55%; }
  table.kv td.v { text-align: right; font-variant-numeric: tabular-nums; }
  table.grid { font-size: 11.5px; margin-top: 2px; }
  table.grid th { text-align: left; color: #888; font-weight: 600; border-bottom: 1px solid #ddd;
                  padding: 4px 6px; }
  table.grid td { padding: 4px 6px; border-bottom: 1px solid #f2f2f0; vertical-align: top;
                  font-variant-numeric: tabular-nums; }
  table.grid th.r, table.grid td.r, .r { text-align: right; }
  table.grid td:first-child, table.grid th:first-child { padding-left: 0; }
  .up { color: #0a7a30; } .down { color: #c0392b; } .dim { color: #999; }
  .zone-green { color: #0a7a30; font-weight: 700; }
  .zone-yellow { color: #b8860b; font-weight: 700; }
  .zone-red { color: #c0392b; font-weight: 700; }
  .sub { color: #888; font-size: 11px; margin: 6px 0 0; }
  .style-item { margin: 6px 0; padding: 6px 0; border-bottom: 1px dashed #ececec; }
  .foot { margin-top: 20px; padding-top: 8px; border-top: 1px solid #e2e2dd;
          font-size: 10px; color: #999; }
  @media print { body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
</style></head><body>
  <div class="head">
    ${logo ? `<img src="${logo}" alt="">` : ""}
    <div>
      <div class="brand">Kuantile</div>
      <div class="sub">${esc(L.subtitle)}</div>
    </div>
    <div class="meta">${esc(L.generated)}: ${esc(dateStr)}${who}</div>
  </div>
  ${buildBody(data, L, lang)}
  <div class="foot">${esc(L.disclaimer)}</div>
</body></html>`;
}

function printHtml(html: string): void {
  const iframe = document.createElement("iframe");
  Object.assign(iframe.style, {
    position: "fixed", right: "0", bottom: "0", width: "0", height: "0", border: "0",
  });
  document.body.appendChild(iframe);
  const win = iframe.contentWindow!;
  win.document.open();
  win.document.write(html);
  win.document.close();
  let removed = false;
  const cleanup = () => { if (!removed) { removed = true; setTimeout(() => iframe.remove(), 500); } };
  win.onafterprint = cleanup;
  // gorseller/yerlesim otursun diye kisa bekleme
  setTimeout(() => {
    win.focus();
    win.print();
    setTimeout(cleanup, 60000);   // guvenlik: diyalog kapanmasa da temizle
  }, 400);
}

export async function exportReport(data: AnalyzeResponse, _positions: PositionIn[],
                                   lang: Lang, nickname?: string | null): Promise<void> {
  const L = LABELS[lang];
  const logo = await loadLogo();
  printHtml(buildHtml(data, L, lang, logo, nickname));
}
