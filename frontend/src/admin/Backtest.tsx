import { useState } from "react";
import {
  api, ApiError, setToken,
  type BacktestRequest, type BacktestResponse, type PortfolioMethod,
} from "../api";

const DEFAULTS: BacktestRequest = {
  universe: {
    filters: { watchlist: true, neg_equity: true, persistent_loss: true, altman: true, liquidity: true },
    altman_min: 1.1, adv_min_tl: 5_000_000, loss_years_min: 3, vol_min: null, vol_max: null, geo_min: null,
  },
  method: "max_sharpe",
  max_assets: 30, max_weight: 0.10, sector_cap: 0.30, rf_annual: 0,
  window_years: 5, train_years: 3, test_months: 3,
};

const METHODS: [PortfolioMethod, string][] = [
  ["max_sharpe", "Max Sharpe"], ["min_variance", "Min Varyans"],
  ["risk_parity", "Risk Parity"], ["hrp", "HRP"], ["equal", "Eşit Ağırlık"],
];

const pct = (v: number | null | undefined, d = 1) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(d)}%`;
const num = (v: number | null | undefined, d = 2) =>
  v === null || v === undefined ? "—" : v.toFixed(d);

/* OOS equity eğrisi (log ölçek) — portföy vs 1/N */
function Curve({ data }: { data: BacktestResponse }) {
  const c = data.curve;
  if (c.length < 2) return null;
  const W = 720, H = 320, pad = 46;
  const ly = (v: number) => Math.log(Math.max(v, 1e-6));
  const all = c.flatMap((p) => [ly(p.port), ly(p.bench)]);
  const y0 = Math.min(...all), y1 = Math.max(...all);
  const n = c.length;
  const sx = (i: number) => pad + (i / (n - 1)) * (W - pad - 12);
  const sy = (v: number) => H - pad - ((ly(v) - y0) / (y1 - y0 || 1)) * (H - pad - 16);
  const line = (key: "port" | "bench") =>
    c.map((p, i) => `${i ? "L" : "M"}${sx(i).toFixed(1)},${sy(p[key]).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="pf-chart" role="img" aria-label="OOS equity eğrisi">
      <line x1={pad} y1={H - pad} x2={W - 12} y2={H - pad} className="pf-axis" />
      <line x1={pad} y1={12} x2={pad} y2={H - pad} className="pf-axis" />
      <path d={line("bench")} className="bt-bench" fill="none" />
      <path d={line("port")} className="bt-port" fill="none" />
      <text x={pad} y={16} className="pf-lbl">↑ 1₺ → {num(c[c.length - 1].port, 1)}₺ (log)</text>
      <text x={W - 12} y={H - pad + 18} className="pf-lbl" textAnchor="end">
        {c[0].date.slice(0, 7)} → {c[c.length - 1].date.slice(0, 7)}
      </text>
      <text x={W - 12} y={16} className="pf-lbl bt-l-port" textAnchor="end">■ portföy</text>
      <text x={W - 100} y={16} className="pf-lbl bt-l-bench" textAnchor="end">■ 1/N</text>
    </svg>
  );
}

export function Backtest({ onAuthFail }: { onAuthFail: () => void }) {
  const [req, setReq] = useState<BacktestRequest>(DEFAULTS);
  const [data, setData] = useState<BacktestResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setBusy(true); setErr(null);
    try {
      setData(await api.adminBacktest(req));
    } catch (ex) {
      if (ex instanceof ApiError && ex.status === 401) { setToken(null); onAuthFail(); return; }
      setErr(ex instanceof ApiError ? ex.message : "Backtest başarısız.");
    } finally { setBusy(false); }
  }

  const m = data?.metrics;

  return (
    <div className="u-wrap">
      <div className="u-controls">
        <div className="pf-methods">
          {METHODS.map(([k, label]) => (
            <button key={k} className={`pf-method ${req.method === k ? "on" : ""}`}
              onClick={() => setReq((r) => ({ ...r, method: k }))}>{label}</button>
          ))}
        </div>
        <div className="u-thresholds">
          <label>Max hisse
            <input type="number" min={5} max={80} value={req.max_assets}
              onChange={(e) => setReq((r) => ({ ...r, max_assets: +e.target.value }))} />
          </label>
          <label>Poz. tavanı (%)
            <input type="number" step={1} value={req.max_weight * 100}
              onChange={(e) => setReq((r) => ({ ...r, max_weight: +e.target.value / 100 }))} />
          </label>
          <label>Sektör tavanı (%)
            <input type="number" step={1} value={req.sector_cap === null ? "" : req.sector_cap * 100}
              onChange={(e) => setReq((r) => ({ ...r, sector_cap: e.target.value === "" ? null : +e.target.value / 100 }))} />
          </label>
          <label>Train (yıl)
            <input type="number" step={0.5} min={0.5} max={5} value={req.train_years}
              onChange={(e) => setReq((r) => ({ ...r, train_years: +e.target.value }))} />
          </label>
          <label>Test (ay)
            <input type="number" min={1} max={12} value={req.test_months}
              onChange={(e) => setReq((r) => ({ ...r, test_months: +e.target.value }))} />
          </label>
          <button className="a-primary u-apply" onClick={run} disabled={busy}>
            {busy ? "Çalışıyor…" : "Backtest çalıştır"}
          </button>
        </div>
      </div>

      {err && <div className="a-err">{err}</div>}

      {data && m && (
        <>
          <div className="u-tiles">
            <div className="u-tile"><span>{pct(m.cagr)}</span>OOS CAGR (nominal)</div>
            <div className="u-tile"><span>{data.real ? pct(data.real.real_cagr) : "—"}</span>reel CAGR</div>
            <div className="u-tile"><span>{num(m.sharpe)}</span>OOS Sharpe ±{num(m.sharpe_se)}</div>
            <div className="u-tile"><span>{pct(m.psr_vs_0, 0)}</span>PSR (&gt;0)</div>
            <div className="u-tile"><span>{pct(m.max_drawdown)}</span>max düşüş</div>
            <div className="u-tile muted"><span>{pct(data.benchmark.cagr)} · {num(data.benchmark.sharpe)}</span>1/N CAGR · Sharpe</div>
            <div className="u-tile muted"><span>{data.rebalances}</span>rebalans</div>
          </div>

          <div className="u-card">
            <h3>OOS büyüme — portföy vs 1/N ({data.start.slice(0, 7)} → {data.end.slice(0, 7)})</h3>
            <Curve data={data} />
            <p className="u-note">
              Ağırlıklar yalnızca train penceresinde üretilip sonraki {data.test_days} günde test edildi
              ({data.rebalances} rebalans, {data.n_assets} hisse). Bu OOS sonuç in-sample'dan düşüktür ve
              gerçekçidir. {data.real ? `Enflasyon (TÜFE) CAGR ${pct(data.real.inflation_cagr)}; reel getiri nominalden bu kadar arındırıldı.` : "TÜFE verisi yok → reel getiri hesaplanamadı (EVDS anahtarı)."}
            </p>
          </div>
        </>
      )}

      {!data && !busy && !err && (
        <div className="a-placeholder">
          <span className="a-ph-ic">⇌</span>
          <h2>Walk-forward backtest</h2>
          <p>Yöntemi seç, "Backtest çalıştır"a bas. Ağırlıklar geçmişte train→test kaydırılarak dürüstçe (OOS) sınanır; 1/N ve reel getiriyle kıyaslanır.</p>
        </div>
      )}
    </div>
  );
}
