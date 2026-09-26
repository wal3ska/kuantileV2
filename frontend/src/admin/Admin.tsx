import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, getToken, setToken } from "../api";
import { Universe } from "./Universe";
import { Portfolio } from "./Portfolio";

interface AdminUser {
  email: string;
  nickname: string | null;
}

/* Panele eklenecek QPC toollari. Simdilik hepsi "yakinda" — kart iskeleti
   hazir, motor baglaninca `ready: true` yapip panel icerigini asariz. */
const TOOLS: { id: string; icon: string; title: string; desc: string; ready: boolean }[] = [
  {
    id: "universe",
    icon: "▦",
    title: "Varlık Evreni",
    desc: "Tüm BIST hisseleri: sektör, volatilite, geometrik getiri, likidite ve distress elemesi.",
    ready: true,
  },
  {
    id: "construct",
    icon: "◈",
    title: "Portföy & Analiz",
    desc: "Max-Sharpe/min-var/risk-parity/HRP ağırlık üretimi + OOS backtest + Monte Carlo projeksiyon + PDF risk raporu.",
    ready: true,
  },
  {
    id: "optimize",
    icon: "⟐",
    title: "Optimizasyon",
    desc: "Etkin sınır taraması, hedef fonksiyon ve kısıt seti üzerinde optimali ara.",
    ready: false,
  },
  {
    id: "risk",
    icon: "△",
    title: "Risk Ayrıştırma",
    desc: "Bileşen VaR/CVaR, faktör maruziyeti ve konsantrasyon teşhisi.",
    ready: false,
  },
];

function LoginView({ onLogin }: { onLogin: (u: AdminUser) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const r = await api.login(email.trim(), password);
      setToken(r.access_token);
      // Girisi yapan hesap admin mi? Backend get_admin_user karar verir.
      const me = await api.adminMe();
      onLogin({ email: me.email, nickname: me.nickname });
    } catch (ex) {
      setToken(null);
      if (ex instanceof ApiError && ex.status === 403) setErr("Bu hesabın panele erişim yetkisi yok.");
      else setErr(ex instanceof ApiError ? ex.message : "Giriş başarısız.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="a-login">
      <form className="a-login-card" onSubmit={submit}>
        <div className="a-brand">
          <img src="/logo.png" width="30" height="30" alt="" />
          <div>
            <b>Kuantile</b>
            <span>Quant Lab</span>
          </div>
        </div>
        <h1>Yönetici girişi</h1>
        <p className="a-sub">Bu alan yalnızca yetkili hesaba açıktır.</p>
        <label className="a-field">
          E-posta
          <input type="email" autoComplete="username" value={email}
            onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label className="a-field">
          Şifre
          <input type="password" autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {err && <div className="a-err">{err}</div>}
        <button className="a-primary" type="submit" disabled={busy}>
          {busy ? "Doğrulanıyor…" : "Giriş yap"}
        </button>
        <a className="a-back" href="/">← Siteye dön</a>
      </form>
    </div>
  );
}

function Panel({ user, onLogout }: { user: AdminUser; onLogout: () => void }) {
  const [active, setActive] = useState(TOOLS[0].id);
  const tool = TOOLS.find((t) => t.id === active)!;

  return (
    <div className="a-shell">
      <aside className="a-side">
        <div className="a-brand">
          <img src="/logo.png" width="26" height="26" alt="" />
          <div>
            <b>Quant Lab</b>
            <span>portföy inşası</span>
          </div>
        </div>
        <nav className="a-nav">
          {TOOLS.map((t) => (
            <button key={t.id} className={t.id === active ? "on" : ""} onClick={() => setActive(t.id)}>
              <span className="a-nav-ic">{t.icon}</span>
              {t.title}
              {!t.ready && <span className="a-soon">yakında</span>}
            </button>
          ))}
        </nav>
        <div className="a-side-foot">
          <div className="a-who" title={user.email}>{user.email}</div>
          <div className="a-side-links">
            <a href="/">Site</a>
            <button onClick={onLogout}>Çıkış</button>
          </div>
        </div>
      </aside>

      <main className="a-main">
        <header className="a-top">
          <div>
            <h1>{tool.title}</h1>
            <p>{tool.desc}</p>
          </div>
          <span className={`a-badge ${tool.ready ? "live" : ""}`}>{tool.ready ? "hazır" : "yapım aşamasında"}</span>
        </header>

        <section className="a-canvas">
          {active === "universe" ? (
            <Universe onAuthFail={onLogout} />
          ) : active === "construct" ? (
            <Portfolio onAuthFail={onLogout} />
          ) : (
            <div className="a-placeholder">
              <span className="a-ph-ic">{tool.icon}</span>
              <h2>{tool.title} aracı burada çalışacak</h2>
              <p>
                Motor bağlandığında bu bölge parametre paneli, sonuç tablosu ve canlı grafikle
                dolacak. Şimdilik iskelet hazır.
              </p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export function Admin() {
  const [user, setUser] = useState<AdminUser | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    if (!getToken()) {
      setChecking(false);
      return;
    }
    api.adminMe()
      .then((me) => setUser({ email: me.email, nickname: me.nickname }))
      .catch(() => setToken(null))
      .finally(() => setChecking(false));
  }, []);

  if (checking) return <div className="a-boot">Yükleniyor…</div>;
  if (!user) return <LoginView onLogin={setUser} />;
  return <Panel user={user} onLogout={() => { setToken(null); setUser(null); }} />;
}
