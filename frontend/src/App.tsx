import { useCallback, useEffect, useState } from "react";
import type { AnalyzeResponse, BondIn, MailPrefs, PositionIn } from "./api";
import { api, ApiError, getToken, setToken } from "./api";
import { AuthArea, type UserInfo } from "./Auth";
import { Builder, newBond, nextId, num, type BondRow, type PosRow } from "./Builder";
import { Dashboard } from "./Dashboard";
import { UNIVERSE } from "./universe";
import { useT, type Lang } from "./i18n";

function ThemeToggle({ theme, onToggle }: { theme: string; onToggle: () => void }) {
  const { t } = useT();
  return (
    <button
      className="ghost"
      onClick={onToggle}
      title={theme === "dark" ? t("themeToLight") : t("themeToDark")}
      aria-label={t("themeToggle")}
      style={{ display: "inline-flex", alignItems: "center", padding: "8px 10px" }}
    >
      {theme === "dark" ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      )}
    </button>
  );
}

function LangSwitch({ lang, setLang }: { lang: Lang; setLang: (l: Lang) => void }) {
  return (
    <div className="seg" style={{ width: 96 }}>
      {(["tr", "en"] as Lang[]).map((l) => (
        <button key={l} type="button" className={lang === l ? "on" : ""} onClick={() => setLang(l)}>
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

function Logo() {
  const { t } = useT();
  return (
    <div className="logo">
      <img src="/logo.png" width="28" height="28" alt="Kuantile logosu" />
      Kuantile
      <span className="tag">{t("tagline")}</span>
    </div>
  );
}

function toPositions(rows: PosRow[]): PositionIn[] {
  return rows
    .filter((r) => num(r.quantity) > 0)
    .map((r) => ({
      name: r.info.name,
      ticker: r.info.ticker,
      currency: r.info.currency,
      source: r.info.source,
      category: r.info.category,
      quantity: num(r.quantity),
      cost: r.costUnknown || num(r.cost) <= 0 ? null : num(r.cost),
    }));
}

function toBonds(bonds: BondRow[]): BondIn[] {
  return bonds
    .filter((b) => num(b.nominal) > 0)
    .map((b) => ({
      name: b.name || "Tahvil",
      currency: b.currency,
      nominal: num(b.nominal),
      price: num(b.price),
      coupon_rate: num(b.couponPct) / 100,
      frequency: b.frequency,
      years: num(b.years),
      ytm: num(b.ytmPct) / 100,
      cost: b.costUnknown || num(b.cost) <= 0 ? null : num(b.cost),
    }));
}

function fromPositions(ps: PositionIn[]): PosRow[] {
  return ps.map((p) => ({
    id: nextId(),
    info: { name: p.name, ticker: p.ticker, currency: p.currency, source: p.source, category: p.category },
    quantity: String(p.quantity),
    cost: p.cost === null ? "" : String(p.cost),
    costUnknown: p.cost === null,
  }));
}

function fromBonds(bs: BondIn[]): BondRow[] {
  return bs.map((b) => ({
    ...newBond(),
    name: b.name,
    currency: b.currency,
    nominal: String(b.nominal),
    price: String(b.price),
    couponPct: String(b.coupon_rate * 100),
    frequency: b.frequency,
    years: String(b.years),
    ytmPct: String(b.ytm * 100),
    cost: b.cost === null ? "" : String(b.cost),
    costUnknown: b.cost === null,
  }));
}

export default function App() {
  const { t, lang, setLang } = useT();
  const [rows, setRows] = useState<PosRow[]>([]);
  const [bonds, setBonds] = useState<BondRow[]>([]);
  const [user, setUser] = useState<UserInfo | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confidence, setConfidence] = useState(0.99);
  const [notice, setNotice] = useState<{ kind: "ok" | "err" | "info"; text: string } | null>(null);
  const [theme, setTheme] = useState(() => localStorage.getItem("kt_theme") ?? "light");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("kt_theme", theme);
  }, [theme]);

  const flash = (kind: "ok" | "err" | "info", text: string) => {
    setNotice({ kind, text });
    window.setTimeout(() => setNotice((n) => (n?.text === text ? null : n)), 5000);
  };

  const loadPortfolio = useCallback(async () => {
    try {
      const pf = await api.getPortfolio();
      if (pf.positions.length > 0 || pf.bonds.length > 0) {
        setRows(fromPositions(pf.positions));
        setBonds(fromBonds(pf.bonds));
        flash("info", t("portfolioLoaded"));
      }
    } catch { /* portföy yüklenemedi — anonim akış devam eder */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!getToken()) return;
    api.me()
      .then((me) => {
        setUser({ email: me.email, nickname: me.nickname, mail: me.mail });
        return loadPortfolio();
      })
      .catch(() => setToken(null));
  }, [loadPortfolio]);

  async function analyze(positionsArg?: PositionIn[], bondsArg?: BondIn[]) {
    const positions = positionsArg ?? toPositions(rows);
    const bs = bondsArg ?? toBonds(bonds);
    if (positions.length === 0 && bs.length === 0) {
      flash("err", t("errNoInput"));
      return;
    }
    for (const b of bs) {
      if (b.price <= 0 || b.years <= 0 || b.ytm <= 0) {
        flash("err", t("errBond", { name: b.name }));
        return;
      }
    }
    setAnalyzing(true);
    setNotice(null);
    try {
      setResult(await api.analyze(positions, bs, confidence));
    } catch (err) {
      flash("err", err instanceof ApiError ? err.message : t("analyzeFailed"));
    } finally {
      setAnalyzing(false);
    }
  }

  async function save() {
    setSaving(true);
    try {
      await api.savePortfolio(toPositions(rows), toBonds(bonds));
      flash("ok", t("saved"));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setToken(null);
        setUser(null);
        flash("err", t("sessionExpired"));
      } else {
        flash("err", err instanceof ApiError ? err.message : t("saveFailed"));
      }
    } finally {
      setSaving(false);
    }
  }

  async function setMailPrefs(prefs: MailPrefs) {
    if (!user) return;
    const prev = user.mail;
    setUser({ ...user, mail: prefs });
    try {
      await api.setMailPrefs(prefs);
    } catch {
      setUser((u) => (u ? { ...u, mail: prev } : u));
      flash("err", t("prefFailed"));
    }
  }

  function runDemo() {
    const demo: PosRow[] = [
      { name: "THYAO", qty: "100", cost: "250,5" },
      { name: "Altın (Gram TL)", qty: "20", cost: "" },
      { name: "Bitcoin (BTC)", qty: "0.02", cost: "" },
      { name: "Apple (AAPL)", qty: "5", cost: "185" },
    ].flatMap(({ name, qty, cost }) => {
      const info = UNIVERSE.find((a) => a.name === name);
      return info ? [{
        id: nextId(), info, quantity: qty, cost, costUnknown: cost === "",
      }] : [];
    });
    setRows(demo);
    setBonds([]);
    analyze(toPositions(demo), []);
  }

  const hasInput = toPositions(rows).length > 0 || toBonds(bonds).length > 0;

  return (
    <>
      <header className="topbar">
        <Logo />
        <div className="spacer" />
        {notice && <div className={`msg ${notice.kind}`}>{notice.text}</div>}
        <LangSwitch lang={lang} setLang={(l) => {
          setLang(l);
          if (user) api.setLang(l).catch(() => { /* dil tercihi arka planda; hata kritik değil */ });
        }} />
        <ThemeToggle theme={theme} onToggle={() => setTheme(theme === "dark" ? "light" : "dark")} />
        <AuthArea
          user={user}
          onLogin={(u) => { setUser(u); loadPortfolio(); }}
          onLogout={() => setUser(null)}
          onSave={save}
          saving={saving}
          onMailPrefs={setMailPrefs}
        />
      </header>

      <main className="layout">
        <div className="stack">
          <Builder rows={rows} setRows={setRows} bonds={bonds} setBonds={setBonds} />
        </div>

        <div className="stack">
          <div className="card">
            <h3><span className="stepn">3</span>{t("step3")}</h3>
            <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
              <button className="primary big" style={{ flex: "1 1 220px" }} onClick={() => analyze()} disabled={analyzing || !hasInput}>
                {analyzing ? (<><span className="spin" />{t("analyzing")}</>) : t("analyzeBtn")}
              </button>
              <label className="f" style={{ flex: "0 0 150px" }}>{t("varConf")}
                <select value={confidence} onChange={(e) => setConfidence(+e.target.value)}>
                  <option value={0.95}>{lang === "en" ? "95%" : "%95"}</option>
                  <option value={0.99}>{lang === "en" ? "99%" : "%99"}</option>
                </select>
              </label>
            </div>
            {!hasInput && <p className="section-note">{t("analyzeHint")}</p>}
          </div>

          {result ? (
            <Dashboard data={result} />
          ) : (
            <div className="empty">
              <h2>{t("emptyTitle")}</h2>
              <p>{t("emptyText")}</p>
              <div className="steps">
                <div className="step">
                  <span className="stepn">1</span>
                  <b>{t("s1t")}</b>
                  <p>{t("s1d")}</p>
                </div>
                <div className="step">
                  <span className="stepn">2</span>
                  <b>{t("s2t")}</b>
                  <p>{t("s2d")}</p>
                </div>
                <div className="step">
                  <span className="stepn">3</span>
                  <b>{t("s3t")}</b>
                  <p>{t("s3d")}</p>
                </div>
              </div>
              <button className="primary" onClick={runDemo} disabled={analyzing}>
                {analyzing ? (<><span className="spin" />{t("demoLoading")}</>) : t("demoBtn")}
              </button>
              <p className="footer-note">{t("emptyFooter")}</p>
            </div>
          )}
        </div>
      </main>
    </>
  );
}
