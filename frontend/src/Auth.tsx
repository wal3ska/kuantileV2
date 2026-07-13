import { useEffect, useRef, useState } from "react";
import { api, ApiError, setToken, type MailPrefs } from "./api";
import { useT } from "./i18n";

export interface UserInfo { email: string; nickname: string | null; mail: MailPrefs }

export const displayName = (u: UserInfo) => u.nickname ?? u.email.split("@")[0];

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
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const ref = useOutsideClose(open, () => setOpen(false));
  const periods = [
    ["daily", t("daily")], ["weekly", t("weekly")],
    ["monthly", t("monthly")], ["yearly", t("yearly")],
  ] as const;
  const activeCount = periods.filter(([k]) => prefs[k]).length;

  return (
    <div className="auth-wrap" ref={ref}>
      <button onClick={() => setOpen(!open)}>
        {t("reportMails")} {activeCount > 0 ? `(${activeCount})` : `(${t("off")})`} ▾
      </button>
      {open && (
        <div className="dropmenu">
          <div className="dropmenu-title">{t("mailMenuTitle")}</div>
          {periods.map(([key, label]) => (
            <label className="checkline" key={key}>
              <input
                type="checkbox"
                checked={prefs[key]}
                onChange={(e) => onChange({ ...prefs, [key]: e.target.checked })}
              />
              {label}
            </label>
          ))}
          <div className="footer-note" style={{ marginTop: 4 }}>{t("mailSchedule")}</div>
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
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const ref = useOutsideClose(open, () => setOpen(false));

  if (user) {
    return (
      <div className="userchip">
        <span title={user.email}>{displayName(user)}</span>
        <MailPrefsMenu prefs={user.mail} onChange={onMailPrefs} />
        <button className="primary" onClick={onSave} disabled={saving}>
          {saving ? t("saving") : t("save")}
        </button>
        <button className="ghost" onClick={() => { setToken(null); onLogout(); }}>{t("logout")}</button>
      </div>
    );
  }

  return (
    <div className="auth-wrap" ref={ref}>
      <button className="primary" onClick={() => setOpen(!open)}>{t("loginRegister")}</button>
      {open && <AuthPop onLogin={(u) => { setOpen(false); onLogin(u); }} />}
    </div>
  );
}

function AuthPop({ onLogin }: { onLogin: (u: UserInfo) => void }) {
  const { t, lang } = useT();
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
        await api.register(email, nick, pw, lang);
        setMsg({ kind: "ok", text: t("registerOk") });
      } else {
        const r = await api.login(email, pw);
        setToken(r.access_token);
        const me = await api.me();
        onLogin({ email: me.email, nickname: me.nickname, mail: me.mail });
      }
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof ApiError ? err.message : t("unexpectedErr") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="auth-pop" onSubmit={submit}>
      <div className="seg">
        <button type="button" className={mode === "login" ? "on" : ""} onClick={() => setMode("login")}>{t("login")}</button>
        <button type="button" className={mode === "register" ? "on" : ""} onClick={() => setMode("register")}>{t("register")}</button>
      </div>
      <label className="f">{t("email")}
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
      </label>
      {mode === "register" && (
        <label className="f">{t("nickname")}
          <input
            type="text" required minLength={2} maxLength={30} placeholder={t("nickPh")}
            value={nick} onChange={(e) => setNick(e.target.value)} autoComplete="nickname"
          />
        </label>
      )}
      <label className="f">{t("password")} {mode === "register" && <span style={{ color: "var(--muted)" }}>{t("pwHint")}</span>}
        <input
          type="password" required minLength={mode === "register" ? 8 : undefined}
          value={pw} onChange={(e) => setPw(e.target.value)}
          autoComplete={mode === "register" ? "new-password" : "current-password"}
        />
      </label>
      {msg && <div className={`msg ${msg.kind}`}>{msg.text}</div>}
      <button className="primary" disabled={busy}>
        {busy ? t("wait") : mode === "register" ? t("registerBtn") : t("loginBtn")}
      </button>
      {mode === "register" && <div className="footer-note">{t("registerNote")}</div>}
    </form>
  );
}
