import { useState } from "react";
import {
  api, ApiError, setToken,
  type PortfolioMethod, type PortfolioRequest, type PortfolioResponse,
} from "../api";

const DEFAULT_UNIVERSE: PortfolioRequest["universe"] = {
  filters: { watchlist: true, neg_equity: true, persistent_loss: true, altman: true, liquidity: true },
  altman_min: 1.1, adv_min_tl: 5_000_000, loss_years_min: 3,
  vol_min: null, vol_max: null, geo_min: null,
};

const DEFAULTS: PortfolioRequest = {
  universe: DEFAULT_UNIVERSE,
  method: "max_sharpe",
  max_assets: 50,
  max_weight: 0.10,
  sector_cap: 0.30,
  rf_annual: 0,
  window_years: 5,
};

const METHODS: [PortfolioMethod, string, string][] = [
  ["max_sharpe", "Max Sharpe", "Tangency (LW shrinkage + kısıtlar)"],
  ["min_variance", "Min Varyans", "En düşük oynaklık"],
  ["risk_parity", "Risk Parity", "Eşit risk katkısı (ERC)"],
  ["hrp", "HRP", "Hiyerarşik risk paritesi"],
  ["equal", "Eşit Ağırlık", "1/N referans"],
];

const pct = (v: number | null | undefined, d = 1) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(d)}%`;
const num = (v: number | null | undefined, d = 2) =>
  v === null || v === undefined ? "—" : v.toFixed(d);

/* Etkin sınır + portföy noktası — kompakt SVG */
function Frontier({ data }: { data: PortfolioResponse }) {
  if (!data.frontier || data.frontier.length < 2) return null;
  const pts = data.frontier;
  const W = 520, H = 300, pad = 42;
  const xs = pts.map((p) => p.vol).concat(data.port_point.vol);
  const ys = pts.map((p) => p.ret).concat(data.port_point.ret);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const sx = (v: number) => pad + ((v - x0) / (x1 - x0 || 1)) * (W - pad - 12);
  const sy = (v: number) => H - pad - ((v - y0) / (y1 - y0 || 1)) * (H - pad - 12);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${sx(p.vol).toFixed(1)},${sy(p.ret).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="pf-chart" role="img" aria-label="Etkin sınır">
      <line x1={pad} y1={H - pad} x2={W - 12} y2={H - pad} className="pf-axis" />
      <line x1={pad} y1={12} x2={pad} y2={H - pad} className="pf-axis" />
      <path d={path} className="pf-frontier" fill="none" />
      <circle cx={sx(data.port_point.vol)} cy={sy(data.port_point.ret)} r="6" className="pf-dot" />
      <text x={W - 12} y={H - pad + 18} className="pf-lbl" textAnchor="end">yıllık vol →</text>
      <text x={pad - 6} y={16} className="pf-lbl">↑ yıllık getiri</text>
      <text x={sx(data.port_point.vol) + 10} y={sy(data.port_point.ret) - 8} className="pf-lbl pf-lbl-strong">
        portföy · {pct(data.port_point.ret)} / {pct(data.port_point.vol)}
      </text>
    </svg>
  );
}

export function Portfolio({ onAuthFail }: { onAuthFail: () => void }) {
  const [req, setReq] = useState<PortfolioRequest>(DEFAULTS);
  const [data, setData] = useState<PortfolioResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setBusy(true); setErr(null);
    try {
      setData(await api.adminPortfolio(req));
    } catch (ex) {
      if (ex instanceof ApiError && ex.status === 401) { setToken(null); onAuthFail(); return; }
      setErr(ex instanceof ApiError ? ex.message : "Portföy kurulamadı.");
    } finally { setBusy(false); }
  }

  const m = data?.metrics;

  return (
    <div className="u-wrap">
      <div className="u-controls">
        <div className="pf-methods">
          {METHODS.map(([k, label, desc]) => (
            <button key={k} className={`pf-method ${req.method === k ? "on" : ""}`}
              onClick={() => setReq((r) => ({ ...r, method: k }))} title={desc}>
              {label}
            </button>
          ))}
        </div>
        <div className="u-thresholds">
          <label>Max hisse
            <input type="number" min={5} max={120} value={req.max_assets}
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
          <label>Risksiz faiz (%)
            <input type="number" step={1} value={req.rf_annual * 100}
              onChange={(e) => setReq((r) => ({ ...r, rf_annual: +e.target.value / 100 }))} />
          </label>
          <label>Pencere (yıl)
            <input type="number" min={1} max={5} value={req.window_years}
              onChange={(e) => setReq((r) => ({ ...r, window_years: +e.target.value }))} />
          </label>
          <button className="a-primary u-apply" onClick={run} disabled={busy}>
            {busy ? "Kuruluyor…" : "Portföyü kur"}
          </button>
        </div>
      </div>

      {err && <div className="a-err">{err}</div>}

      {data && m && (
        <>
          <div className="u-tiles">
            <div className="u-tile"><span>{pct(m.cagr)}</span>CAGR</div>
            <div className="u-tile"><span>{pct(m.geo_growth)}</span>geo. büyüme</div>
            <div className="u-tile"><span>{pct(m.ann_vol)}</span>yıllık vol</div>
            <div className="u-tile"><span>{num(m.sharpe)}</span>Sharpe ±{num(m.sharpe_se)}</div>
            <div className="u-tile"><span>{pct(m.psr_vs_0, 0)}</span>PSR (&gt;0)</div>
            <div className="u-tile"><span>{pct(m.max_drawdown)}</span>max düşüş</div>
            <div className="u-tile muted"><span>{data.n_assets} · {num(data.effective_n, 1)}</span>hisse · etkin</div>
          </div>

          <div className="u-grid">
            <div className="u-card">
              <h3>Etkin sınır & portföy</h3>
              {data.frontier ? <Frontier data={data} />
                : <p className="u-note">Bu yöntem için sınır çizilmedi (min-var/max-Sharpe'de gösterilir).</p>}
              <p className="u-note">
                Sharpe belirsizliğiyle verilir (±SE); PSR &gt;%95 ≈ anlamlı. Vol sürüklenme:
                CAGR ≈ aritmetik − σ²/2, düşük vol geometrik getiriyi korur.
              </p>
            </div>

            <div className="u-card">
              <h3>Sektör dağılımı</h3>
              <div className="u-sectors">
                {data.sectors.slice(0, 12).map((s) => (
                  <div key={s.sector} className="u-sector">
                    <div className="u-sector-top"><span title={s.sector}>{s.sector}</span><b>{pct(s.weight)}</b></div>
                    <div className="u-bar"><div style={{ width: `${s.weight * 100}%` }} /></div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="u-card">
            <h3>Ağırlıklar ({data.weights.length} pozisyon)</h3>
            <div className="u-table-scroll">
              <table className="u-table">
                <thead><tr><th>Kod</th><th>Sektör</th><th>Ağırlık</th><th>Risk katkısı</th></tr></thead>
                <tbody>
                  {data.weights.map((w) => (
                    <tr key={w.ticker}>
                      <td className="u-tk">{w.ticker}</td>
                      <td className="u-sec">{w.sector}</td>
                      <td>{pct(w.weight)}</td>
                      <td className="u-muted">{pct(w.risk_contrib)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {!data && !busy && !err && (
        <div className="a-placeholder">
          <span className="a-ph-ic">◈</span>
          <h2>Portföy kur</h2>
          <p>Yöntem ve kısıtları seçip "Portföyü kur"a bas. Uygun evren, Varlık Evreni varsayılan filtreleriyle süzülür.</p>
        </div>
      )}
    </div>
  );
}
