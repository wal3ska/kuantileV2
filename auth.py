"""Kimlik dogrulama: kayit, e-posta dogrulama, giris (JWT)."""

import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt as bcrypt_lib
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

import email_service
from db import Portfolio, User, get_db

JWT_SECRET = os.getenv("JWT_SECRET", "degistir-bunu-production-icin")
JWT_ALGO = "HS256"
TOKEN_TTL_HOURS = 24 * 7


def hash_password(p: str) -> str:
    return bcrypt_lib.hashpw(p.encode(), bcrypt_lib.gensalt()).decode()


def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt_lib.checkpw(p.encode(), h.encode())
    except ValueError:
        return False

bearer = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    nickname: str = Field(min_length=2, max_length=30)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def make_token(user_id: int) -> str:
    payload = {"sub": str(user_id),
               "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def make_unsub_token(user_id: int) -> str:
    payload = {"sub": str(user_id), "scope": "unsub",
               "exp": datetime.now(timezone.utc) + timedelta(days=365)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer),
                     db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(401, "Giriş gerekli.")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        raise HTTPException(401, "Geçersiz veya süresi dolmuş oturum.")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(401, "Kullanıcı bulunamadı.")
    return user


@router.post("/register", status_code=201)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email.lower()).first():
        raise HTTPException(409, "Bu e-posta ile bir hesap zaten var.")
    user = User(email=req.email.lower(),
                nickname=req.nickname.strip(),
                password_hash=hash_password(req.password),
                verification_token=secrets.token_urlsafe(32))
    db.add(user)
    db.commit()
    try:
        email_service.send_verification(user.email, user.verification_token)
    except Exception as exc:
        db.delete(user)
        db.commit()
        raise HTTPException(502, f"Doğrulama e-postası gönderilemedi: {exc}")
    return {"message": "Kayıt alındı. Lütfen e-postanızı doğrulayın."}


@router.get("/verify", response_class=HTMLResponse)
def verify(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.verification_token == token).first()
    if user is None:
        return HTMLResponse("<h3>Geçersiz veya kullanılmış doğrulama bağlantısı.</h3>", 400)
    user.is_verified = True
    user.verification_token = None
    if user.portfolio is None:
        db.add(Portfolio(user_id=user.id))
    db.commit()
    return HTMLResponse(
        "<div style='font-family:Arial;text-align:center;margin-top:80px'>"
        "<h2>E-posta doğrulandı ✓</h2>"
        "<p><a href='https://kuantile.com'>kuantile.com</a> üzerinden giriş yapabilirsiniz.</p></div>"
    )


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email.lower()).first()
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "E-posta veya şifre hatalı.")
    if not user.is_verified:
        raise HTTPException(403, "E-posta henüz doğrulanmamış. Gelen kutunuzu kontrol edin.")
    return {"access_token": make_token(user.id), "token_type": "bearer",
            "email": user.email, "nickname": user.nickname}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"email": user.email, "nickname": user.nickname, "verified": user.is_verified,
            "daily_mail": user.daily_mail_enabled}


class DailyMailRequest(BaseModel):
    enabled: bool


@router.post("/daily-mail")
def set_daily_mail(req: DailyMailRequest, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    user.daily_mail_enabled = req.enabled
    db.commit()
    return {"daily_mail": user.daily_mail_enabled}


@router.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe(token: str, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        if payload.get("scope") != "unsub":
            raise jwt.PyJWTError()
    except jwt.PyJWTError:
        return HTMLResponse("<h3>Geçersiz veya süresi dolmuş bağlantı.</h3>", 400)
    user = db.get(User, int(payload["sub"]))
    if user is not None:
        user.daily_mail_enabled = False
        db.commit()
    return HTMLResponse(
        "<div style='font-family:Arial;text-align:center;margin-top:80px'>"
        "<h2>Günlük özet maili kapatıldı</h2>"
        "<p>Dilediğiniz zaman <a href='https://kuantile.com'>kuantile.com</a> "
        "hesap bölümünden yeniden açabilirsiniz.</p></div>"
    )
