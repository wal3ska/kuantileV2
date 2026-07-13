import { useMemo, useRef, useState } from "react";
import type { AssetInfo } from "./universe";
import { CATEGORIES, UNIVERSE, customBist, customGlobal, customTefas } from "./universe";
import { catLabel, useT } from "./i18n";

/* Sayısal inputlar string tutulur (virgül/nokta serbest), gönderimde parse edilir. */
export function num(s: string): number {
  const v = parseFloat(s.replace(",", "."));
  return Number.isFinite(v) ? v : 0;
}

export interface PosRow {
  id: number;
  info: AssetInfo;
  quantity: string;
  cost: string;
  costUnknown: boolean;
}

export interface BondRow {
  id: number;
  name: string;
  currency: "TRY" | "USD";
  nominal: string;
  price: string;
  couponPct: string;
  frequency: number;
  years: string;
  ytmPct: string;
  cost: string;
  costUnknown: boolean;
}

let seq = 1;
export const nextId = () => seq++;

export function newBond(): BondRow {
  return {
    id: nextId(), name: `Tahvil`, currency: "TRY", nominal: "", price: "100",
    couponPct: "0", frequency: 2, years: "2", ytmPct: "40", cost: "", costUnknown: true,
  };
}

/* ---------- varlık seçici ---------- */

function AssetPicker({ taken, onAdd }: { taken: Set<string>; onAdd: (a: AssetInfo) => void }) {
  const { t } = useT();
  const [q, setQ] = useState("");
  const [cats, setCats] = useState<string[]>([...CATEGORIES]);
  const [focus, setFocus] = useState(false);
  const blurT = useRef(0);

  const results = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return UNIVERSE.filter((a) =>
      cats.includes(a.category) &&
      !taken.has(a.ticker + a.source) &&
      (needle === "" || a.name.toLowerCase().includes(needle) || a.ticker.toLowerCase().includes(needle)),
    ).slice(0, 60);
  }, [q, cats, taken]);

  return (
    <div>
      <div className="chips" style={{ marginBottom: 8 }}>
        {CATEGORIES.map((c) => (
          <button
            key={c} type="button"
            className={`chip ${cats.includes(c) ? "on" : ""}`}
            onClick={() => setCats(cats.includes(c) ? cats.filter((x) => x !== c) : [...cats, c])}
          >
            {catLabel(t, c)}
          </button>
        ))}
      </div>
      <div className="picker">
        <input
          type="text"
          placeholder={t("searchPh")}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => { clearTimeout(blurT.current); setFocus(true); }}
          onBlur={() => { blurT.current = window.setTimeout(() => setFocus(false), 150); }}
        />
        {focus && results.length > 0 && (
          <div className="picker-list">
            {results.map((a) => (
              <div
                key={a.ticker + a.source}
                className="picker-item"
                onMouseDown={(e) => { e.preventDefault(); onAdd(a); setQ(""); }}
              >
                <span>{a.name}</span>
                <span className="cat">{catLabel(t, a.category)} · {a.currency}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function CustomAdder({ label, placeholder, make, onAdd }: {
  label: string;
  placeholder: string;
  make: (code: string) => AssetInfo;
  onAdd: (a: AssetInfo) => void;
}) {
  const [v, setV] = useState("");
  const add = () => {
    v.split(",").map((s) => s.trim()).filter(Boolean).forEach((code) => onAdd(make(code)));
    setV("");
  };
  return (
    <div className="row">
      <input
        type="text" placeholder={placeholder} value={v}
        onChange={(e) => setV(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
      />
      <button type="button" style={{ flex: "0 0 auto" }} onClick={add}>{label}</button>
    </div>
  );
}

/* ---------- ana panel ---------- */

export function Builder({ rows, setRows, bonds, setBonds }: {
  rows: PosRow[];
  setRows: (r: PosRow[]) => void;
  bonds: BondRow[];
  setBonds: (b: BondRow[]) => void;
}) {
  const { t } = useT();
  const taken = useMemo(() => new Set(rows.map((r) => r.info.ticker + r.info.source)), [rows]);

  const addAsset = (a: AssetInfo) => {
    if (taken.has(a.ticker + a.source)) return;
    setRows([...rows, { id: nextId(), info: a, quantity: "", cost: "", costUnknown: false }]);
  };

  const patch = (id: number, p: Partial<PosRow>) =>
    setRows(rows.map((r) => (r.id === id ? { ...r, ...p } : r)));

  const patchBond = (id: number, p: Partial<BondRow>) =>
    setBonds(bonds.map((b) => (b.id === id ? { ...b, ...p } : b)));

  return (
    <div className="stack">
      <div className="card">
        <h3><span className="stepn">1</span>{t("step1")}</h3>
        <AssetPicker taken={taken} onAdd={addAsset} />
        <details className="acc" style={{ marginTop: 10 }}>
          <summary>{t("customSummary")}</summary>
          <div className="inner">
            <CustomAdder label={t("addBist")} placeholder={t("bistPh")} make={customBist} onAdd={addAsset} />
            <CustomAdder label={t("addGlobal")} placeholder={t("globalPh")} make={customGlobal} onAdd={addAsset} />
            <CustomAdder label={t("addFund")} placeholder={t("fundPh")} make={customTefas} onAdd={addAsset} />
          </div>
        </details>

        {rows.length > 0 && <hr className="sep" />}
        <div className="stack" style={{ gap: 8 }}>
          {rows.map((r) => (
            <div className="pos-row" key={r.id}>
              <div className="head">
                <span className="name">{r.info.name}</span>
                <span className="cur">{catLabel(t, r.info.category)} · {r.info.currency}</span>
                <button type="button" className="x" title={t("remove")}
                  onClick={() => setRows(rows.filter((x) => x.id !== r.id))}>✕</button>
              </div>
              <div className="row">
                <label className="f">{t("qty")}
                  <input type="text" inputMode="decimal" placeholder="0"
                    value={r.quantity} onChange={(e) => patch(r.id, { quantity: e.target.value })} />
                </label>
                <label className="f">{t("unitCost")} ({r.info.currency})
                  <input type="text" inputMode="decimal" placeholder="—"
                    value={r.cost} disabled={r.costUnknown}
                    onChange={(e) => patch(r.id, { cost: e.target.value })} />
                </label>
              </div>
              <label className="checkline">
                <input type="checkbox" checked={r.costUnknown}
                  onChange={(e) => patch(r.id, { costUnknown: e.target.checked })} />
                {t("costUnknown")}
              </label>
            </div>
          ))}
        </div>
        {rows.length === 0 && (
          <p className="section-note">{t("posNote")}</p>
        )}
      </div>

      <div className="card">
        <h3><span className="stepn">2</span>{t("step2")} <span className="opt">{t("optional")}</span></h3>
        <div className="stack" style={{ gap: 8 }}>
          {bonds.map((b, i) => (
            <details className="acc" key={b.id} open>
              <summary>{b.name || `${t("bondDefault")} ${i + 1}`} — {b.currency}</summary>
              <div className="inner">
                <div className="row">
                  <label className="f">{t("bondName")}
                    <input type="text" value={b.name} onChange={(e) => patchBond(b.id, { name: e.target.value })} />
                  </label>
                  <label className="f">{t("currency")}
                    <select value={b.currency} onChange={(e) => patchBond(b.id, { currency: e.target.value as "TRY" | "USD" })}>
                      <option>TRY</option><option>USD</option>
                    </select>
                  </label>
                </div>
                <div className="row">
                  <label className="f" title={t("nominalTip")}>
                    {t("nominal")} ({b.currency})
                    <input type="text" inputMode="decimal" placeholder={t("nominalPh")}
                      value={b.nominal} onChange={(e) => patchBond(b.id, { nominal: e.target.value })} />
                  </label>
                  <label className="f" title={t("marketPriceTip")}>{t("marketPrice")}
                    <input type="text" inputMode="decimal"
                      value={b.price} onChange={(e) => patchBond(b.id, { price: e.target.value })} />
                  </label>
                </div>
                <div className="row">
                  <label className="f">{t("couponPct")}
                    <input type="text" inputMode="decimal"
                      value={b.couponPct} onChange={(e) => patchBond(b.id, { couponPct: e.target.value })} />
                  </label>
                  <label className="f">{t("freq")}
                    <select value={b.frequency} onChange={(e) => patchBond(b.id, { frequency: +e.target.value })}>
                      <option value={2}>{t("freq2")}</option>
                      <option value={1}>{t("freq1")}</option>
                      <option value={4}>{t("freq4")}</option>
                    </select>
                  </label>
                </div>
                <div className="row">
                  <label className="f">{t("years")}
                    <input type="text" inputMode="decimal"
                      value={b.years} onChange={(e) => patchBond(b.id, { years: e.target.value })} />
                  </label>
                  <label className="f" title={t("ytmTip")}>YTM %
                    <input type="text" inputMode="decimal"
                      value={b.ytmPct} onChange={(e) => patchBond(b.id, { ytmPct: e.target.value })} />
                  </label>
                </div>
                <div className="row">
                  <label className="f">{t("purchasePrice")}
                    <input type="text" inputMode="decimal" placeholder="—"
                      value={b.cost} disabled={b.costUnknown}
                      onChange={(e) => patchBond(b.id, { cost: e.target.value })} />
                  </label>
                  <label className="checkline" style={{ alignSelf: "end", paddingBottom: 8 }}>
                    <input type="checkbox" checked={b.costUnknown}
                      onChange={(e) => patchBond(b.id, { costUnknown: e.target.checked })} />
                    {t("dontKnow")}
                  </label>
                </div>
                <button type="button" className="danger" onClick={() => setBonds(bonds.filter((x) => x.id !== b.id))}>
                  {t("removeBond")}
                </button>
              </div>
            </details>
          ))}
        </div>
        <button
          type="button"
          style={{ marginTop: bonds.length ? 10 : 0 }}
          onClick={() => setBonds([...bonds, { ...newBond(), name: `${t("bondDefault")} ${bonds.length + 1}` }])}
          disabled={bonds.length >= 5}
        >
          {t("addBond")}
        </button>
        <p className="section-note">{t("bondNote")}</p>
      </div>
    </div>
  );
}
