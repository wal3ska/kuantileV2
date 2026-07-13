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
}

export interface MarketRisk {
  confidence: number;
  var_pct: number;
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

  analyze: (positions: PositionIn[], bonds: BondIn[], confidence: number) =>
    req<AnalyzeResponse>("POST", "/portfolio/analyze", { positions, bonds, confidence }),
};

/* ---------- biçimleme yardımcıları ---------- */

const locale = () => (getLang() === "en" ? "en-US" : "tr-TR");

export const fmtTL = (v: number) =>
  `${v.toLocaleString(locale(), { maximumFractionDigits: 0 })} ₺`;
export const fmtNum = (v: number) =>
  v.toLocaleString(locale(), { maximumFractionDigits: 2 });
export const fmtPct = (v: number, digits = 2) =>
  `${v > 0 ? "+" : ""}${(v * 100).toLocaleString(locale(), { maximumFractionDigits: digits, minimumFractionDigits: digits })}%`;
