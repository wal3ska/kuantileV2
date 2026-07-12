import type { AnalyzeResponse, ValuationRow } from "./api";
import { fmtNum, fmtPct, fmtTL } from "./api";
import { CorrHeatmap, HBars } from "./charts";

function Delta({ v, children }: { v: number | null; children?: React.ReactNode }) {
  if (v === null) return <span className="dim">—</span>;
  return <span className={v >= 0 ? "up" : "down"}>{children}</span>;
}

function ValuationTable({ rows }: { rows: ValuationRow[] }) {
  const hasBond = rows.some((r) => r.type === "bond");
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead>
          <tr>
            <th>Varlık</th>
            <th>Son Fiyat</th>
            {hasBond && <th>Makul Fiyat</th>}
            <th>Değer (TL)</th>
            <th>K/Z (TL)</th>
            <th>K/Z %</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name + r.type}>
              <td className="name">
                {r.name} <span className="dim">{r.type === "bond" ? "tahvil" : r.currency}</span>
              </td>
              <td>{r.last_price !== undefined ? fmtNum(r.last_price) : "—"}</td>
              {hasBond && (
                <td className="dim">{r.fair_price !== undefined ? fmtNum(r.fair_price) : "—"}</td>
              )}
              <td>{fmtTL(r.value_try)}</td>
              <td><Delta v={r.pnl_try}>{r.pnl_try !== null ? fmtTL(r.pnl_try) : ""}</Delta></td>
              <td><Delta v={r.pnl_pct}>{r.pnl_pct !== null ? fmtPct(r.pnl_pct / 100) : ""}</Delta></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Dashboard({ data }: { data: AnalyzeResponse }) {
  const risk = data.market_risk;
  const bond = data.bond_risk;

  const alloc = [...data.valuation]
    .sort((a, b) => b.value_try - a.value_try)
    .map((v) => ({
      label: v.name,
      value: v.value_try,
      tip: (
        <>
          <div className="t">{v.name}</div>
          {fmtTL(v.value_try)} · portföyün {fmtPct(v.value_try / data.total_value_try, 1).replace("+", "")}
        </>
      ),
    }));

  const pnl = data.valuation
    .filter((v) => v.pnl_try !== null)
    .sort((a, b) => (b.pnl_try ?? 0) - (a.pnl_try ?? 0))
    .map((v) => ({
      label: v.name,
      value: v.pnl_try as number,
      tip: (
        <>
          <div className="t">{v.name}</div>
          {fmtTL(v.pnl_try as number)} ({v.pnl_pct !== null ? fmtPct(v.pnl_pct / 100) : "—"})
        </>
      ),
    }));

  const stress = risk
    ? Object.entries(risk.stress_tests)
        .filter(([, s]) => s.impact_try !== null)
        .sort(([, a], [, b]) => (a.impact_try ?? 0) - (b.impact_try ?? 0))
        .map(([name, s]) => ({
          label: name,
          value: s.impact_try as number,
          tip: (
            <>
              <div className="t">{name} ({s.start} → {s.end})</div>
              getiri: {fmtPct(s.cumulative_return ?? 0)} · etki: {fmtTL(s.impact_try as number)}
              {s.missing_assets.length > 0 && (
                <div className="t" style={{ marginTop: 4 }}>kapsam dışı: {s.missing_assets.join(", ")}</div>
              )}
            </>
          ),
        }))
    : [];

  const totalPnl = data.valuation.reduce<number | null>(
    (acc, v) => (v.pnl_try === null ? acc : (acc ?? 0) + v.pnl_try), null);

  return (
    <div className="stack">
      {data.failed_assets.length > 0 && (
        <div className="msg err">Veri bulunamadı: {data.failed_assets.join(", ")} — bu varlıklar analize dahil edilmedi.</div>
      )}

      <div className="tiles">
        <div className="tile">
          <div className="k">Toplam Portföy Değeri</div>
          <div className="v hero">{fmtTL(data.total_value_try)}</div>
          {totalPnl !== null && (
            <div className="sub"><Delta v={totalPnl}>{fmtTL(totalPnl)} toplam K/Z</Delta></div>
          )}
        </div>
        <div className="tile">
          <div className="k">USD / TRY</div>
          <div className="v">{fmtNum(data.fx_usdtry)}</div>
          <div className="sub">güncel kur</div>
        </div>
        {risk && (
          <div className="tile">
            <div className="k">VaR — %{(risk.confidence * 100).toFixed(0)} güven, 1 gün</div>
            <div className="v down">{fmtTL(risk.var_value_try)}</div>
            <div className="sub">{fmtPct(risk.var_pct)} · {risk.observations.toLocaleString("tr-TR")} gözlem</div>
          </div>
        )}
        {risk && (
          <div className="tile">
            <div className="k">Çeşitlendirme Faydası</div>
            <div className="v up">{fmtTL(risk.diversification.benefit)}</div>
            <div className="sub">tekil VaR toplamına kıyasla azalan risk</div>
          </div>
        )}
        {bond && (
          <div className="tile">
            <div className="k">Tahvil Sepeti — DV01</div>
            <div className="v">{fmtTL(bond.total_dv01)}</div>
            <div className="sub">durasyon {fmtNum(bond.weighted_modified_duration)} yıl</div>
          </div>
        )}
      </div>

      <div className="card">
        <h3>Değerleme</h3>
        <ValuationTable rows={data.valuation} />
      </div>

      <div className="grid2">
        <div className="card">
          <h3>Dağılım (TL değer)</h3>
          <HBars items={alloc} format={fmtTL} />
        </div>
        {pnl.length > 0 && (
          <div className="card">
            <h3>Kâr / Zarar</h3>
            <HBars items={pnl} format={fmtTL} diverging />
          </div>
        )}
      </div>

      {risk && Object.keys(risk.correlation).length >= 2 && (
        <div className="card">
          <h3>Korelasyon Matrisi</h3>
          <CorrHeatmap matrix={risk.correlation} />
          <p className="section-note">
            Düşük veya negatif korelasyon çeşitlendirme demektir: varlıklar aynı anda aynı yöne düşmez.
          </p>
        </div>
      )}

      {stress.length > 0 && (
        <div className="card">
          <h3>Tarihsel Stres Testleri</h3>
          <HBars items={stress} format={fmtTL} diverging />
          <p className="section-note">
            Mevcut ağırlıklarınız geçmiş kriz pencerelerinde yaşansaydı portföyün TL etkisi. Kapsam dışı varlıklar için imleci barın üzerine getirin.
          </p>
        </div>
      )}

      {bond && (
        <div className="card">
          <h3>Faiz Şoku Senaryoları (tahvil sepeti)</h3>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr><th>Şok</th><th>Etki (TL)</th></tr>
              </thead>
              <tbody>
                {Object.entries(bond.rate_shocks).map(([bps, v]) => (
                  <tr key={bps}>
                    <td className="name">{+bps > 0 ? "+" : ""}{bps} baz puan</td>
                    <td><Delta v={v}>{fmtTL(v)}</Delta></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="section-note">
            DV01: faizde 1 baz puanlık artışın sepette yarattığı yaklaşık TL kaybı. Şoklar basitleştirilmiş durasyon yaklaşımıdır.
          </p>
        </div>
      )}

      <p className="footer-note">{data.disclaimer} Fiyat kaynağı: Yahoo Finance, TEFAS.</p>
    </div>
  );
}
