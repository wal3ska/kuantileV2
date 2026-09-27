import { useState } from "react";
import {
  api, ApiError, setToken,
  type BacktestResponse, type PortfolioMethod, type PortfolioRequest,
  type PortfolioResponse, type PositionIn, type ProjectionResponse, type RiskFree,
} from "../api";
import { exportReport } from "../report";

const DEFAULT_UNIVERSE: PortfolioRequest["universe"] = {
  filters: { watchlist: true, neg_equity: true, persistent_loss: true, altman: true, liquidity: true, limit_down: true, drawdown: true },
  altman_min: 1.1, adv_min_tl: 5_000_000, loss_years_min: 3, limit_down_days_min: 2, drawdown_limit: 0.90,
  vol_min: null, vol_max: null, geo_min: null,
};

const DEFAULTS: PortfolioRequest = {
  universe: DEFAULT_UNIVERSE, method: "max_sharpe",
  max_assets: 50, max_weight: 0.10, sector_cap: 0.30, rf_annual: 0, window_years: 5,
};

const METHODS: [PortfolioMethod, string, string][] = [
  ["max_sharpe", "Max Sharpe", "Tangency (LW shrinkage + kısıtlar)"],
  ["min_variance", "Min Varyans", "En düşük oynaklık"],
  ["risk_parity", "Risk Parity", "Eşit risk katkısı (ERC)"],
  ["hrp", "HRP", "Hiyerarşik risk paritesi"],
  ["equal", "Eşit Ağırlık", "1/N referans"],
  ["mc_max_return", "MC Max Getiri", "Monte Carlo ile en yüksek beklenen getiri (agresif; riski projeksiyon/backtest'te gör)"],
];

const NOTIONAL = 1_000_000;              // PDF/aktarım için varsayılan portföy büyüklüğü
const COMMODITY_MAP: Record<string, { ticker: string; name: string }> = {
  XAUTRY: { ticker: "GRAMALTIN", name: "Altın (Gram TL)" },   // ana sitede karşılığı olan tek emtia
};

const pct = (v: number | null | undefined, d = 1) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(d)}%`;
const num = (v: number | null | undefined, d = 2) =>
  v === null || v === undefined ? "—" : v.toFixed(d);

/* Portföy ağırlıklarını ana site pozisyonlarına çevirir (BIST + gram altın). */
function toPositions(weights: PortfolioResponse["weights"]): PositionIn[] {
  const out: PositionIn[] = [];
  for (const w of weights) {
    if (!w.last_price || w.last_price <= 0) continue;
    let ticker: string, name: string, category: string;
    if (w.ticker in COMMODITY_MAP) {
      ({ ticker, name } = COMMODITY_MAP[w.ticker]); category = "Emtia";
    } else if (w.ticker === "XAGTRY") {
      continue;                       // gram gümüşün ana sitede fiyatlaması yok (yalnız altın map'li)
    } else {
      ticker = `${w.ticker}.IS`; name = w.ticker; category = "BIST";
    }
    out.push({ name, ticker, currency: "TRY", source: "yahoo", category,
               quantity: (w.weight * NOTIONAL) / w.last_price, cost: null });
  }
  return out;
}

/* ---------- grafikler ---------- */
function Frontier({ data }: { data: PortfolioResponse }) {
  if (!data.frontier || data.frontier.length < 2) return null;
  const pts = data.frontier, W = 520, H = 280, pad = 42;
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
      <text x={sx(data.port_point.vol) + 9} y={sy(data.port_point.ret) - 8} className="pf-lbl pj-l-port">
        {`getiri ${(data.port_point.ret * 100).toFixed(0)}% / vol ${(data.port_point.vol * 100).toFixed(0)}%`}
      </text>
      <text x={pad} y={H - pad + 16} className="pf-lbl">{(x0 * 100).toFixed(0)}%</text>
      <text x={W - 12} y={H - pad + 16} className="pf-lbl" textAnchor="end">vol {(x1 * 100).toFixed(0)}%</text>
      <text x={pad - 6} y={sy(y1) + 3} className="pf-lbl" textAnchor="end">{(y1 * 100).toFixed(0)}%</text>
      <text x={pad - 6} y={sy(y0) + 3} className="pf-lbl" textAnchor="end">{(y0 * 100).toFixed(0)}%</text>
      <text x={pad - 6} y={16} className="pf-lbl">↑ getiri</text>
    </svg>
  );
}

function BtCurve({ data }: { data: BacktestResponse }) {
  const c = data.curve; if (c.length < 2) return null;
  const W = 760, H = 320, padL = 48, padR = 66, padB = 40;
  const ly = (v: number) => Math.log(Math.max(v, 1e-6));
  const all = c.flatMap((p) => [ly(p.port), ly(p.bench)]);
  const y0 = Math.min(...all), y1 = Math.max(...all), n = c.length;
  const sx = (i: number) => padL + (i / (n - 1)) * (W - padL - padR);
  const sy = (v: number) => H - padB - ((ly(v) - y0) / (y1 - y0 || 1)) * (H - padB - 22);
  const line = (k: "port" | "bench") => c.map((p, i) => `${i ? "L" : "M"}${sx(i).toFixed(1)},${sy(p[k]).toFixed(1)}`).join(" ");
  const yr = (s: string) => s.slice(0, 7);
  const xticks = [0, Math.floor((n - 1) / 2), n - 1];
  const endP = c[n - 1].port, endB = c[n - 1].bench;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="pf-chart" role="img" aria-label="OOS equity">
      <line x1={padL} y1={H - padB} x2={W - padR} y2={H - padB} className="pf-axis" />
      <line x1={padL} y1={12} x2={padL} y2={H - padB} className="pf-axis" />
      <path d={line("bench")} className="bt-bench" fill="none" />
      <path d={line("port")} className="bt-port" fill="none" />
      {xticks.map((i, k) => (
        <text key={k} x={sx(i)} y={H - padB + 16} className="pf-lbl" textAnchor="middle">{yr(c[i].date)}</text>
      ))}
      <text x={sx(0) + 4} y={sy(1) - 6} className="pf-lbl">1,00₺</text>
      <text x={W - padR + 6} y={sy(endP) + 3} className="pf-lbl bt-l-port">portföy {endP.toFixed(1)}₺</text>
      <text x={W - padR + 6} y={sy(endB) + 3} className="pf-lbl bt-l-bench">1/N {endB.toFixed(1)}₺</text>
      <text x={padL} y={16} className="pf-lbl">↑ 1₺ → (log ölçek)</text>
    </svg>
  );
}

const monthLbl = (d: Date) => d.toLocaleDateString("tr-TR", { month: "short", year: "2-digit" });

function ProjChart({ data, hi, onPick }: { data: ProjectionResponse; hi: string | null; onPick: (t: string | null) => void }) {
  const g = data.grid_days; if (g.length < 2) return null;
  const W = 760, H = 360, padL = 52, padR = 70, padB = 40, n = g.length;
  const P = data.portfolio;
  const allV = [1, ...data.assets.flatMap((a) => a.path), ...P.p95, ...P.p5];
  const y0 = Math.min(...allV), y1 = Math.max(...allV);
  const sx = (i: number) => padL + (i / (n - 1)) * (W - padL - padR);
  const sy = (v: number) => H - padB - ((v - y0) / (y1 - y0 || 1)) * (H - padB - 22);
  const line = (arr: number[]) => arr.map((v, i) => `${i ? "L" : "M"}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join(" ");
  const band = line(P.p95) + " " + P.p5.map((_, i) => n - 1 - i)
    .map((i) => `L${sx(i).toFixed(1)},${sy(P.p5[i]).toFixed(1)}`).join(" ") + " Z";
  const now = new Date();
  const dateAt = (dayOff: number) => { const d = new Date(now); d.setDate(d.getDate() + dayOff); return d; };
  const xticks = [0, Math.floor((n - 1) / 3), Math.floor((2 * (n - 1)) / 3), n - 1];
  const yticks = [y0, (y0 + y1) / 2, y1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="pf-chart" role="img" aria-label="Monte Carlo projeksiyon">
      <line x1={padL} y1={H - padB} x2={W - padR} y2={H - padB} className="pf-axis" />
      <line x1={padL} y1={12} x2={padL} y2={H - padB} className="pf-axis" />
      {yticks.map((v, k) => (
        <text key={k} x={padL - 6} y={sy(v) + 3} className="pf-lbl" textAnchor="end">{v.toFixed(2)}₺</text>
      ))}
      {xticks.map((i, k) => (
        <text key={k} x={sx(i)} y={H - padB + 16} className="pf-lbl" textAnchor="middle">{monthLbl(dateAt(g[i]))}</text>
      ))}
      <path d={band} className="pj-band" />
      {data.assets.map((a) => {
        const cls = hi === a.ticker ? "pj-asset pj-hi" : hi ? "pj-asset pj-dim" : "pj-asset";
        return (
          <path key={a.ticker} d={line(a.path)} className={cls} fill="none"
            style={hi ? undefined : { opacity: 0.2 + 0.55 * Math.min(a.weight / 0.12, 1) }}
            onClick={() => onPick(hi === a.ticker ? null : a.ticker)}>
            <title>{a.ticker} · %{(a.weight * 100).toFixed(1)} · 1₺→{a.path[a.path.length - 1].toFixed(2)}₺</title>
          </path>
        );
      })}
      <path d={line(P.p50)} className="pj-port" fill="none" />
      {/* baslangic ve bitis tutarlari */}
      <text x={sx(0) + 4} y={sy(1) - 6} className="pf-lbl">1,00₺</text>
      <text x={W - padR + 6} y={sy(P.p95[n - 1]) + 3} className="pf-lbl">p95 {P.p95[n - 1].toFixed(2)}₺</text>
      <text x={W - padR + 6} y={sy(P.p50[n - 1]) + 3} className="pf-lbl pj-l-port">p50 {P.p50[n - 1].toFixed(2)}₺</text>
      <text x={W - padR + 6} y={sy(P.p5[n - 1]) + 3} className="pf-lbl">p5 {P.p5[n - 1].toFixed(2)}₺</text>
    </svg>
  );
}

export function Portfolio({ onAuthFail }: { onAuthFail: () => void }) {
  const [req, setReq] = useState<PortfolioRequest>(DEFAULTS);
  const [data, setData] = useState<PortfolioResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [bt, setBt] = useState<BacktestResponse | null>(null);
  const [btBusy, setBtBusy] = useState(false);
  const [train, setTrain] = useState(3);
  const [test, setTest] = useState(3);

  const [pj, setPj] = useState<ProjectionResponse | null>(null);
  const [pjBusy, setPjBusy] = useState(false);
  const [horizon, setHorizon] = useState(9);   // ~Haz 2027 (bugünden)
  const [hi, setHi] = useState<string | null>(null);   // projeksiyonda vurgulanan hisse

  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  const authGuard = (ex: unknown) => {
    if (ex instanceof ApiError && ex.status === 401) { setToken(null); onAuthFail(); return true; }
    return false;
  };

  async function build() {
    setBusy(true); setErr(null); setBt(null); setPj(null); setNote(null);
    try { setData(await api.adminPortfolio(req)); }
    catch (ex) { if (!authGuard(ex)) setErr(ex instanceof ApiError ? ex.message : "Portföy kurulamadı."); }
    finally { setBusy(false); }
  }

  async function runBacktest() {
    setBtBusy(true); setNote(null);
    try { setBt(await api.adminBacktest({ ...req, train_years: train, test_months: test })); }
    catch (ex) { if (!authGuard(ex)) setNote({ ok: false, text: ex instanceof ApiError ? ex.message : "Backtest başarısız." }); }
    finally { setBtBusy(false); }
  }

  async function runProjection() {
    setPjBusy(true); setNote(null);
    try { setPj(await api.adminProjection({ ...req, horizon_months: horizon })); }
    catch (ex) { if (!authGuard(ex)) setNote({ ok: false, text: ex instanceof ApiError ? ex.message : "Projeksiyon başarısız." }); }
    finally { setPjBusy(false); }
  }

  async function saveToKuantile() {
    if (!data) return;
    const positions = toPositions(data.weights);
    if (positions.length === 0) { setNote({ ok: false, text: "Aktarılabilir pozisyon yok." }); return; }
    if (!window.confirm(`Kuantile'daki kayıtlı portföyün ${positions.length} pozisyonla değiştirilecek. Onaylıyor musun?`)) return;
    try {
      await api.savePortfolio(positions, []);
      setNote({ ok: true, text: `${positions.length} pozisyon Kuantile hesabına kaydedildi (kuantile.com'da görünür).` });
    } catch (ex) {
      if (ex instanceof ApiError && ex.status === 401) {
        setNote({ ok: false, text: "Kaydetmek için önce kuantile.com'da hesabınıza giriş yapın." });
      } else {
        setNote({ ok: false, text: ex instanceof ApiError ? ex.message : "Kaydedilemedi." });
      }
    }
  }

  async function exportPDF() {
    if (!data) return;
    const positions = toPositions(data.weights);
    if (positions.length === 0) { setNote({ ok: false, text: "Rapor için pozisyon yok." }); return; }
    setNote({ ok: true, text: "Risk raporu hesaplanıyor…" });
    try {
      const rf: RiskFree = { kind: "rate", annual_rate: req.rf_annual || 0.45 };
      const analyzed = await api.analyze(positions, [], 0.99, rf);
      await exportReport(analyzed, positions, "tr", "Quant Lab");
      setNote({ ok: true, text: "PDF yazdırma penceresi açıldı." });
    } catch (ex) { if (!authGuard(ex)) setNote({ ok: false, text: ex instanceof ApiError ? ex.message : "Rapor üretilemedi." }); }
  }

  const m = data?.metrics;

  return (
    <div className="u-wrap">
      {/* kontroller */}
      <div className="u-controls">
        <div className="pf-methods">
          {METHODS.map(([k, label, desc]) => (
            <button key={k} className={`pf-method ${req.method === k ? "on" : ""}`}
              onClick={() => setReq((r) => ({ ...r, method: k }))} title={desc}>{label}</button>
          ))}
        </div>
        <div className="u-thresholds">
          <label>Max hisse<input type="number" min={5} max={120} value={req.max_assets}
            onChange={(e) => setReq((r) => ({ ...r, max_assets: +e.target.value }))} /></label>
          <label>Poz. tavanı (%)<input type="number" step={1} value={req.max_weight * 100}
            onChange={(e) => setReq((r) => ({ ...r, max_weight: +e.target.value / 100 }))} /></label>
          <label>Sektör tavanı (%)<input type="number" step={1} value={req.sector_cap === null ? "" : req.sector_cap * 100}
            onChange={(e) => setReq((r) => ({ ...r, sector_cap: e.target.value === "" ? null : +e.target.value / 100 }))} /></label>
          <label>Risksiz faiz (%)<input type="number" step={1} value={req.rf_annual * 100}
            onChange={(e) => setReq((r) => ({ ...r, rf_annual: +e.target.value / 100 }))} /></label>
          <button className="a-primary u-apply" onClick={build} disabled={busy}>
            {busy ? "Kuruluyor…" : "Portföyü kur"}
          </button>
        </div>
      </div>

      {err && <div className="a-err">{err}</div>}
      {note && <div className={note.ok ? "pf-ok" : "a-err"}>{note.text}</div>}

      {data && m && (
        <>
          <div className="u-tiles">
            <div className="u-tile"><span>{pct(m.cagr)}</span>CAGR (in-sample)</div>
            <div className="u-tile"><span>{pct(m.geo_growth)}</span>geo. büyüme</div>
            <div className="u-tile"><span>{pct(m.ann_vol)}</span>yıllık vol</div>
            <div className="u-tile"><span>{num(m.sharpe)}</span>Sharpe ±{num(m.sharpe_se)}</div>
            <div className="u-tile"><span>{pct(m.max_drawdown)}</span>max düşüş</div>
            <div className="u-tile muted"><span>{data.n_assets} · {num(data.effective_n, 1)}</span>hisse · etkin</div>
          </div>

          {/* aksiyonlar — hepsi bu portföye bağlı */}
          <div className="pf-actions">
            <div className="pf-act">
              <button className="pf-btn" onClick={runBacktest} disabled={btBusy}>{btBusy ? "Backtest…" : "⇌ Backtest (OOS)"}</button>
              <span>train<input type="number" step={0.5} min={0.5} max={5} value={train} onChange={(e) => setTrain(+e.target.value)} />yıl</span>
              <span>test<input type="number" min={1} max={12} value={test} onChange={(e) => setTest(+e.target.value)} />ay</span>
            </div>
            <div className="pf-act">
              <button className="pf-btn" onClick={runProjection} disabled={pjBusy}>{pjBusy ? "Projeksiyon…" : "◉ Projeksiyon (MC)"}</button>
              <span>ufuk<input type="number" min={1} max={36} value={horizon} onChange={(e) => setHorizon(+e.target.value)} />ay</span>
            </div>
            <div className="pf-act pf-act-end">
              <button className="pf-btn" onClick={saveToKuantile}>↗ Kuantile'a kaydet</button>
              <button className="pf-btn pf-btn-accent" onClick={exportPDF}>⤓ PDF risk raporu</button>
            </div>
          </div>

          <div className="u-grid">
            <div className="u-card">
              <h3>Etkin sınır & portföy</h3>
              {data.frontier ? <Frontier data={data} /> : <p className="u-note">Bu yöntem için sınır çizilmez.</p>}
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

          {/* backtest sonucu */}
          {bt && (
            <div className="u-card">
              <h3>OOS backtest — portföy vs 1/N ({bt.start.slice(0, 7)} → {bt.end.slice(0, 7)})</h3>
              <div className="u-tiles">
                <div className="u-tile"><span>{pct(bt.metrics.cagr)}</span>OOS CAGR</div>
                <div className="u-tile"><span>{bt.real ? pct(bt.real.real_cagr) : "—"}</span>reel CAGR</div>
                <div className="u-tile"><span>{num(bt.metrics.sharpe)}</span>OOS Sharpe ±{num(bt.metrics.sharpe_se)}</div>
                <div className="u-tile"><span>{pct(bt.metrics.psr_vs_0, 0)}</span>PSR</div>
                <div className="u-tile"><span>{pct(bt.metrics.max_drawdown)}</span>max düşüş</div>
                <div className="u-tile muted"><span>{pct(bt.benchmark.cagr)} · {num(bt.benchmark.sharpe)}</span>1/N CAGR·Sharpe</div>
              </div>
              <BtCurve data={bt} />
              <p className="u-note">Ağırlıklar train'de üretilip sonraki {bt.test_days} günde test edildi ({bt.rebalances} rebalans). OOS &lt; in-sample olması normaldir.</p>
            </div>
          )}

          {/* projeksiyon sonucu */}
          {pj && (
            <div className="u-card">
              <h3>Monte Carlo projeksiyon — {pj.horizon_months} ay (bekl. getiri {pct(pj.exp_return_ann)}, vol {pct(pj.exp_vol_ann)})</h3>
              <ProjChart data={pj} hi={hi} onPick={setHi} />
              <div className="pj-legend">
                {pj.assets.map((a) => (
                  <button key={a.ticker} className={`pj-chip ${hi === a.ticker ? "on" : ""}`}
                    onClick={() => setHi(hi === a.ticker ? null : a.ticker)}
                    title={`%${(a.weight * 100).toFixed(1)} · 1₺→${a.path[a.path.length - 1].toFixed(2)}₺`}>
                    {a.ticker} <b>%{(a.weight * 100).toFixed(0)}</b>
                  </button>
                ))}
                {hi && <button className="pj-chip pj-clear" onClick={() => setHi(null)}>× temizle</button>}
              </div>
              <p className="u-note">İnce çizgiler varlıkların medyan yolları; bir çizgiye ya da alttaki koda tıkla → o hisse vurgulanır (üzerine gelince adı da çıkar). Kalın çizgi portföy medyanı, bant p5–p95. GBM/normal varsayımı — kuyruk riskini hafife alır.</p>
            </div>
          )}

          <div className="u-card">
            <h3>Ağırlıklar ({data.weights.length} pozisyon)</h3>
            <div className="u-table-scroll">
              <table className="u-table">
                <thead><tr><th>Kod</th><th>Sektör</th><th>Ağırlık</th><th>Risk katkısı</th></tr></thead>
                <tbody>
                  {data.weights.map((w) => (
                    <tr key={w.ticker}>
                      <td className="u-tk">{w.ticker}</td><td className="u-sec">{w.sector}</td>
                      <td>{pct(w.weight)}</td><td className="u-muted">{pct(w.risk_contrib)}</td>
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
          <p>Yöntem ve kısıtları seç, "Portföyü kur"a bas. Sonra aynı portföy üzerinde backtest, projeksiyon ve PDF risk raporu alabilirsin. Evren, Varlık Evreni varsayılan filtreleriyle (taban serisi dahil) süzülür.</p>
        </div>
      )}
    </div>
  );
}
