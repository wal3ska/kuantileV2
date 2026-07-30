import type { AdvancedBlock } from "./api";
import { fmtNum, fmtPct, fmtTL } from "./api";
import { HBars } from "./charts";
import { useT } from "./i18n";

/* Gelismis risk bolumu: her kart kisa bir ozet verir, uzun anlatim rehberde. */

function Delta({ v, children }: { v: number; children?: React.ReactNode }) {
  return <span className={v >= 0 ? "up" : "down"}>{children}</span>;
}

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
  const tk = t as unknown as (key: string) => string;  // dinamik anahtarlar icin
  const zoneCls = { green: "up", yellow: "dim", red: "down" } as const;

  const hasAny = Object.values(adv).some((v) => v !== null && v !== undefined);
  if (!hasAny) return null;

  return (
    <>
      <h2 className="adv-heading" id="advanced">{t("advTitle")}</h2>

      {adv.vol_regime && (
        <p className={`vol-regime-banner ${adv.vol_regime.percentile < 0.35 ? "calm" : adv.vol_regime.percentile > 0.7 ? "hot" : ""}`}>
          {t("advVolRegime", {
            p: (adv.vol_regime.percentile * 100).toFixed(0),
            v: fmtPct(adv.vol_regime.current_vol_ann).replace("+", ""),
          })}
        </p>
      )}

      {(adv.score || adv.risk_class) && (
        <div className="card score-card">
          <div className="score-row">
            {adv.score && (
              <div className="score-main">
                <div className="k">{t("advScore")}</div>
                <div className={`score-big ${adv.score.score >= 70 ? "up" : adv.score.score < 40 ? "down" : ""}`}>
                  {fmtNum(adv.score.score)}<span className="score-of">/100</span>
                </div>
              </div>
            )}
            {adv.risk_class && (
              <div className="score-main">
                <div className="k">{t("advRiskClass")}</div>
                <div className="riskseg" aria-label={`${adv.risk_class.risk_class}/7`}>
                  {[1, 2, 3, 4, 5, 6, 7].map((i) => (
                    <span key={i}
                      className={`seg${i <= adv.risk_class!.risk_class ? ` on r${adv.risk_class!.risk_class}` : ""}`}>
                      {i}
                    </span>
                  ))}
                </div>
                <div className="sub">{t("advRiskClassSub", {
                  v: fmtPct(adv.risk_class.ann_vol_weekly).replace("+", ""),
                  n: String(adv.risk_class.weeks),
                })}</div>
              </div>
            )}
          </div>
          {adv.score && (
            <div className="score-comps">
              {Object.entries(adv.score.components).map(([k, v]) => (
                <div key={k} className="score-comp">
                  <span>{tk(`advC_${k}`)}</span>
                  <div className="score-bar"><i style={{ width: `${v}%` }} /></div>
                  <b>{fmtNum(v)}</b>
                </div>
              ))}
            </div>
          )}
          <p className="section-note">{t("advScoreNote")}</p>
        </div>
      )}

      {(adv.sharpe_ci || adv.beat_deposit) && (
        <div className="grid2">
          {adv.sharpe_ci && (
            <div className="card">
              <h3>{t("advUncertainty")}</h3>
              <div className="kv-list">
                <div><span>{t("advSharpePoint")}</span><b>{fmtNum(adv.sharpe_ci.sharpe_ann)}</b></div>
                <div><span>{t("advSharpeCI")}</span><b>{fmtNum(adv.sharpe_ci.ci_low)} – {fmtNum(adv.sharpe_ci.ci_high)}</b></div>
                <div><span>{t("advPSR")}</span>
                  <b className={adv.sharpe_ci.psr >= 0.9 ? "up" : adv.sharpe_ci.psr < 0.6 ? "down" : ""}>
                    {fmtPct(adv.sharpe_ci.psr).replace("+", "")}
                  </b>
                </div>
              </div>
              <p className="section-note">{t("advPSRNote", { n: String(adv.sharpe_ci.observations) })}</p>
              <p className="section-note">{t("advPSRvsBeat")}</p>
              <GuideLink slug={MODELS} />
            </div>
          )}
          {adv.beat_deposit && (
            <div className="card">
              <h3>{t("advBeatDepTitle")}</h3>
              <div className="score-main">
                <div className={`score-big ${(1 - adv.beat_deposit.prob_below_deposit) >= 0.6 ? "up" : (1 - adv.beat_deposit.prob_below_deposit) < 0.4 ? "down" : ""}`}>
                  {fmtPct(1 - adv.beat_deposit.prob_below_deposit).replace("+", "")}
                </div>
              </div>
              <p className="section-note">{t("advBeatDepNote", {
                r: fmtPct(adv.beat_deposit.deposit_annual).replace("+", ""),
                p: fmtPct(adv.beat_deposit.prob_below_deposit).replace("+", ""),
                pt: fmtPct(1 - adv.beat_deposit.prob_below_point).replace("+", ""),
              })}</p>
              <GuideLink slug={MODELS} />
            </div>
          )}
        </div>
      )}

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
                    {adv.ewma.es_fhs_pct != null && (
                      <tr><td className="name">{t("advEsFhs")}</td><td className="down">{fmtPct(adv.ewma.es_fhs_pct)}</td></tr>
                    )}
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
              <div className="bt-block">
                <div className="bt-head">{t("advBacktestHead", { n: String(adv.backtest.days) })}</div>
                <div className="tbl-wrap"><table className="tbl">
                  <thead><tr>
                    <th>{t("advModelCol")}</th><th>{t("advViolCol")}</th>
                    <th>Kupiec</th><th>Basel</th>
                  </tr></thead>
                  <tbody>
                    {(["historical", "ewma", "fhs"] as const).map((m) => {
                      const b = adv.backtest!.models[m];
                      return (
                        <tr key={m}>
                          <td className="name">{tk(`advModel_${m}`)}</td>
                          <td>{b.violations} / {b.expected}</td>
                          <td className="dim">%{(b.kupiec_p * 100).toFixed(0)}</td>
                          <td><b className={zoneCls[b.basel_zone]}>{tk(`advZoneShort_${b.basel_zone}`)}</b></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table></div>
                <p className="section-note">{t("advBacktestNote2")}</p>
              </div>
            )}
            {adv.headline_var && adv.headline_var.model !== "historical" && (
              <p className="section-note"><b>{t("advDerivedBase", { m: tk(`advModel_${adv.headline_var.model}`) })}</b></p>
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
            <p className="section-note">{t("advRealNote", {
              d: adv.real.cpi_as_of, s: adv.real.period_start ?? "",
            })}</p>
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
            <p className="section-note">{t("advFxDriftNote", {
              v: fmtPct(adv.fx.fx_vol_ann).replace("+", ""),
              d: fmtPct(adv.fx.fx_drift_ann),
            })}</p>
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
            <p className="section-note">{t("advTailObsNote", {
              n: String(adv.tail_dependence.tail_obs),
              e: String(adv.tail_dependence.expected_co),
            })}</p>
            <GuideLink slug={ATTRIB} />
          </div>
        )}
      </div>

      {/* Faktor sok izgarasi (hipotetik parametrik stres) — nominal + reel */}
      {adv.factor_shock && adv.factor_shock.scenarios.length > 0 && (
        <div className="card">
          <h3>{t("advFactorShock")}</h3>
          <div className="tbl-wrap"><table className="tbl">
            <thead><tr>
              <th>{t("advScenarioCol")}</th>
              <th>{t("advNominalCol")}</th>
              <th>{t("advRealCol")}</th>
            </tr></thead>
            <tbody>
              {adv.factor_shock.scenarios.map((s) => (
                <tr key={s.name}>
                  <td className="name">{s.name}</td>
                  <td><Delta v={s.impact_tl}>{fmtTL(s.impact_tl)}</Delta>
                    <span className="dim"> ({fmtPct(s.impact_pct)})</span></td>
                  <td><Delta v={s.impact_real_pct}>{fmtPct(s.impact_real_pct)}</Delta></td>
                </tr>
              ))}
            </tbody>
          </table></div>
          <p className="section-note">{t("advFactorShockNote", { pt: ((adv.factor_shock.passthrough ?? 0.4) * 100).toFixed(0) })}</p>
          <p className="section-note">{t("advFactorRealNote", { pt: ((adv.factor_shock.passthrough ?? 0.4) * 100).toFixed(0) })}</p>
          <GuideLink slug={REALFX} />
        </div>
      )}

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
          {adv.hrp.excluded_cash_like && adv.hrp.excluded_cash_like.length > 0 && (
            <p className="section-note">{t("advHrpCash", { list: adv.hrp.excluded_cash_like.join(", ") })}</p>
          )}
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
                {s.r2 != null && s.r2 >= 0.30
                  ? t("advStyleNote", {
                      r2: fmtPct(s.r2).replace("+", ""),
                      te: fmtPct(s.tracking_error_ann).replace("+", ""),
                      ir: s.information_ratio != null ? fmtNum(s.information_ratio) : "—",
                    })
                  : t("advStyleLowR2", { r2: s.r2 != null ? fmtPct(s.r2).replace("+", "") : "—" })}
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
