import { useState } from "react";
import { api, ApiError, setToken, type PortfolioMethod, type PortfolioRequest, type RiskResponse } from "../api";

const DEFAULT_UNIVERSE: PortfolioRequest["universe"] = {
  filters: { watchlist: true, neg_equity: true, persistent_loss: true, altman: true, liquidity: true, limit_down: true, drawdown: true },
  altman_min: 1.1, adv_min_tl: 5_000_000, loss_years_min: 3, limit_down_days_min: 2, drawdown_limit: 0.90,
  vol_min: null, vol_max: null, geo_min: null,
};
const BASE: PortfolioRequest = {
  universe: DEFAULT_UNIVERSE, method: "max_sharpe",
  max_assets: 50, max_weight: 0.10, sector_cap: 0.30, rf_annual: 0, window_years: 5,
};
const METHODS: [PortfolioMethod, string][] = [
  ["max_sharpe", "Max Sharpe"], ["min_variance", "Min Varyans"], ["risk_parity", "Risk Parity"],
  ["hrp", "HRP"], ["equal", "Eşit Ağırlık"], ["mc_max_return", "MC Max Getiri"],
];

const pct = (v: number | null | undefined, d = 1) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(d)}%`;
const num = (v: number | null | undefined, d = 2) =>
  v === null || v === undefined ? "—" : v.toFixed(d);
const tl = (v: number) => `${Math.round(v).toLocaleString("tr-TR")} ₺`;

export function Risk({ onAuthFail }: { onAuthFail: () => void }) {
  const [req, setReq] = useState<PortfolioRequest>(BASE);
  const [data, setData] = useState<RiskResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setBusy(true); setErr(null);
    try { setData(await api.adminRisk(req)); }
    catch (ex) {
      if (ex instanceof ApiError && ex.status === 401) { setToken(null); onAuthFail(); return; }
      setErr(ex instanceof ApiError ? ex.message : "Risk analizi başarısız.");
    } finally { setBusy(false); }
  }

  const f = data?.factor;

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
          <label>Max hisse<input type="number" min={5} max={120} value={req.max_assets}
            onChange={(e) => setReq((r) => ({ ...r, max_assets: +e.target.value }))} /></label>
          <label>Poz. tavanı (%)<input type="number" step={1} value={req.max_weight * 100}
            onChange={(e) => setReq((r) => ({ ...r, max_weight: +e.target.value / 100 }))} /></label>
          <label>Sektör tavanı (%)<input type="number" step={1} value={req.sector_cap === null ? "" : req.sector_cap * 100}
            onChange={(e) => setReq((r) => ({ ...r, sector_cap: e.target.value === "" ? null : +e.target.value / 100 }))} /></label>
          <button className="a-primary u-apply" onClick={run} disabled={busy}>
            {busy ? "Analiz…" : "Risk analizi"}
          </button>
        </div>
      </div>

      {err && <div className="a-err">{err}</div>}

      {data && (
        <>
          <div className="u-tiles">
            <div className="u-tile"><span>{pct(data.var_pct.var99)}</span>1g VaR %99</div>
            <div className="u-tile"><span>{pct(data.var_pct.cvar99)}</span>CVaR %99 (kuyruk)</div>
            <div className="u-tile"><span>{pct(data.var_pct.var99_cf)}</span>VaR %99 (Cornish-Fisher)</div>
            <div className="u-tile"><span>{pct(data.concentration.port_vol_ann)}</span>yıllık vol</div>
            <div className="u-tile"><span>{num(data.concentration.effective_n, 1)}</span>etkin N (HHI {num(data.concentration.hhi, 2)})</div>
            <div className="u-tile muted"><span>{num(data.concentration.diversification_ratio)}</span>çeşitlendirme oranı</div>
          </div>

          <div className="u-card">
            <h3>1M ₺ portföyde kayıp (tarihsel, 1 gün)</h3>
            <div className="u-tiles">
              <div className="u-tile"><span>{tl(data.var_tl.var95)}</span>VaR %95</div>
              <div className="u-tile"><span>{tl(data.var_tl.var99)}</span>VaR %99</div>
              <div className="u-tile"><span>{tl(data.var_tl.cvar99)}</span>CVaR %99</div>
              <div className="u-tile muted"><span>{pct(data.var_pct.worst_day)}</span>en kötü gün</div>
            </div>
          </div>

          <div className="u-grid">
            <div className="u-card">
              <h3>Bileşen risk — hisse (VaR %99 payı)</h3>
              <div className="u-table-scroll">
                <table className="u-table">
                  <thead><tr><th>Kod</th><th>Ağırlık</th><th>Risk payı</th><th>Bileşen VaR</th></tr></thead>
                  <tbody>
                    {data.components.slice(0, 15).map((c) => (
                      <tr key={c.ticker}>
                        <td className="u-tk">{c.ticker}</td>
                        <td>{pct(c.weight)}</td>
                        <td><b>{pct(c.risk_share)}</b></td>
                        <td className="u-muted">{tl(c.comp_var99_tl)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="u-note">Risk payı = Euler ayrıştırması (ağırlık × marjinal risk); toplamı %100. Ağırlığından yüksek risk payı = o hisse riski domine ediyor.</p>
            </div>

            <div className="u-card">
              <h3>Sektör risk payı</h3>
              <div className="u-sectors">
                {data.sector_risk.slice(0, 12).map((s) => (
                  <div key={s.sector} className="u-sector">
                    <div className="u-sector-top"><span title={s.sector}>{s.sector}</span><b>{pct(s.risk_share)}</b></div>
                    <div className="u-bar"><div style={{ width: `${s.risk_share * 100}%` }} /></div>
                  </div>
                ))}
              </div>
              <h3 style={{ marginTop: 18 }}>Faktör maruziyeti</h3>
              <div className="u-tiles">
                <div className="u-tile"><span>{pct(f?.systematic_share)}</span>sistematik pay (PC1)</div>
                <div className="u-tile"><span>{pct(f?.pc1_explained)}</span>PC1 evren varyansı</div>
                <div className="u-tile"><span>{num(f?.gold_beta)}</span>altın betası</div>
                <div className="u-tile muted"><span>{num(data.tail.skew)} / {num(data.tail.excess_kurtosis)}</span>çarpıklık / basıklık</div>
              </div>
              <p className="u-note">Sistematik pay yüksekse portföy tek ortak faktöre (piyasa) bağlı; düşükse çeşitlenmiş. Yüksek fazla-basıklık = şişman kuyruk (VaR gerçeği hafife alır).</p>
            </div>
          </div>
        </>
      )}

      {!data && !busy && !err && (
        <div className="a-placeholder">
          <span className="a-ph-ic">△</span>
          <h2>Risk ayrıştırma</h2>
          <p>Yöntem + kısıtları seç, "Risk analizi"ne bas. Portföyün bileşen VaR/CVaR'ı (hisse & sektör), yoğunlaşması ve faktör (sistematik/altın) maruziyeti çıkar.</p>
        </div>
      )}
    </div>
  );
}
