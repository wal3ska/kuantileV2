import { useCallback, useEffect, useState } from "react";
import type { AnalyzeResponse, BondIn, PositionIn } from "./api";
import { api, ApiError, getToken, setToken } from "./api";
import { AuthArea, type UserInfo } from "./Auth";
import { Builder, newBond, nextId, num, type BondRow, type PosRow } from "./Builder";
import { Dashboard } from "./Dashboard";

function Logo() {
  return (
    <div className="logo">
      <svg width="26" height="26" viewBox="0 0 32 32">
        <rect width="32" height="32" rx="7" fill="#3987e5" />
        <path d="M8 24V8h3.2v7.1L17.4 8h4L15 15.6l6.8 8.4h-4l-5-6.4-1.6 1.8V24z" fill="#fff" />
      </svg>
      Kuantile
      <span className="tag">Portföy & Risk Terminali</span>
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
  const [rows, setRows] = useState<PosRow[]>([]);
  const [bonds, setBonds] = useState<BondRow[]>([]);
  const [user, setUser] = useState<UserInfo | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confidence, setConfidence] = useState(0.99);
  const [notice, setNotice] = useState<{ kind: "ok" | "err" | "info"; text: string } | null>(null);

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
        flash("info", "Kayıtlı portföyünüz yüklendi.");
      }
    } catch { /* portföy yüklenemedi — anonim akış devam eder */ }
  }, []);

  useEffect(() => {
    if (!getToken()) return;
    api.me()
      .then((me) => {
        setUser({ email: me.email, nickname: me.nickname, dailyMail: me.daily_mail });
        return loadPortfolio();
      })
      .catch(() => setToken(null));
  }, [loadPortfolio]);

  async function analyze() {
    const positions = toPositions(rows);
    const bs = toBonds(bonds);
    if (positions.length === 0 && bs.length === 0) {
      flash("err", "Önce en az bir varlığa adet girin veya tahvil ekleyin.");
      return;
    }
    for (const b of bs) {
      if (b.price <= 0 || b.years <= 0 || b.ytm <= 0) {
        flash("err", `"${b.name}" için fiyat, vade ve YTM sıfırdan büyük olmalı.`);
        return;
      }
    }
    setAnalyzing(true);
    setNotice(null);
    try {
      setResult(await api.analyze(positions, bs, confidence));
    } catch (err) {
      flash("err", err instanceof ApiError ? err.message : "Analiz başarısız oldu.");
    } finally {
      setAnalyzing(false);
    }
  }

  async function save() {
    setSaving(true);
    try {
      await api.savePortfolio(toPositions(rows), toBonds(bonds));
      flash("ok", "Portföy kaydedildi ✓");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setToken(null);
        setUser(null);
        flash("err", "Oturum süresi doldu, tekrar giriş yapın.");
      } else {
        flash("err", err instanceof ApiError ? err.message : "Kaydedilemedi.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function setDailyMail(enabled: boolean) {
    if (!user) return;
    const prev = user.dailyMail;
    setUser({ ...user, dailyMail: enabled });
    try {
      await api.setDailyMail(enabled);
    } catch {
      setUser((u) => (u ? { ...u, dailyMail: prev } : u));
      flash("err", "Tercih kaydedilemedi.");
    }
  }

  const hasInput = toPositions(rows).length > 0 || toBonds(bonds).length > 0;

  return (
    <>
      <header className="topbar">
        <Logo />
        <div className="spacer" />
        {notice && <div className={`msg ${notice.kind}`}>{notice.text}</div>}
        <AuthArea
          user={user}
          onLogin={(u) => { setUser(u); loadPortfolio(); }}
          onLogout={() => setUser(null)}
          onSave={save}
          saving={saving}
          onDailyMail={setDailyMail}
        />
      </header>

      <main className="layout">
        <div className="stack">
          <Builder rows={rows} setRows={setRows} bonds={bonds} setBonds={setBonds} />
        </div>

        <div className="stack">
          <div className="card" style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <button className="primary big" style={{ flex: "1 1 220px" }} onClick={analyze} disabled={analyzing || !hasInput}>
              {analyzing ? (<><span className="spin" />Analiz ediliyor — fiyat geçmişi çekiliyor…</>) : "⚡ Analiz Et"}
            </button>
            <label className="f" style={{ flex: "0 0 150px" }}>VaR güven düzeyi
              <select value={confidence} onChange={(e) => setConfidence(+e.target.value)}>
                <option value={0.95}>%95</option>
                <option value={0.99}>%99</option>
              </select>
            </label>
          </div>

          {result ? (
            <Dashboard data={result} />
          ) : (
            <div className="empty">
              <h2>Portföyünüz ne kadar risk taşıyor?</h2>
              <p>
                Soldan varlıklarınızı ekleyin, adetleri girin ve <b>Analiz Et</b>'e basın.<br />
                TL bazlı değerleme, %99 VaR, korelasyon, tarihsel kriz senaryoları ve tahvil durasyonu — tek ekranda.
              </p>
              <p className="footer-note">
                Hesap açarsanız portföyünüz saklanır; günlük, haftalık, aylık ve yıllık rapor e-postaları alırsınız. Hesapsız kullanım da serbesttir.
              </p>
            </div>
          )}
        </div>
      </main>
    </>
  );
}
