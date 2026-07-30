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
};

/* ---------- biçimleme yardımcıları ---------- */

const locale = () => (getLang() === "en" ? "en-US" : "tr-TR");

export const fmtTL = (v: number) =>
  `${v.toLocaleString(locale(), { maximumFractionDigits: 0 })} ₺`;
export const fmtNum = (v: number) =>
  v.toLocaleString(locale(), { maximumFractionDigits: 2 });
export const fmtPct = (v: number, digits = 2) =>
  `${v > 0 ? "+" : ""}${(v * 100).toLocaleString(locale(), { maximumFractionDigits: digits, minimumFractionDigits: digits })}%`;
