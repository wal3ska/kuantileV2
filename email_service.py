"""Resend uzerinden e-posta gonderimi. RESEND_API_KEY ve MAIL_FROM env'den okunur."""

import os

import httpx

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
MAIL_FROM = os.getenv("MAIL_FROM", "Kuantile <onboarding@resend.dev>")
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://api.kuantile.com")


def send_email(to: str, subject: str, html: str) -> None:
    if not RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY tanımlı değil.")
    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        json={"from": MAIL_FROM, "to": [to], "subject": subject, "html": html},
        timeout=15,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"E-posta gönderilemedi: {resp.status_code} {resp.text[:200]}")


def send_verification(to: str, token: str) -> None:
    link = f"{APP_BASE_URL}/auth/verify?token={token}"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto">
      <h2>Kuantile'e hoş geldiniz</h2>
      <p>Hesabınızı doğrulamak için aşağıdaki bağlantıya tıklayın:</p>
      <p><a href="{link}" style="background:#1f77b4;color:#fff;padding:10px 18px;
         text-decoration:none;border-radius:6px">E-postamı Doğrula</a></p>
      <p style="color:#888;font-size:12px">Bu kaydı siz yapmadıysanız bu e-postayı yok sayabilirsiniz.</p>
    </div>
    """
    send_email(to, "Kuantile — E-posta Doğrulama", html)
