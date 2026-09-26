import { useState } from "react";
import { api, ApiError, setToken, type OptimizeResponse, type PortfolioRequest } from "../api";

const DEFAULT_UNIVERSE: PortfolioRequest["universe"] = {
  filters: { watchlist: true, neg_equity: true, persistent_loss: true, altman: true, liquidity: true, limit_down: true, drawdown: true },
  altman_min: 1.1, adv_min_tl: 5_000_000, loss_years_min: 3, limit_down_days_min: 2, drawdown_limit: 0.90,
  vol_min: null, vol_max: null, geo_min: null,
};
const BASE: PortfolioRequest = {
  universe: DEFAULT_UNIVERSE, method: "max_sharpe",
  max_assets: 50, max_weight: 0.10, sector_cap: 0.30, rf_annual: 0, window_years: 5,
};

const MNAME: Record<string, string> = {
  max_sharpe: "Max Sharpe", min_variance: "Min Varyans", risk_parity: "Risk Parity",
  hrp: "HRP", equal: "Eşit Ağırlık", mc_max_return: "MC Max Getiri",
};

const pct = (v: number | null | undefined, d = 1) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(d)}%`;
const num = (v: number | null | undefined, d = 2) =>
  v === null || v === undefined ? "—" : v.toFixed(d);

function Frontier({ data }: { data: OptimizeResponse }) {
  if (!data.frontier || data.frontier.length < 2) return null;
  const pts = data.frontier, W = 560, H = 320, padL = 46, padR = 12, padB = 34;
  const mp = data.methods;
  const xs = pts.map((p) => p.vol).concat(mp.map((m) => m.vol));
  const ys = pts.map((p) => p.ret).concat(mp.map((m) => m.exp_return));
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const sx = (v: number) => padL + ((v - x0) / (x1 - x0 || 1)) * (W - padL - padR);
  const sy = (v: number) => H - padB - ((v - y0) / (y1 - y0 || 1)) * (H - padB - 16);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${sx(p.vol).toFixed(1)},${sy(p.ret).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="pf-chart" role="img" aria-label="Etkin sınır & yöntemler">
      <line x1={padL} y1={H - padB} x2={W - padR} y2={H - padB} className="pf-axis" />
      <line x1={padL} y1={12} x2={padL} y2={H - padB} className="pf-axis" />
      <path d={path} className="pf-frontier" fill="none" />
      {mp.map((m) => (
        <g key={m.method}>
          <circle cx={sx(m.vol)} cy={sy(m.exp_return)} r="5" className="pf-dot" />
          <text x={sx(m.vol) + 7} y={sy(m.exp_return) + 3} className="pf-lbl">{MNAME[m.method] ?? m.method}</text>
        </g>
      ))}
      <text x={W - padR} y={H - padB + 16} className="pf-lbl" textAnchor="end">yıllık vol →</text>
      <text x={padL} y={16} className="pf-lbl">↑ beklenen getiri</text>
    </svg>
  );
}

export function Optimize({ onAuthFail }: { onAuthFail: () => void }) {
  const [req, setReq] = useState<PortfolioRequest>(BASE);
  const [data, setData] = useState<OptimizeResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setBusy(true); setErr(null);
    try { setData(await api.adminOptimize(req)); }
    catch (ex) {
      if (ex instanceof ApiError && ex.status === 401) { setToken(null); onAuthFail(); return; }
      setErr(ex instanceof ApiError ? ex.message : "Optimizasyon başarısız.");
    } finally { setBusy(false); }
  }

  const best = data ? [...data.methods].sort((a, b) => b.sharpe - a.sharpe)[0] : null;

  return (
    <div className="u-wrap">
      <div className="u-controls">
        <div className="u-thresholds">
          <label>Max hisse<input type="number" min={5} max={120} value={req.max_assets}
            onChange={(e) => setReq((r) => ({ ...r, max_assets: +e.target.value }))} /></label>
          <label>Poz. tavanı (%)<input type="number" step={1} value={req.max_weight * 100}
            onChange={(e) => setReq((r) => ({ ...r, max_weight: +e.target.value / 100 }))} /></label>
          <label>Sektör tavanı (%)<input type="number" step={1} value={req.sector_cap === null ? "" : req.sector_cap * 100}
            onChange={(e) => setReq((r) => ({ ...r, sector_cap: e.target.value === "" ? null : +e.target.value / 100 }))} /></label>
          <label>Risksiz faiz (%)<input type="number" step={1} value={req.rf_annual * 100}
            onChange={(e) => setReq((r) => ({ ...r, rf_annual: +e.target.value / 100 }))} /></label>
          <button className="a-primary u-apply" onClick={run} disabled={busy}>
            {busy ? "Karşılaştırılıyor…" : "Yöntemleri karşılaştır"}
          </button>
        </div>
      </div>

      {err && <div className="a-err">{err}</div>}

      {data && (
        <>
          <div className="u-grid">
            <div className="u-card">
              <h3>Etkin sınır & yöntemler ({data.n_assets} hisse)</h3>
              <Frontier data={data} />
            </div>
            <div className="u-card">
              <h3>½-Kelly kaldıraç (max-Sharpe portföyü)</h3>
              {data.kelly ? (
                <div className="u-tiles">
                  <div className="u-tile"><span>{num(data.kelly.full)}×</span>tam Kelly</div>
                  <div className="u-tile"><span>{num(data.kelly.half)}×</span>½-Kelly (önerilen)</div>
                  <div className="u-tile"><span>{pct(data.kelly.growth_half)}</span>½-Kelly büyüme</div>
                  <div className="u-tile muted"><span>{pct(data.kelly.port_return)} / {pct(data.kelly.port_vol)}</span>getiri / vol</div>
                </div>
              ) : <p className="u-note">Kelly hesaplanamadı.</p>}
              <p className="u-note">Kelly = (μ−rf)/σ². μ tahmini çok gürültülü olduğundan pratik seçim ½-Kelly (≈%75 büyüme, yarı varyans). 1× üstü kaldıraç riski katlar.</p>
            </div>
          </div>

          <div className="u-card">
            <h3>Yöntem karşılaştırması {best && <span className="opt-best">en yüksek Sharpe: {MNAME[best.method]}</span>}</h3>
            <div className="u-table-scroll">
              <table className="u-table">
                <thead><tr><th>Yöntem</th><th>Bekl. Getiri</th><th>Vol</th><th>Sharpe</th><th>CAGR</th><th>Max DD</th><th>Etkin N</th><th>En büyük 3</th></tr></thead>
                <tbody>
                  {data.methods.map((m) => (
                    <tr key={m.method} className={best && m.method === best.method ? "opt-row-best" : ""}>
                      <td className="u-tk">{MNAME[m.method] ?? m.method}</td>
                      <td>{pct(m.exp_return)}</td>
                      <td>{pct(m.vol)}</td>
                      <td><b>{num(m.sharpe)}</b></td>
                      <td>{pct(m.cagr)}</td>
                      <td className="u-neg">{pct(m.max_drawdown)}</td>
                      <td className="u-muted">{num(m.effective_n, 1)}</td>
                      <td className="u-sec">{m.top.slice(0, 3).map((t) => `${t.ticker} %${(t.weight * 100).toFixed(0)}`).join(" · ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="u-note">Bekl. getiri/vol geçmiş ortalamaya dayanır (in-sample); gerçek beklenti için "Portföy & Analiz"te aynı yöntemle OOS backtest çalıştır.</p>
          </div>
        </>
      )}

      {!data && !busy && !err && (
        <div className="a-placeholder">
          <span className="a-ph-ic">⟐</span>
          <h2>Yöntem karşılaştırması</h2>
          <p>Kısıtları seç, "Yöntemleri karşılaştır"a bas. Tüm yöntemler aynı evrende kurulur; etkin sınırda konumları, Sharpe/getiri/risk tablosu ve ½-Kelly kaldıraç önerisi gelir.</p>
        </div>
      )}
    </div>
  );
}
