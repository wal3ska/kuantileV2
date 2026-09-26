/* API istemcisi. Prod'da nginx kuantile.com/api/* -> api:8000/* olarak vekalet eder;
   dev'de vite proxy ayni isi yapar. */

import { getLang } from "./i18n";

const BASE = "/api";
const TOKEN_KEY = "kt_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string | null) {
  if (t === null) localStorage.removeItem(TOKEN_KEY);
  else localStorage.setItem(TOKEN_KEY, t);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

async function req<T>(method: string, path: string, body?: unknown, auth = false): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) headers["Authorization"] = `Bearer ${getToken() ?? ""}`;
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, getLang() === "en" ? "Could not reach the server." : "Sunucuya ulaşılamadı.");
  }
  if (!res.ok) {
    let detail = `Hata (${res.status})`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") detail = j.detail;
      else if (Array.isArray(j.detail) && j.detail[0]?.msg) detail = j.detail[0].msg;
    } catch { /* gövde JSON değil */ }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

/* ---------- tipler (api.py şemalarının aynası) ---------- */

export type Currency = "TRY" | "USD";
export type Source = "yahoo" | "tefas";

export interface MailPrefs {
  daily: boolean;
  weekly: boolean;
  monthly: boolean;
  yearly: boolean;
}

export interface PositionIn {
  name: string;
  ticker: string;
  currency: Currency;
  source: Source;
  category: string;
  quantity: number;
  cost: number | null;
}

export interface BondIn {
  name: string;
  currency: Currency;
  nominal: number;
  price: number;
  coupon_rate: number;
  frequency: number;
  years: number;
  ytm: number;
  cost: number | null;
}

export interface ValuationRow {
  name: string;
  type: "market" | "bond";
  currency: Currency;
  last_price?: number;
  fair_price?: number;
  macaulay?: number;
  modified?: number;
  ytm?: number;
  value: number;
  cost_total: number | null;
  pnl: number | null;
  pnl_pct: number | null;
  value_try: number;
  pnl_try: number | null;
}

export interface StressResult {
  region: string;
  start: string;
  end: string;
  cumulative_return: number | null;
  impact_try: number | null;
  missing_assets: string[];
  coverage: number | null;
}

export interface SharpeInfo {
  sharpe: number;
  ann_return: number;
  ann_vol: number;
  ann_rf: number;
  observations: number;
}

export interface SharpeMulti {
  "1y": SharpeInfo | null;
  "3y": SharpeInfo | null;
  "5y": SharpeInfo | null;
}

export interface RiskFree {
  kind: "rate" | "deposit" | "tlref" | "usd" | "eur";
  annual_rate: number;
}

export interface AdvViolations {
  violations: number; expected: number;
  kupiec_p: number; christoffersen_p: number | null;
  basel_zone: "green" | "yellow" | "red";
}
export interface AdvBacktest {
  days: number; confidence: number;
  models: { historical: AdvViolations; ewma: AdvViolations; fhs: AdvViolations };
}
export interface AdvSharpeCI {
  sharpe_ann: number; se_ann: number; ci_low: number; ci_high: number;
  psr: number; observations: number; skew: number; excess_kurtosis: number;
}
export interface AdvBeatDeposit {
  prob_below_deposit: number; prob_below_point: number;
  deposit_annual: number; horizon_days: number;
}
export interface AdvComponent {
  name: string; weight: number; cvar_tl: number;
  cvar_share: number | null; incremental_tl: number | null;
}
export interface AdvStyle {
  weights: Record<string, number>; r2: number | null; tracking_error_ann: number;
  alpha_ann: number; information_ratio: number | null; observations: number;
  lag_days?: number;
}
export interface AdvancedBlock {
  es: { es_pct: number | null; es975_pct: number | null } | null;
  backtest: AdvBacktest | null;
  sharpe_ci: AdvSharpeCI | null;
  beat_deposit: AdvBeatDeposit | null;
  attribution: { components: AdvComponent[]; total_var_tl: number } | null;
  ewma: {
    ewma_vol_ann: number; var_ewma_pct: number; var_fhs_pct: number;
    es_fhs_pct?: number; es_ewma_pct?: number; lambda: number;
  } | null;
  drawdown: {
    max_drawdown: number; calmar: number | null; ulcer_index: number;
    underwater_days_now: number; longest_underwater_days: number; ann_return: number | null;
  } | null;
  concentration: {
    hhi: number; effective_positions: number; diversification_ratio: number;
    effective_bets: number; n_assets: number;
  } | null;
  evt: {
    tail_index: number; threshold_pct: number; exceedances: number;
    var995_pct: number; es995_pct: number;
  } | null;
  tail_dependence: {
    pairs: { pair: string; lambda_lower: number; co_exceedances: number; pearson: number }[];
    q: number; tail_obs: number; expected_co: number;
  } | null;
  hrp: { weights: Record<string, number>; excluded_cash_like?: string[] } | null;
  real: {
    inflation_12m: number; nominal_return_12m: number; real_return_12m: number;
    prob_real_loss_12m: number | null; cpi_as_of: string;
    period_start?: string; window_aligned?: boolean;
  } | null;
  fx: {
    usd_exposure_share: number; local_share: number;
    fx_share: number; cov_share: number; fx_vol_ann: number; fx_drift_ann: number;
  } | null;
  liquidity: {
    positions: { name: string; days_to_exit: number; value_share: number }[];
    lvar_multiplier: number; lvar_value_tl: number;
  } | null;
  style: Record<string, AdvStyle | null> | null;
  vol_regime: { current_vol_ann: number; percentile: number; median_vol_ann: number; observations: number } | null;
  factor_shock: {
    scenarios: { name: string; impact_pct: number; impact_tl: number; impact_real_pct: number; shocks: Record<string, number> }[];
    betas: Record<string, number>;
    passthrough?: number;
  } | null;
  expected_mdd?: number | null;
  headline_var?: {
    model: string; var_pct: number | null;
    basel_zone: "green" | "yellow" | "red" | null; kupiec_p: number | null;
  } | null;
  risk_class?: { risk_class: number; ann_vol_weekly: number; weeks: number } | null;
  score?: {
    score: number;
    components: Record<string, number>;
    weights_used: Record<string, number>;
  } | null;
}

export interface MarketRisk {
  confidence: number;
  sharpe: SharpeMulti | null;
  advanced?: AdvancedBlock;
  var_pct: number;
  var_pct_historical?: number;
  var_value_try: number;
  market_value_try: number;
  observations: number;
  correlation: Record<string, Record<string, number>>;
  diversification: { sum_individual_var: number; portfolio_var: number; benefit: number };
  stress_tests: Record<string, StressResult>;
}

export interface BondRisk {
  basket_value: number;
  weighted_modified_duration: number;
  total_dv01: number;
  rate_shocks: Record<string, number>;
  portfolio_duration_contribution?: number;
}

export interface AnalyzeResponse {
  fx_usdtry: number;
  total_value_try: number;
  valuation: ValuationRow[];
  failed_assets: string[];
  market_risk: MarketRisk | null;
  bond_risk: BondRisk | null;
  disclaimer: string;
}

export interface SimulateResponse {
  start: string;
  end: string;
  cumulative_return: number;
  impact_try: number;
  base_value_try: number;
  final_value_try: number;
  missing_assets: string[];
  series: { date: string; value: number }[];
}

export interface PortfolioData {
  name: string;
  updated_at: string | null;
  positions: PositionIn[];
  bonds: BondIn[];
}

/* ---------- uçlar ---------- */

export const api = {
  register: (email: string, nickname: string, password: string, lang: string) =>
    req<{ message: string }>("POST", "/auth/register", { email, nickname, password, lang }),

  setLang: (lang: string) =>
    req<{ lang: string }>("POST", "/auth/lang", { lang }, true),

  login: (email: string, password: string) =>
    req<{ access_token: string; email: string; nickname: string | null }>("POST", "/auth/login", { email, password }),

  me: () => req<{ email: string; nickname: string | null; verified: boolean; mail: MailPrefs }>("GET", "/auth/me", undefined, true),

  setMailPrefs: (prefs: MailPrefs) =>
    req<{ mail: MailPrefs }>("POST", "/auth/mail-prefs", prefs, true),

  getPortfolio: () => req<PortfolioData>("GET", "/portfolio", undefined, true),

  savePortfolio: (positions: PositionIn[], bonds: BondIn[]) =>
    req<{ message: string }>("PUT", "/portfolio", { positions, bonds }, true),

  analyze: (positions: PositionIn[], bonds: BondIn[], confidence: number, riskFree: RiskFree) =>
    req<AnalyzeResponse>("POST", "/portfolio/analyze", { positions, bonds, confidence, risk_free: riskFree }),

  rates: () =>
    req<{ deposit_gross: number; deposit_net: number; stopaj: number; as_of: string; source: string;
          tlref?: number; tlref_as_of?: string }>("GET", "/rates"),

  simulate: (positions: PositionIn[], start: string, end: string) =>
    req<SimulateResponse>("POST", "/portfolio/simulate", { positions, start, end }),

  adminMe: () =>
    req<{ email: string; nickname: string | null; admin: true }>("GET", "/admin/me", undefined, true),

  adminUniverseStatus: () =>
    req<UniverseStatus>("GET", "/admin/universe/status", undefined, true),

  adminUniverse: (body: UniverseRequest) =>
    req<UniverseResponse>("POST", "/admin/universe", body, true),

  adminPortfolio: (body: PortfolioRequest) =>
    req<PortfolioResponse>("POST", "/admin/portfolio", body, true),

  adminBacktest: (body: BacktestRequest) =>
    req<BacktestResponse>("POST", "/admin/backtest", body, true),

  adminProjection: (body: ProjectionRequest) =>
    req<ProjectionResponse>("POST", "/admin/projection", body, true),

  adminOptimize: (body: PortfolioRequest) =>
    req<OptimizeResponse>("POST", "/admin/optimize", body, true),

  adminRisk: (body: PortfolioRequest) =>
    req<RiskResponse>("POST", "/admin/risk", body, true),
};

/* ---------- Quant Lab: Optimizasyon (yöntem kıyas + Kelly) ---------- */

export interface OptimizeResponse {
  n_assets: number;
  observations: number;
  eligible_count: number;
  methods: {
    method: string; exp_return: number; vol: number; sharpe: number;
    cagr: number; max_drawdown: number; effective_n: number;
    top: { ticker: string; weight: number }[];
  }[];
  frontier: { vol: number; ret: number }[] | null;
  kelly: { full: number; half: number; growth_full: number; growth_half: number;
           port_return: number; port_vol: number } | null;
}

/* ---------- Quant Lab: Risk Ayrıştırma ---------- */

export interface RiskResponse {
  method: string;
  n_assets: number;
  observations: number;
  eligible_count: number;
  notional: number;
  var_pct: { var95: number; var99: number; cvar95: number; cvar99: number; var99_cf: number; worst_day: number };
  var_tl: { var95: number; var99: number; cvar95: number; cvar99: number; var99_cf: number; worst_day: number };
  components: { ticker: string; sector: string; weight: number; risk_share: number; comp_var99_tl: number }[];
  sector_risk: { sector: string; risk_share: number }[];
  concentration: { hhi: number; effective_n: number | null; diversification_ratio: number | null; port_vol_ann: number };
  tail: { skew: number; excess_kurtosis: number };
  factor: { pc1_explained?: number; systematic_share?: number; gold_beta?: number; gold_r2?: number };
}

/* ---------- Quant Lab: Monte Carlo projeksiyon ---------- */

export interface ProjectionRequest extends PortfolioRequest {
  horizon_months: number;
}

export interface ProjectionResponse {
  method: string;
  n_assets: number;
  horizon_months: number;
  grid_days: number[];
  assets: { ticker: string; weight: number; path: number[] }[];
  portfolio: { p5: number[]; p50: number[]; p95: number[] };
  exp_return_ann: number;
  exp_vol_ann: number;
}

/* ---------- Quant Lab: Varlık Evreni ---------- */

export interface UniverseStatus {
  metrics: number;
  symbols: number;
  as_of: string | null;
}

export interface UniverseFilters {
  watchlist: boolean;
  neg_equity: boolean;
  persistent_loss: boolean;
  altman: boolean;
  liquidity: boolean;
  limit_down: boolean;
  drawdown: boolean;
}

export interface UniverseRequest {
  filters: UniverseFilters;
  altman_min: number;
  adv_min_tl: number;
  loss_years_min: number;
  limit_down_days_min: number;
  drawdown_limit: number;
  vol_min: number | null;
  vol_max: number | null;
  geo_min: number | null;
}

export interface UniverseRow {
  ticker: string;
  name: string | null;
  sector: string | null;
  ann_vol: number | null;
  geo_return_ann: number | null;
  adv_tl: number | null;
  altman_z: number | null;
  obs: number;
  max_drawdown: number | null;
  market_cap: number | null;
}

export interface UniverseResponse {
  as_of: string | null;
  total: number;
  eligible_count: number;
  excluded_reasons: Record<string, number>;
  sectors: { sector: string; count: number; share: number }[];
  sample: UniverseRow[];
}

/* ---------- Quant Lab: Portföy İnşası ---------- */

export type PortfolioMethod = "max_sharpe" | "min_variance" | "risk_parity" | "hrp" | "equal" | "mc_max_return";

export interface PortfolioRequest {
  universe: UniverseRequest;
  method: PortfolioMethod;
  max_assets: number;
  max_weight: number;
  sector_cap: number | null;
  rf_annual: number;
  window_years: number;
}

export interface PortfolioResponse {
  method: string;
  n_assets: number;
  observations: number;
  as_of: string | null;
  eligible_count: number;
  effective_n: number;
  weights: { ticker: string; sector: string; weight: number; risk_contrib: number; last_price: number | null }[];
  sectors: { sector: string; weight: number }[];
  metrics: {
    cagr: number; ann_vol: number; sharpe: number; sharpe_se: number; psr_vs_0: number;
    sortino: number; max_drawdown: number; calmar: number; skew: number;
    excess_kurtosis: number; geo_growth: number; vol_drag: number;
  };
  port_point: { vol: number; ret: number };
  frontier: { vol: number; ret: number }[] | null;
}

/* ---------- Quant Lab: Backtest (walk-forward OOS) ---------- */

export interface BacktestRequest {
  universe: UniverseRequest;
  method: PortfolioMethod;
  max_assets: number;
  max_weight: number;
  sector_cap: number | null;
  rf_annual: number;
  window_years: number;
  train_years: number;
  test_months: number;
}

export interface BacktestResponse {
  method: string;
  n_assets: number;
  oos_days: number;
  rebalances: number;
  train_days: number;
  test_days: number;
  start: string;
  end: string;
  metrics: {
    cagr: number; ann_vol: number; sharpe: number; sharpe_se: number;
    psr_vs_0: number; sortino: number; max_drawdown: number; calmar: number;
  };
  benchmark: { cagr: number; sharpe: number; max_drawdown: number };
  real: { real_cagr: number; inflation_cagr: number } | null;
  curve: { date: string; port: number; bench: number }[];
}

/* ---------- biçimleme yardımcıları ---------- */

const locale = () => (getLang() === "en" ? "en-US" : "tr-TR");

export const fmtTL = (v: number) =>
  `${v.toLocaleString(locale(), { maximumFractionDigits: 0 })} ₺`;
export const fmtNum = (v: number) =>
  v.toLocaleString(locale(), { maximumFractionDigits: 2 });
export const fmtPct = (v: number, digits = 2) =>
  `${v > 0 ? "+" : ""}${(v * 100).toLocaleString(locale(), { maximumFractionDigits: digits, minimumFractionDigits: digits })}%`;
