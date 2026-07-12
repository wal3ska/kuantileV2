import { useEffect, useRef, useState } from "react";
import { api, ApiError, setToken, type MailPrefs } from "./api";

export interface UserInfo { email: string; nickname: string | null; mail: MailPrefs }

export const displayName = (u: UserInfo) => u.nickname ?? u.email.split("@")[0];

const PERIOD_LABELS: [keyof MailPrefs, string][] = [
  ["daily", "Günlük"],
  ["weekly", "Haftalık"],
  ["monthly", "Aylık"],
  ["yearly", "Yıllık"],
];

function useOutsideClose(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open, close]);
  return ref;
}

function MailPrefsMenu({ prefs, onChange }: {
  prefs: MailPrefs;
  onChange: (p: MailPrefs) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useOutsideClose(open, () => setOpen(false));
  const activeCount = PERIOD_LABELS.filter(([k]) => prefs[k]).length;

  return (
    <div className="auth-wrap" ref={ref}>
      <button onClick={() => setOpen(!open)}>
        Rapor mailleri {activeCount > 0 ? `(${activeCount})` : "(kapalı)"} ▾
      </button>
      {open && (
        <div className="dropmenu">
          <div className="dropmenu-title">Portföy raporu e-postaları</div>
          {PERIOD_LABELS.map(([key, label]) => (
            <label className="checkline" key={key}>
              <input
                type="checkbox"
                checked={prefs[key]}
                onChange={(e) => onChange({ ...prefs, [key]: e.target.checked })}
              />
              {label}
            </label>
          ))}
          <div className="footer-note" style={{ marginTop: 4 }}>
            Günlük her sabah 07:00, haftalık pazartesi, aylık ayın 1'i, yıllık 1 Ocak'ta gönderilir.
          </div>
        </div>
      )}
    </div>
  );
}

export function AuthArea({ user, onLogin, onLogout, onSave, saving, onMailPrefs }: {
  user: UserInfo | null;
  onLogin: (u: UserInfo) => void;
  onLogout: () => void;
  onSave: () => void;
  saving: boolean;
  onMailPrefs: (p: MailPrefs) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useOutsideClose(open, () => setOpen(false));

  if (user) {
    return (
      <div className="userchip">
        <span title={user.email}>{displayName(user)}</span>
        <MailPrefsMenu prefs={user.mail} onChange={onMailPrefs} />
        <button className="primary" onClick={onSave} disabled={saving}>
          {saving ? "Kaydediliyor…" : "Kaydet"}
        </button>
        <button className="ghost" onClick={() => { setToken(null); onLogout(); }}>Çıkış</button>
      </div>
    );
  }

  return (
    <div className="auth-wrap" ref={ref}>
      <button className="primary" onClick={() => setOpen(!open)}>Giriş / Kayıt</button>
      {open && <AuthPop onLogin={(u) => { setOpen(false); onLogin(u); }} />}
    </div>
  );
}

function AuthPop({ onLogin }: { onLogin: (u: UserInfo) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [nick, setNick] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err" | "info"; text: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setBusy(true);
    try {
      if (mode === "register") {
        const r = await api.register(email, nick, pw);
        setMsg({ kind: "ok", text: r.message });
      } else {
        const r = await api.login(email, pw);
        setToken(r.access_token);
        const me = await api.me();
        onLogin({ email: me.email, nickname: me.nickname, mail: me.mail });
      }
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof ApiError ? err.message : "Beklenmeyen hata." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="auth-pop" onSubmit={submit}>
      <div className="seg">
        <button type="button" className={mode === "login" ? "on" : ""} onClick={() => setMode("login")}>Giriş</button>
        <button type="button" className={mode === "register" ? "on" : ""} onClick={() => setMode("register")}>Kayıt</button>
      </div>
      <label className="f">E-posta
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
      </label>
      {mode === "register" && (
        <label className="f">Takma ad
          <input
            type="text" required minLength={2} maxLength={30} placeholder="ör: anil"
            value={nick} onChange={(e) => setNick(e.target.value)} autoComplete="nickname"
          />
        </label>
      )}
      <label className="f">Şifre {mode === "register" && <span style={{ color: "var(--muted)" }}>(en az 8 karakter)</span>}
        <input
          type="password" required minLength={mode === "register" ? 8 : undefined}
          value={pw} onChange={(e) => setPw(e.target.value)}
          autoComplete={mode === "register" ? "new-password" : "current-password"}
        />
      </label>
      {msg && <div className={`msg ${msg.kind}`}>{msg.text}</div>}
      <button className="primary" disabled={busy}>
        {busy ? "Bekleyin…" : mode === "register" ? "Kayıt Ol" : "Giriş Yap"}
      </button>
      {mode === "register" && (
        <div className="footer-note">
          Kayıt sonrası e-postanıza doğrulama bağlantısı gönderilir. Kayıt zorunlu değildir;
          giriş yapmadan da analiz kullanılabilir — hesap, portföyünüzü kalıcı saklar ve rapor maillerini açar.
        </div>
      )}
    </form>
  );
}
