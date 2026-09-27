import { useEffect, useState } from "react";
import { api, ApiError, setToken, type ManualRequest, type ManualResponse } from "../api";

type Row = { ticker: string; weight: string };
const START: Row[] = [
  { ticker: "THYAO", weight: "20" }, { ticker: "ASELS", weight: "20" },
  { ticker: "TUPRS", weight: "20" }, { ticker: "XAUTRY", weight: "20" },
  { ticker: "BIMAS", weight: "20" },
];

const pct = (v: number | null | undefined, d = 1) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(d)}%`;
const num = (v: number | null | undefined, d = 2) =>
  v === null || v === undefined ? "—" : v.toFixed(d);
const tl = (v: number) => `${Math.round(v).toLocaleString("tr-TR")} ₺`;
const monthLbl = (d: Date) => d.toLocaleDateString("tr-TR", { month: "short", year: "2-digit" });

function HistCurve({ curve }: { curve: ManualResponse["curve"] }) {
  if (curve.length < 2) return null;
  const W = 760, H = 300, padL = 48, padR = 66, padB = 40;
  const ly = (v: number) => Math.log(Math.max(v, 1e-6));
  const all = curve.flatMap((p) => [ly(p.port), ly(p.bench)]);
  const y0 = Math.min(...all), y1 = Math.max(...all), n = curve.length;
  const sx = (i: number) => padL + (i / (n - 1)) * (W - padL - padR);
  const sy = (v: number) => H - padB - ((ly(v) - y0) / (y1 - y0 || 1)) * (H - padB - 22);
  const line = (k: "port" | "bench") => curve.map((p, i) => `${i ? "L" : "M"}${sx(i).toFixed(1)},${sy(p[k]).toFixed(1)}`).join(" ");
  const xt = [0, Math.floor((n - 1) / 2), n - 1];
  const eP = curve[n - 1].port, eB = curve[n - 1].bench;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="pf-chart" role="img" aria-label="Tarihsel">
      <line x1={padL} y1={H - padB} x2={W - padR} y2={H - padB} className="pf-axis" />
      <line x1={padL} y1={12} x2={padL} y2={H - padB} className="pf-axis" />
      <path d={line("bench")} className="bt-bench" fill="none" />
      <path d={line("port")} className="bt-port" fill="none" />
      {xt.map((i, k) => <text key={k} x={sx(i)} y={H - padB + 16} className="pf-lbl" textAnchor="middle">{curve[i].date.slice(0, 7)}</text>)}
      <text x={sx(0) + 4} y={sy(1) - 6} className="pf-lbl">1,00₺</text>
      <text x={W - padR + 6} y={sy(eP) + 3} className="pf-lbl bt-l-port">portföy {eP.toFixed(1)}₺</text>
      <text x={W - padR + 6} y={sy(eB) + 3} className="pf-lbl bt-l-bench">1/N {eB.toFixed(1)}₺</text>
    </svg>
  );
}

function McChart({ mc, hi, onPick }: { mc: ManualResponse["mc"]; hi: string | null; onPick: (t: string | null) => void }) {
  const g = mc.grid_days; if (g.length < 2) return null;
  const W = 760, H = 340, padL = 52, padR = 70, padB = 40, n = g.length, P = mc.portfolio;
  const allV = [1, ...mc.assets.flatMap((a) => a.path), ...P.p95, ...P.p5];
  const y0 = Math.min(...allV), y1 = Math.max(...allV);
  const sx = (i: number) => padL + (i / (n - 1)) * (W - padL - padR);
  const sy = (v: number) => H - padB - ((v - y0) / (y1 - y0 || 1)) * (H - padB - 22);
  const line = (arr: number[]) => arr.map((v, i) => `${i ? "L" : "M"}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join(" ");
  const band = line(P.p95) + " " + P.p5.map((_, i) => n - 1 - i).map((i) => `L${sx(i).toFixed(1)},${sy(P.p5[i]).toFixed(1)}`).join(" ") + " Z";
  const now = new Date();
  const dAt = (o: number) => { const d = new Date(now); d.setDate(d.getDate() + o); return d; };
  const xt = [0, Math.floor((n - 1) / 2), n - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="pf-chart" role="img" aria-label="Monte Carlo">
      <line x1={padL} y1={H - padB} x2={W - padR} y2={H - padB} className="pf-axis" />
      <line x1={padL} y1={12} x2={padL} y2={H - padB} className="pf-axis" />
      <path d={band} className="pj-band" />
      {mc.assets.map((a) => (
        <path key={a.ticker} d={line(a.path)} fill="none"
          className={hi === a.ticker ? "pj-asset pj-hi" : hi ? "pj-asset pj-dim" : "pj-asset"}
          style={hi ? undefined : { opacity: 0.2 + 0.55 * Math.min(a.weight / 0.12, 1) }}
          onClick={() => onPick(hi === a.ticker ? null : a.ticker)}>
          <title>{a.ticker} · %{(a.weight * 100).toFixed(1)} · 1₺→{a.path[a.path.length - 1].toFixed(2)}₺</title>
        </path>
      ))}
      <path d={line(P.p50)} className="pj-port" fill="none" />
      <text x={sx(0) + 4} y={sy(1) - 6} className="pf-lbl">1,00₺</text>
      {xt.map((i, k) => <text key={k} x={sx(i)} y={H - padB + 16} className="pf-lbl" textAnchor="middle">{monthLbl(dAt(g[i]))}</text>)}
      <text x={W - padR + 6} y={sy(P.p50[n - 1]) + 3} className="pf-lbl pj-l-port">p50 {P.p50[n - 1].toFixed(2)}₺</text>
      <text x={W - padR + 6} y={sy(P.p95[n - 1]) + 3} className="pf-lbl">p95 {P.p95[n - 1].toFixed(2)}₺</text>
      <text x={W - padR + 6} y={sy(P.p5[n - 1]) + 3} className="pf-lbl">p5 {P.p5[n - 1].toFixed(2)}₺</text>
    </svg>
  );
}

export function Manuel({ onAuthFail }: { onAuthFail: () => void }) {
  const [rows, setRows] = useState<Row[]>(START);
  const [rf, setRf] = useState(0);
  const [horizon, setHorizon] = useState(9);
  const [notional, setNotional] = useState(1_000_000);
  const [opts, setOpts] = useState<{ ticker: string; name: string | null }[]>([]);
  const [data, setData] = useState<ManualResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [hi, setHi] = useState<string | null>(null);

  useEffect(() => { api.adminTickers().then((r) => setOpts(r.tickers)).catch(() => {}); }, []);

  const sum = rows.reduce((a, r) => a + (parseFloat(r.weight) || 0), 0);
  const setRow = (i: number, k: keyof Row, v: string) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  async function run() {
    setBusy(true); setErr(null); setHi(null);
    const holdings = rows
      .filter((r) => r.ticker.trim() && (parseFloat(r.weight) || 0) > 0)
      .map((r) => ({ ticker: r.ticker.trim().toUpperCase(), weight: parseFloat(r.weight) }));
    if (holdings.length === 0) { setErr("En az bir hisse ve ağırlık girin."); setBusy(false); return; }
    const body: ManualRequest = { holdings, rf_annual: rf, window_years: 5, horizon_months: horizon, notional };
    try { setData(await api.adminManual(body)); }
    catch (ex) {
      if (ex instanceof ApiError && ex.status === 401) { setToken(null); onAuthFail(); return; }
      setErr(ex instanceof ApiError ? ex.message : "Test başarısız.");
    } finally { setBusy(false); }
  }

  const m = data?.metrics;

  return (
    <div className="u-wrap">
      <div className="u-controls">
        <datalist id="tk-list">
          {opts.map((o) => <option key={o.ticker} value={o.ticker}>{o.name ?? ""}</option>)}
        </datalist>
        <div className="mn-rows">
          {rows.map((r, i) => (
            <div key={i} className="mn-row">
              <input list="tk-list" placeholder="KOD" value={r.ticker}
                onChange={(e) => setRow(i, "ticker", e.target.value)} className="mn-tk" />
              <input type="number" placeholder="%" value={r.weight}
                onChange={(e) => setRow(i, "weight", e.target.value)} className="mn-w" />
              <button className="mn-x" onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}>×</button>
            </div>
          ))}
          <button className="pf-btn" onClick={() => setRows((rs) => [...rs, { ticker: "", weight: "" }])}>+ satır</button>
        </div>
        <div className="u-thresholds">
          <span className={`mn-sum ${Math.abs(sum - 100) > 0.5 ? "mn-warn" : ""}`}>toplam %{sum.toFixed(1)} {Math.abs(sum - 100) > 0.5 ? "(normalize edilir)" : ""}</span>
          <label>Risksiz faiz (%)<input type="number" step={1} value={rf * 100} onChange={(e) => setRf(+e.target.value / 100)} /></label>
          <label>MC ufku (ay)<input type="number" min={1} max={36} value={horizon} onChange={(e) => setHorizon(+e.target.value)} /></label>
          <label>Portföy (₺)<input type="number" step={100000} value={notional} onChange={(e) => setNotional(+e.target.value)} /></label>
          <button className="a-primary u-apply" onClick={run} disabled={busy}>{busy ? "Test ediliyor…" : "Test et"}</button>
        </div>
      </div>

      {err && <div className="a-err">{err}</div>}
      {data && data.missing.length > 0 && <div className="pf-ok">Bulunamayan/atlanan kodlar: {data.missing.join(", ")}</div>}

      {data && m && (
        <>
          <div className="u-tiles">
            <div className="u-tile"><span>{pct(m.cagr)}</span>CAGR (tarihsel)</div>
            <div className="u-tile"><span>{pct(m.geo_growth)}</span>geo. büyüme</div>
            <div className="u-tile"><span>{pct(m.ann_vol)}</span>yıllık vol</div>
            <div className="u-tile"><span>{num(m.sharpe)}</span>Sharpe ±{num(m.sharpe_se)}</div>
            <div className="u-tile"><span>{pct(m.psr_vs_0, 0)}</span>PSR</div>
            <div className="u-tile"><span>{pct(m.max_drawdown)}</span>max düşüş</div>
            <div className="u-tile"><span>{num(m.sortino)}</span>Sortino</div>
            <div className="u-tile muted"><span>{pct(data.benchmark.cagr)} · {num(data.benchmark.sharpe)}</span>1/N CAGR·Sharpe</div>
          </div>

          <div className="u-card">
            <h3>Tarihsel performans — portföyün vs 1/N ({data.start.slice(0, 7)}→{data.end.slice(0, 7)})</h3>
            <HistCurve curve={data.curve} />
            <p className="u-note">Sabit ağırlıklı, günlük dengeli. {data.n_assets} hisse, {data.observations} gün. Sharpe belirsizliğiyle (±SE); PSR &gt;%95 ≈ anlamlı.</p>
          </div>

          <div className="u-card">
            <h3>Monte Carlo projeksiyon — {data.mc.horizon_months} ay (bekl. {pct(data.mc.exp_return_ann)}, vol {pct(data.mc.exp_vol_ann)})</h3>
            <McChart mc={data.mc} hi={hi} onPick={setHi} />
            <div className="pj-legend">
              {data.mc.assets.map((a) => (
                <button key={a.ticker} className={`pj-chip ${hi === a.ticker ? "on" : ""}`}
                  onClick={() => setHi(hi === a.ticker ? null : a.ticker)}>{a.ticker} <b>%{(a.weight * 100).toFixed(0)}</b></button>
              ))}
              {hi && <button className="pj-chip pj-clear" onClick={() => setHi(null)}>× temizle</button>}
            </div>
          </div>

          <div className="u-card">
            <h3>{tl(data.notional)} portföyde 1 gün kayıp (tarihsel)</h3>
            <div className="u-tiles">
              <div className="u-tile"><span>{tl(data.var_tl.var99)}</span>VaR %99 ({pct(data.var_pct.var99)})</div>
              <div className="u-tile"><span>{tl(data.var_tl.cvar99)}</span>CVaR %99 ({pct(data.var_pct.cvar99)})</div>
              <div className="u-tile"><span>{tl(data.var_tl.var95)}</span>VaR %95</div>
              <div className="u-tile"><span>{num(data.concentration.effective_n, 1)}</span>etkin N</div>
              <div className="u-tile"><span>{pct(data.factor.systematic_share)}</span>sistematik pay</div>
              <div className="u-tile muted"><span>{num(data.factor.gold_beta)}</span>altın betası</div>
            </div>
          </div>

          <div className="u-card">
            <h3>Bileşen risk (VaR %99 payı)</h3>
            <div className="u-table-scroll">
              <table className="u-table">
                <thead><tr><th>Kod</th><th>Sektör</th><th>Ağırlık</th><th>Risk payı</th><th>Bileşen VaR</th></tr></thead>
                <tbody>
                  {data.components.map((c) => (
                    <tr key={c.ticker}>
                      <td className="u-tk">{c.ticker}</td><td className="u-sec">{c.sector}</td>
                      <td>{pct(c.weight)}</td><td><b>{pct(c.risk_share)}</b></td><td className="u-muted">{tl(c.comp_var99_tl)}</td>
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
          <span className="a-ph-ic">✎</span>
          <h2>Manuel test</h2>
          <p>Kendi hisse kodlarını ve yüzdelerini gir (kod kutusunda otomatik tamamlama var; XAUTRY/XAGTRY = gram altın/gümüş), "Test et"e bas. Sabit ağırlıklı tarihsel backtest, Sharpe/PSR, Monte Carlo ve VaR/bileşen risk çıkar.</p>
        </div>
      )}
    </div>
  );
}
