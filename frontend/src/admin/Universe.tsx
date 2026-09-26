import { useCallback, useEffect, useState } from "react";
import { api, ApiError, setToken, type UniverseRequest, type UniverseResponse } from "../api";

const DEFAULTS: UniverseRequest = {
  filters: { watchlist: true, neg_equity: true, persistent_loss: true, altman: true, liquidity: true, limit_down: true, drawdown: true },
  altman_min: 1.1,
  adv_min_tl: 5_000_000,
  loss_years_min: 3,
  limit_down_days_min: 2,
  drawdown_limit: 0.80,
  vol_min: null,
  vol_max: null,
  geo_min: null,
};

const REASON_LABELS: Record<string, string> = {
  watchlist: "Gözaltı/Yakın İzleme",
  neg_equity: "Negatif özkaynak",
  persistent_loss: "Sürekli zarar",
  altman: "Altman Z″ distress",
  liquidity: "Likidite altı",
  limit_down: "Taban serisi",
  drawdown: "Büyük drawdown",
  vol_band: "Vol bandı dışı",
  geo_min: "Geo getiri altı",
};

const FILTER_LABELS: [keyof UniverseRequest["filters"], string][] = [
  ["watchlist", "Gözaltı/Yakın İzleme Pazarı"],
  ["neg_equity", "Negatif özkaynak"],
  ["persistent_loss", "Sürekli zarar"],
  ["altman", "Altman Z″ distress"],
  ["liquidity", "Likidite eşiği"],
  ["limit_down", "Taban serisi (≤-%8)"],
  ["drawdown", "Büyük drawdown"],
];

const pct = (v: number | null, d = 1) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(d)}%`;
const milyonTL = (v: number | null) =>
  v === null || v === undefined ? "—" : `${(v / 1_000_000).toLocaleString("tr-TR", { maximumFractionDigits: 1 })} M₺`;

export function Universe({ onAuthFail }: { onAuthFail: () => void }) {
  const [req, setReq] = useState<UniverseRequest>(DEFAULTS);
  const [data, setData] = useState<UniverseResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = useCallback(async (body: UniverseRequest) => {
    setBusy(true);
    setErr(null);
    try {
      setData(await api.adminUniverse(body));
    } catch (ex) {
      if (ex instanceof ApiError && ex.status === 401) { setToken(null); onAuthFail(); return; }
      setErr(ex instanceof ApiError ? ex.message : "Sorgu başarısız.");
    } finally {
      setBusy(false);
    }
  }, [onAuthFail]);

  useEffect(() => { run(DEFAULTS); }, [run]);

  const setFilter = (k: keyof UniverseRequest["filters"]) =>
    setReq((r) => ({ ...r, filters: { ...r.filters, [k]: !r.filters[k] } }));

  const empty = !data || data.total === 0;

  return (
    <div className="u-wrap">
      {/* ---- kontrol paneli ---- */}
      <div className="u-controls">
        <div className="u-filters">
          {FILTER_LABELS.map(([k, label]) => (
            <label key={k} className={`u-chip ${req.filters[k] ? "on" : ""}`}>
              <input type="checkbox" checked={req.filters[k]} onChange={() => setFilter(k)} />
              {label}
            </label>
          ))}
        </div>
        <div className="u-thresholds">
          <label>Altman Z″ min
            <input type="number" step="0.1" value={req.altman_min}
              onChange={(e) => setReq((r) => ({ ...r, altman_min: +e.target.value }))} />
          </label>
          <label>Likidite min (M₺)
            <input type="number" step="1" value={req.adv_min_tl / 1_000_000}
              onChange={(e) => setReq((r) => ({ ...r, adv_min_tl: +e.target.value * 1_000_000 }))} />
          </label>
          <label>Zarar yılı ≥
            <input type="number" step="1" min="1" value={req.loss_years_min}
              onChange={(e) => setReq((r) => ({ ...r, loss_years_min: +e.target.value }))} />
          </label>
          <label>Taban günü ≥
            <input type="number" step="1" min="1" value={req.limit_down_days_min}
              onChange={(e) => setReq((r) => ({ ...r, limit_down_days_min: +e.target.value }))} />
          </label>
          <label>Max drawdown (%)
            <input type="number" step="5" min="10" value={Math.round(req.drawdown_limit * 100)}
              onChange={(e) => setReq((r) => ({ ...r, drawdown_limit: +e.target.value / 100 }))} />
          </label>
          <label>Vol min (%)
            <input type="number" step="1" value={req.vol_min === null ? "" : req.vol_min * 100}
              onChange={(e) => setReq((r) => ({ ...r, vol_min: e.target.value === "" ? null : +e.target.value / 100 }))} />
          </label>
          <label>Vol max (%)
            <input type="number" step="1" value={req.vol_max === null ? "" : req.vol_max * 100}
              onChange={(e) => setReq((r) => ({ ...r, vol_max: e.target.value === "" ? null : +e.target.value / 100 }))} />
          </label>
          <label>Geo getiri min (%)
            <input type="number" step="1" value={req.geo_min === null ? "" : req.geo_min * 100}
              onChange={(e) => setReq((r) => ({ ...r, geo_min: e.target.value === "" ? null : +e.target.value / 100 }))} />
          </label>
          <button className="a-primary u-apply" onClick={() => run(req)} disabled={busy}>
            {busy ? "Hesaplanıyor…" : "Uygula"}
          </button>
        </div>
      </div>

      {err && <div className="a-err">{err}</div>}

      {empty && !busy && (
        <div className="a-placeholder">
          <span className="a-ph-ic">▦</span>
          <h2>Henüz veri yok</h2>
          <p>Sunucuda <code>bist_cli.py all</code> ingest job'u çalışınca evren burada dolacak.</p>
        </div>
      )}

      {data && data.total > 0 && (
        <>
          {/* ---- özet ---- */}
          <div className="u-tiles">
            <div className="u-tile"><span>{data.eligible_count}</span>uygun hisse</div>
            <div className="u-tile"><span>{data.total}</span>toplam</div>
            <div className="u-tile"><span>{data.sectors.length}</span>sektör</div>
            <div className="u-tile muted"><span>{data.as_of ? data.as_of.slice(0, 10) : "—"}</span>güncelleme</div>
          </div>

          <div className="u-grid">
            {/* ---- eleme nedenleri ---- */}
            <div className="u-card">
              <h3>Eleme nedenleri</h3>
              <div className="u-reasons">
                {Object.entries(data.excluded_reasons)
                  .filter(([, n]) => n > 0)
                  .sort((a, b) => b[1] - a[1])
                  .map(([k, n]) => (
                    <div key={k} className="u-reason">
                      <span>{REASON_LABELS[k] ?? k}</span><b>{n}</b>
                    </div>
                  ))}
                {Object.values(data.excluded_reasons).every((n) => n === 0) && (
                  <p className="u-note">Aktif filtreyle elenen yok.</p>
                )}
              </div>
            </div>

            {/* ---- sektör dağılımı ---- */}
            <div className="u-card">
              <h3>Sektör dağılımı (uygun evren)</h3>
              <div className="u-sectors">
                {data.sectors.slice(0, 14).map((s) => (
                  <div key={s.sector} className="u-sector">
                    <div className="u-sector-top">
                      <span title={s.sector}>{s.sector}</span><b>{s.count}</b>
                    </div>
                    <div className="u-bar"><div style={{ width: `${s.share * 100}%` }} /></div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* ---- örnek liste ---- */}
          <div className="u-card">
            <h3>En likit uygun hisseler (ilk {data.sample.length})</h3>
            <div className="u-table-scroll">
              <table className="u-table">
                <thead>
                  <tr><th>Kod</th><th>Sektör</th><th>Yıl. Vol</th><th>Geo Getiri</th><th>Max DD</th><th>Altman Z″</th><th>Günlük Hacim</th><th>Gün</th></tr>
                </thead>
                <tbody>
                  {data.sample.map((r) => (
                    <tr key={r.ticker}>
                      <td className="u-tk">{r.ticker}</td>
                      <td className="u-sec">{r.sector ?? "—"}</td>
                      <td>{pct(r.ann_vol)}</td>
                      <td className={r.geo_return_ann != null && r.geo_return_ann < 0 ? "u-neg" : "u-pos"}>{pct(r.geo_return_ann)}</td>
                      <td className="u-neg">{pct(r.max_drawdown)}</td>
                      <td>{r.altman_z === null ? "—" : r.altman_z.toFixed(2)}</td>
                      <td>{milyonTL(r.adv_tl)}</td>
                      <td className="u-muted">{r.obs}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
