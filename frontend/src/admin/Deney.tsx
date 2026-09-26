import { useState } from "react";
import { api, ApiError, setToken, type ExperimentRequest, type ExperimentResponse } from "../api";

const DEFAULT_UNIVERSE: ExperimentRequest["universe"] = {
  filters: { watchlist: true, neg_equity: true, persistent_loss: true, altman: true, liquidity: true, limit_down: true, drawdown: true },
  altman_min: 1.1, adv_min_tl: 5_000_000, loss_years_min: 3, limit_down_days_min: 2, drawdown_limit: 0.90,
  vol_min: null, vol_max: null, geo_min: null,
};
const DEFAULTS: ExperimentRequest = {
  universe: DEFAULT_UNIVERSE, rf_annual: 0.35, var_limit: 0.03,
  window_years: 5, train_years: 2, test_months: 3, horizon_months: 9,
};
const MNAME: Record<string, string> = {
  max_sharpe: "Max Sharpe", min_variance: "Min Varyans", risk_parity: "Risk Parity", hrp: "HRP",
};
const pct = (v: number | null | undefined, d = 1) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(d)}%`;
const num = (v: number | null | undefined, d = 2) =>
  v === null || v === undefined ? "—" : v.toFixed(d);
const capLbl = (v: number | null) => v === null ? "yok" : `%${Math.round(v * 100)}`;

function Curve({ curve }: { curve: ExperimentResponse["best"]["backtest"]["curve"] }) {
  if (curve.length < 2) return null;
  const W = 760, H = 300, padL = 48, padR = 66, padB = 40;
  const ly = (v: number) => Math.log(Math.max(v, 1e-6));
  const all = curve.flatMap((p) => [ly(p.port), ly(p.bench)]);
  const y0 = Math.min(...all), y1 = Math.max(...all), n = curve.length;
  const sx = (i: number) => padL + (i / (n - 1)) * (W - padL - padR);
  const sy = (v: number) => H - padB - ((ly(v) - y0) / (y1 - y0 || 1)) * (H - padB - 22);
  const line = (k: "port" | "bench") => curve.map((p, i) => `${i ? "L" : "M"}${sx(i).toFixed(1)},${sy(p[k]).toFixed(1)}`).join(" ");
  const xticks = [0, Math.floor((n - 1) / 2), n - 1];
  const endP = curve[n - 1].port, endB = curve[n - 1].bench;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="pf-chart" role="img" aria-label="En iyi OOS eğrisi">
      <line x1={padL} y1={H - padB} x2={W - padR} y2={H - padB} className="pf-axis" />
      <line x1={padL} y1={12} x2={padL} y2={H - padB} className="pf-axis" />
      <path d={line("bench")} className="bt-bench" fill="none" />
      <path d={line("port")} className="bt-port" fill="none" />
      {xticks.map((i, k) => (
        <text key={k} x={sx(i)} y={H - padB + 16} className="pf-lbl" textAnchor="middle">{curve[i].date.slice(0, 7)}</text>
      ))}
      <text x={sx(0) + 4} y={sy(1) - 6} className="pf-lbl">1,00₺</text>
      <text x={W - padR + 6} y={sy(endP) + 3} className="pf-lbl bt-l-port">portföy {endP.toFixed(1)}₺</text>
      <text x={W - padR + 6} y={sy(endB) + 3} className="pf-lbl bt-l-bench">1/N {endB.toFixed(1)}₺</text>
    </svg>
  );
}

export function Deney({ onAuthFail }: { onAuthFail: () => void }) {
  const [req, setReq] = useState<ExperimentRequest>(DEFAULTS);
  const [data, setData] = useState<ExperimentResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setBusy(true); setErr(null);
    try { setData(await api.adminExperiment(req)); }
    catch (ex) {
      if (ex instanceof ApiError && ex.status === 401) { setToken(null); onAuthFail(); return; }
      setErr(ex instanceof ApiError ? ex.message : "Deney başarısız.");
    } finally { setBusy(false); }
  }

  const b = data?.best;

  return (
    <div className="u-wrap">
      <div className="u-controls">
        <div className="u-thresholds">
          <label>Risksiz faiz (%)<input type="number" step={1} value={req.rf_annual * 100}
            onChange={(e) => setReq((r) => ({ ...r, rf_annual: +e.target.value / 100 }))} /></label>
          <label>VaR%99 üst (%)<input type="number" step={0.5} value={req.var_limit * 100}
            onChange={(e) => setReq((r) => ({ ...r, var_limit: +e.target.value / 100 }))} /></label>
          <label>Train (yıl)<input type="number" step={0.5} min={0.5} max={5} value={req.train_years}
            onChange={(e) => setReq((r) => ({ ...r, train_years: +e.target.value }))} /></label>
          <label>Test (ay)<input type="number" min={1} max={12} value={req.test_months}
            onChange={(e) => setReq((r) => ({ ...r, test_months: +e.target.value }))} /></label>
          <button className="a-primary u-apply" onClick={run} disabled={busy}>
            {busy ? "Taranıyor… (uzun sürebilir)" : "Deneyi çalıştır"}
          </button>
        </div>
        <p className="u-note">
          Izgara: max hisse {DEFAULTS.universe ? "[20,30,40,50]" : ""} × poz.tavanı [%10,15,20,25] × sektör tavanı [%30,50,yok] × 4 yöntem.
          rf=%{(req.rf_annual * 100).toFixed(0)}'te kurulur, günlük VaR%99 &gt; %{(req.var_limit * 100).toFixed(1)} olanlar elenir, kalanların en iyileri OOS backtest + MC ile sınanır.
        </p>
      </div>

      {err && <div className="a-err">{err}</div>}

      {data && b && (
        <>
          <div className="u-tiles">
            <div className="u-tile"><span>{data.total}</span>kombinasyon</div>
            <div className="u-tile"><span>{data.var_eliminated}</span>VaR'dan elendi</div>
            <div className="u-tile"><span>{data.survivors}</span>hayatta kalan</div>
            <div className="u-tile"><span>{num(b.oos_sharpe)}</span>en iyi OOS Sharpe</div>
            <div className="u-tile"><span>{pct(b.oos_cagr)}</span>OOS CAGR</div>
            <div className="u-tile"><span>{b.real_cagr != null ? pct(b.real_cagr) : "—"}</span>reel CAGR</div>
          </div>

          <div className="u-card">
            <h3>🏆 En iyi kombinasyon</h3>
            <div className="dn-best">
              <span className="dn-tag">{MNAME[b.method] ?? b.method}</span>
              <span className="dn-tag">max {b.max_assets} hisse</span>
              <span className="dn-tag">poz. tavanı %{Math.round(b.max_weight * 100)}</span>
              <span className="dn-tag">sektör tavanı {capLbl(b.sector_cap)}</span>
              <span className="dn-tag">VaR%99 {pct(b.var99)}</span>
              <span className="dn-tag">in-sample Sharpe {num(b.in_sample_sharpe)}</span>
            </div>
            <div className="u-tiles" style={{ marginTop: 12 }}>
              <div className="u-tile"><span>{num(b.oos_sharpe)}</span>OOS Sharpe</div>
              <div className="u-tile"><span>{pct(b.oos_cagr)}</span>OOS CAGR</div>
              <div className="u-tile"><span>{pct(b.oos_max_drawdown)}</span>OOS max düşüş</div>
              {b.mc && <div className="u-tile"><span>{num(b.mc.p50_end)}×</span>MC medyan ({b.mc.horizon_months}ay)</div>}
              {b.mc && <div className="u-tile muted"><span>{num(b.mc.p5_end)}× / {num(b.mc.p95_end)}×</span>MC p5 / p95</div>}
            </div>
            <Curve curve={b.backtest.curve} />
            <p className="u-note">OOS {b.backtest.start.slice(0, 7)}→{b.backtest.end.slice(0, 7)}, {b.backtest.rebalances} rebalans. 1/N: CAGR {pct(b.backtest.benchmark.cagr)}, Sharpe {num(b.backtest.benchmark.sharpe)}.</p>
          </div>

          <div className="u-grid">
            <div className="u-card">
              <h3>En iyi portföy ağırlıkları ({b.weights.length})</h3>
              <div className="u-table-scroll">
                <table className="u-table">
                  <thead><tr><th>Kod</th><th>Sektör</th><th>Ağırlık</th></tr></thead>
                  <tbody>
                    {b.weights.map((w) => (
                      <tr key={w.ticker}><td className="u-tk">{w.ticker}</td><td className="u-sec">{w.sector}</td><td>{pct(w.weight)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="u-card">
              <h3>Değerlendirilen en iyi adaylar (OOS)</h3>
              <div className="u-table-scroll">
                <table className="u-table">
                  <thead><tr><th>Yöntem</th><th>Hisse</th><th>Poz.</th><th>Sekt.</th><th>VaR99</th><th>OOS Sharpe</th></tr></thead>
                  <tbody>
                    {data.top.map((t, i) => (
                      <tr key={i} className={i === 0 ? "opt-row-best" : ""}>
                        <td className="u-tk">{MNAME[t.method] ?? t.method}</td>
                        <td>{t.max_assets}</td>
                        <td>%{Math.round(t.max_weight * 100)}</td>
                        <td>{capLbl(t.sector_cap)}</td>
                        <td className="u-muted">{pct(t.var99)}</td>
                        <td><b>{num(t.oos_sharpe)}</b></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}

      {!data && !busy && !err && (
        <div className="a-placeholder">
          <span className="a-ph-ic">⚗</span>
          <h2>Deney — kısıt taraması</h2>
          <p>rf=%35'te tüm (max hisse × poz. tavanı × sektör tavanı × yöntem) kombinasyonlarını tarar, günlük VaR%99 &gt; %3 olanları eler, kalanların en iyilerini OOS backtest + Monte Carlo ile sınayıp en yüksek OOS-Sharpe portföyünü tüm ağırlıklarıyla verir. Birkaç dakika sürebilir.</p>
        </div>
      )}
    </div>
  );
}
