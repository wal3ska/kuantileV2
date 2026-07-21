import { useState } from "react";
import type { AnalyzeResponse, PositionIn, SimulateResponse, ValuationRow } from "./api";
import { api, ApiError, fmtNum, fmtPct, fmtTL } from "./api";
import { CorrHeatmap, HBars, LineChart } from "./charts";
import { useT } from "./i18n";

function Delta({ v, children }: { v: number | null; children?: React.ReactNode }) {
  if (v === null) return <span className="dim">—</span>;
  return <span className={v >= 0 ? "up" : "down"}>{children}</span>;
}

function ValuationTable({ rows }: { rows: ValuationRow[] }) {
  const { t } = useT();
  const hasBond = rows.some((r) => r.type === "bond");
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead>
          <tr>
            <th>{t("colAsset")}</th>
            <th>{t("colLast")}</th>
            {hasBond && <th>{t("colFair")}</th>}
            <th>{t("colValue")}</th>
            <th>{t("colPnl")}</th>
            <th>{t("colPnlPct")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name + r.type}>
              <td className="name">
                {r.name} <span className="dim">{r.type === "bond" ? t("bondTag") : r.currency}</span>
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

function CustomSim({ positions }: { positions: PositionIn[] }) {
  const { t } = useT();
  const today = new Date().toISOString().slice(0, 10);
  const [start, setStart] = useState("2022-01-01");
  const [end, setEnd] = useState(today);
  const [busy, setBusy] = useState(false);
  const [sim, setSim] = useState<SimulateResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  if (positions.length === 0) return null;

  async function run() {
    if (!start || !end || start >= end) {
      setErr(t("simBadRange"));
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      setSim(await api.simulate(positions, start, end));
    } catch (e) {
      setSim(null);
      setErr(e instanceof ApiError ? e.message : t("analyzeFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h3>{t("customSim")}</h3>
      <p className="section-note" style={{ margin: "0 0 10px" }}>{t("simDesc")}</p>
      <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
        <label className="f" style={{ flex: "0 0 160px" }}>{t("startDate")}
          <input type="date" value={start} max={end} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label className="f" style={{ flex: "0 0 160px" }}>{t("endDate")}
          <input type="date" value={end} min={start} max={today} onChange={(e) => setEnd(e.target.value)} />
        </label>
        <button className="primary" onClick={run} disabled={busy}>
          {busy ? (<><span className="spin" />{t("simulating")}</>) : t("simulateBtn")}
        </button>
      </div>
      {err && <div className="msg err" style={{ marginTop: 10 }}>{err}</div>}
      {sim && (
        <div style={{ marginTop: 14 }}>
          <p style={{ margin: "0 0 10px" }}>
            <Delta v={sim.cumulative_return}>
              {t("simSummary", {
                p: fmtPct(sim.cumulative_return),
                v1: fmtTL(sim.base_value_try),
                v2: fmtTL(sim.final_value_try),
              })}
            </Delta>
          </p>
          <LineChart points={sim.series} format={fmtTL} />
          {sim.missing_assets.length > 0 && (
            <p className="section-note">{t("simMissing", { list: sim.missing_assets.join(", ") })}</p>
          )}
        </div>
      )}
    </div>
  );
}

export function Dashboard({ data, positions }: { data: AnalyzeResponse; positions: PositionIn[] }) {
  const { t } = useT();
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
          {fmtTL(v.value_try)} · {t("ofPortfolio", { p: fmtPct(v.value_try / data.total_value_try, 1).replace("+", "") })}
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
              {t("ret")}: {fmtPct(s.cumulative_return ?? 0)} · {t("impact")}: {fmtTL(s.impact_try as number)}
              {s.missing_assets.length > 0 && (
                <div className="t" style={{ marginTop: 4 }}>{t("notCovered")}: {s.missing_assets.join(", ")}</div>
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
        <div className="msg err">{t("failedAssets", { list: data.failed_assets.join(", ") })}</div>
      )}

      <div className="tiles">
        <div className="tile">
          <div className="k">{t("totalValue")}</div>
          <div className="v hero">{fmtTL(data.total_value_try)}</div>
          {totalPnl !== null && (
            <div className="sub"><Delta v={totalPnl}>{fmtTL(totalPnl)} {t("totalPnl")}</Delta></div>
          )}
        </div>
        <div className="tile">
          <div className="k">USD / TRY</div>
          <div className="v">{fmtNum(data.fx_usdtry)}</div>
          <div className="sub">{t("fxSub")}</div>
        </div>
        {risk && (
          <div className="tile">
            <div className="k">{t("varTile", { c: (risk.confidence * 100).toFixed(0) })}</div>
            <div className="v down">{fmtTL(risk.var_value_try)}</div>
            <div className="sub">{fmtPct(risk.var_pct)} · {risk.observations.toLocaleString()} {t("observations")}</div>
          </div>
        )}
        {risk?.sharpe?.["1y"] && (
          <div className="tile">
            <div className="k">{t("sharpeTile")}</div>
            <div className="v"><Delta v={risk.sharpe["1y"].sharpe}>{fmtNum(risk.sharpe["1y"].sharpe)}</Delta></div>
            <div className="sub">{t("sharpeHorizons", {
              a: risk.sharpe["3y"] ? fmtNum(risk.sharpe["3y"].sharpe) : "—",
              b: risk.sharpe["5y"] ? fmtNum(risk.sharpe["5y"].sharpe) : "—",
            })}</div>
            <div className="sub">{t("sharpeSub", {
              r: fmtPct(risk.sharpe["1y"].ann_return),
              v: fmtPct(risk.sharpe["1y"].ann_vol).replace("+", ""),
              rf: fmtPct(risk.sharpe["1y"].ann_rf),
            })}</div>
          </div>
        )}
        {risk && (
          <div className="tile">
            <div className="k">{t("divTile")}</div>
            <div className="v up">{fmtTL(risk.diversification.benefit)}</div>
            <div className="sub">{t("divSub")}</div>
          </div>
        )}
        {bond && (
          <div className="tile">
            <div className="k">{t("dv01Tile")}</div>
            <div className="v">{fmtTL(bond.total_dv01)}</div>
            <div className="sub">{t("durationSub", { n: fmtNum(bond.weighted_modified_duration) })}</div>
          </div>
        )}
      </div>

      <div className="card">
        <h3>{t("valuation")}</h3>
        <ValuationTable rows={data.valuation} />
      </div>

      <div className="grid2">
        <div className="card">
          <h3>{t("alloc")}</h3>
          <HBars items={alloc} format={fmtTL} />
        </div>
        {pnl.length > 0 && (
          <div className="card">
            <h3>{t("pnlCard")}</h3>
            <HBars items={pnl} format={fmtTL} diverging />
          </div>
        )}
      </div>

      {risk && Object.keys(risk.correlation).length >= 2 && (
        <div className="card">
          <h3>{t("corr")}</h3>
          <div className="heat-scroll"><CorrHeatmap matrix={risk.correlation} /></div>
          <p className="section-note">{t("corrNote")}</p>
        </div>
      )}

      {stress.length > 0 && (
        <div className="card">
          <h3>{t("stress")}</h3>
          <HBars items={stress} format={fmtTL} diverging />
          <p className="section-note">{t("stressNote")}</p>
        </div>
      )}

      <CustomSim positions={positions} />

      {bond && (
        <div className="card">
          <h3>{t("shocks")}</h3>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr><th>{t("shock")}</th><th>{t("impactTL")}</th></tr>
              </thead>
              <tbody>
                {Object.entries(bond.rate_shocks).map(([bps, v]) => (
                  <tr key={bps}>
                    <td className="name">{+bps > 0 ? "+" : ""}{bps} {t("bp")}</td>
                    <td><Delta v={v}>{fmtTL(v)}</Delta></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="section-note">{t("shockNote")}</p>
        </div>
      )}

      <p className="footer-note">{t("disclaimer")}</p>
    </div>
  );
}
