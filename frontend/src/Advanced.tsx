import type { AdvancedBlock } from "./api";
import { fmtNum, fmtPct, fmtTL } from "./api";
import { HBars } from "./charts";
import { useT } from "./i18n";

/* Gelismis risk bolumu: her kart kisa bir ozet verir, uzun anlatim rehberde. */

function GuideLink({ slug }: { slug: string }) {
  const { t, lang } = useT();
  const href = lang === "en" ? `/en/guides/${slug.split("|")[1]}/` : `/rehber/${slug.split("|")[0]}/`;
  return <a className="guide-link" href={href} target="_blank" rel="noreferrer">{t("advGuide")}</a>;
}

const MODELS = "gelismis-risk-metrikleri|advanced-risk-metrics";
const ATTRIB = "risk-atfi-yogunlasma|risk-attribution-concentration";
const REALFX = "reel-getiri-kur-likidite|real-return-fx-liquidity";

export function AdvancedSection({ adv, varPct }: {
  adv: AdvancedBlock; varPct: number;
}) {
  const { t } = useT();
  const zoneCls = { green: "up", yellow: "dim", red: "down" } as const;

  const hasAny = Object.values(adv).some((v) => v !== null && v !== undefined);
  if (!hasAny) return null;

  return (
    <>
      <h2 className="adv-heading">{t("advTitle")}</h2>

      <div className="grid2">
        {/* Model karsilastirma + backtest */}
        {(adv.es || adv.ewma || adv.evt || adv.backtest) && (
          <div className="card">
            <h3>{t("advModels")}</h3>
            <div className="tbl-wrap"><table className="tbl">
              <thead><tr><th>{t("advModelCol")}</th><th>{t("advLossCol")}</th></tr></thead>
              <tbody>
                <tr><td className="name">{t("advHistVar")}</td><td className="down">{fmtPct(varPct)}</td></tr>
                {adv.es?.es_pct != null && (
                  <tr><td className="name">{t("advEs")}</td><td className="down">{fmtPct(adv.es.es_pct)}</td></tr>
                )}
                {adv.es?.es975_pct != null && (
                  <tr><td className="name">{t("advEs975")}</td><td className="down">{fmtPct(adv.es.es975_pct)}</td></tr>
                )}
                {adv.ewma && (
                  <>
                    <tr><td className="name">{t("advEwmaVar")}</td><td className="down">{fmtPct(adv.ewma.var_ewma_pct)}</td></tr>
                    <tr><td className="name">{t("advFhsVar")}</td><td className="down">{fmtPct(adv.ewma.var_fhs_pct)}</td></tr>
                  </>
                )}
                {adv.evt && (
                  <>
                    <tr><td className="name">{t("advEvtVar")}</td><td className="down">{fmtPct(adv.evt.var995_pct)}</td></tr>
                    <tr><td className="name">{t("advEvtEs")}</td><td className="down">{fmtPct(adv.evt.es995_pct)}</td></tr>
                  </>
                )}
              </tbody>
            </table></div>
            {adv.ewma && (
              <p className="section-note">{t("advEwmaNote", { v: fmtPct(adv.ewma.ewma_vol_ann).replace("+", "") })}</p>
            )}
            {adv.evt && (
              <p className="section-note">{t("advEvtNote", { xi: fmtNum(adv.evt.tail_index), n: String(adv.evt.exceedances) })}</p>
            )}
            {adv.backtest && (
              <p className="section-note">
                <b className={zoneCls[adv.backtest.basel_zone]}>{t(`advZone_${adv.backtest.basel_zone}`)}</b>
                {" — "}
                {t("advBacktestNote", {
                  x: String(adv.backtest.violations),
                  e: String(adv.backtest.expected),
                  n: String(adv.backtest.days),
                  k: (adv.backtest.kupiec_p * 100).toFixed(0),
                })}
                {adv.backtest.christoffersen_p != null &&
                  ` ${t("advChristNote", { c: (adv.backtest.christoffersen_p * 100).toFixed(0) })}`}
              </p>
            )}
            <GuideLink slug={MODELS} />
          </div>
        )}

        {/* Risk atfi */}
        {adv.attribution && (
          <div className="card">
            <h3>{t("advAttrib")}</h3>
            <div className="tbl-wrap"><table className="tbl">
              <thead><tr>
                <th>{t("colAsset")}</th><th>{t("advWeightCol")}</th>
                <th>{t("advRiskShareCol")}</th><th>{t("advIncCol")}</th>
              </tr></thead>
              <tbody>
                {adv.attribution.components.map((c) => (
                  <tr key={c.name}>
                    <td className="name">{c.name}</td>
                    <td>{fmtPct(c.weight).replace("+", "")}</td>
                    <td className={c.cvar_share != null && c.cvar_share > c.weight ? "down" : ""}>
                      {c.cvar_share != null ? fmtPct(c.cvar_share).replace("+", "") : "—"}
                    </td>
                    <td>{c.incremental_tl != null ? fmtTL(c.incremental_tl) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
            <p className="section-note">{t("advAttribNote")}</p>
            <GuideLink slug={ATTRIB} />
          </div>
        )}
      </div>

      <div className="grid2">
        {/* Reel getiri */}
        {adv.real && (
          <div className="card">
            <h3>{t("advReal")}</h3>
            <div className="kv-list">
              <div><span>{t("advInfl")}</span><b>{fmtPct(adv.real.inflation_12m).replace("+", "")}</b></div>
              <div><span>{t("advNom12")}</span><b className={adv.real.nominal_return_12m >= 0 ? "up" : "down"}>{fmtPct(adv.real.nominal_return_12m)}</b></div>
              <div><span>{t("advReal12")}</span><b className={adv.real.real_return_12m >= 0 ? "up" : "down"}>{fmtPct(adv.real.real_return_12m)}</b></div>
              {adv.real.prob_real_loss_12m != null && (
                <div><span>{t("advRealLossProb")}</span><b>{fmtPct(adv.real.prob_real_loss_12m).replace("+", "")}</b></div>
              )}
            </div>
            <p className="section-note">{t("advRealNote", { d: adv.real.cpi_as_of })}</p>
            <GuideLink slug={REALFX} />
          </div>
        )}

        {/* Kur ayristirmasi */}
        {adv.fx && (
          <div className="card">
            <h3>{t("advFx")}</h3>
            <div className="kv-list">
              <div><span>{t("advFxExposure")}</span><b>{fmtPct(adv.fx.usd_exposure_share).replace("+", "")}</b></div>
              <div><span>{t("advFxLocal")}</span><b>{fmtPct(adv.fx.local_share).replace("+", "")}</b></div>
              <div><span>{t("advFxCur")}</span><b>{fmtPct(adv.fx.fx_share).replace("+", "")}</b></div>
              <div><span>{t("advFxCov")}</span><b>{fmtPct(adv.fx.cov_share)}</b></div>
            </div>
            <p className="section-note">{t("advFxNote")}</p>
            <GuideLink slug={REALFX} />
          </div>
        )}
      </div>

      <div className="grid2">
        {/* Drawdown */}
        {adv.drawdown && (
          <div className="card">
            <h3>{t("advDd")}</h3>
            <div className="kv-list">
              <div><span>{t("advMaxDd")}</span><b className="down">{fmtPct(adv.drawdown.max_drawdown)}</b></div>
              {adv.drawdown.calmar != null && (
                <div><span>Calmar</span><b>{fmtNum(adv.drawdown.calmar)}</b></div>
              )}
              <div><span>{t("advUlcer")}</span><b>{fmtNum(adv.drawdown.ulcer_index * 100)}</b></div>
              <div><span>{t("advUnderwater")}</span><b>{adv.drawdown.underwater_days_now} / {adv.drawdown.longest_underwater_days} {t("advDays")}</b></div>
            </div>
            <p className="section-note">{t("advDdNote")}</p>
            <GuideLink slug={MODELS} />
          </div>
        )}

        {/* Yogunlasma */}
        {adv.concentration && (
          <div className="card">
            <h3>{t("advConc")}</h3>
            <div className="kv-list">
              <div><span>{t("advEffPos")}</span><b>{fmtNum(adv.concentration.effective_positions)} / {adv.concentration.n_assets}</b></div>
              <div><span>{t("advEffBets")}</span><b>{fmtNum(adv.concentration.effective_bets)}</b></div>
              <div><span>{t("advDivRatio")}</span><b>{fmtNum(adv.concentration.diversification_ratio)}</b></div>
              <div><span>HHI</span><b>{fmtNum(adv.concentration.hhi)}</b></div>
            </div>
            <p className="section-note">{t("advConcNote", { n: fmtNum(adv.concentration.effective_bets) })}</p>
            <GuideLink slug={ATTRIB} />
          </div>
        )}
      </div>

      <div className="grid2">
        {/* Likidite */}
        {adv.liquidity && (
          <div className="card">
            <h3>{t("advLiq")}</h3>
            <div className="tbl-wrap"><table className="tbl">
              <thead><tr><th>{t("colAsset")}</th><th>{t("advExitDays")}</th></tr></thead>
              <tbody>
                {adv.liquidity.positions.map((p) => (
                  <tr key={p.name}>
                    <td className="name">{p.name}</td>
                    <td className={p.days_to_exit > 5 ? "down" : ""}>{fmtNum(p.days_to_exit)}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
            <p className="section-note">
              {t("advLiqNote", { v: fmtTL(adv.liquidity.lvar_value_tl), m: fmtNum(adv.liquidity.lvar_multiplier) })}
            </p>
            <GuideLink slug={REALFX} />
          </div>
        )}

        {/* Kuyruk bagimliligi */}
        {adv.tail_dependence && adv.tail_dependence.pairs.length > 0 && (
          <div className="card">
            <h3>{t("advTailDep")}</h3>
            <div className="tbl-wrap"><table className="tbl">
              <thead><tr><th>{t("advPairCol")}</th><th>λ</th><th>ρ</th></tr></thead>
              <tbody>
                {adv.tail_dependence.pairs.map((p) => (
                  <tr key={p.pair}>
                    <td className="name">{p.pair}</td>
                    <td className={p.lambda_lower > 0.4 ? "down" : ""}>{fmtNum(p.lambda_lower)}</td>
                    <td className="dim">{fmtNum(p.pearson)}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
            <p className="section-note">{t("advTailDepNote")}</p>
            <GuideLink slug={ATTRIB} />
          </div>
        )}
      </div>

      {/* HRP */}
      {adv.hrp && (
        <div className="card">
          <h3>{t("advHrp")}</h3>
          <HBars
            items={Object.entries(adv.hrp.weights)
              .sort((a, b) => b[1] - a[1])
              .map(([name, w]) => ({ label: name, value: w }))}
            format={(v) => fmtPct(v).replace("+", "")}
          />
          <p className="section-note">{t("advHrpNote")}</p>
          <GuideLink slug={ATTRIB} />
        </div>
      )}

      {/* Stil analizi */}
      {adv.style && Object.entries(adv.style).some(([, s]) => s) && (
        <div className="card">
          <h3>{t("advStyle")}</h3>
          {Object.entries(adv.style).map(([fund, s]) => s && (
            <div key={fund} className="style-block">
              <h4>{fund}</h4>
              <HBars
                items={Object.entries(s.weights)
                  .filter(([, w]) => w > 0.01)
                  .sort((a, b) => b[1] - a[1])
                  .map(([name, w]) => ({ label: name, value: w }))}
                format={(v) => fmtPct(v).replace("+", "")}
              />
              <p className="section-note">
                {t("advStyleNote", {
                  r2: s.r2 != null ? fmtPct(s.r2).replace("+", "") : "—",
                  te: fmtPct(s.tracking_error_ann).replace("+", ""),
                  ir: s.information_ratio != null ? fmtNum(s.information_ratio) : "—",
                })}
              </p>
            </div>
          ))}
          <p className="section-note">{t("advStyleFoot")}</p>
          <GuideLink slug={REALFX} />
        </div>
      )}
    </>
  );
}
