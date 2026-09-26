"""Admin paneli uclari. Yalnizca ADMIN_EMAIL sahibi erisebilir.

Kimlik dogrulama mevcut JWT akisini yeniden kullanir (auth.get_current_user);
tek fark, get_admin_user'in token sahibinin e-postasini ADMIN_EMAIL ile
karsilastirmasidir. QPC (kantitatif portfoy insasi) toollari buraya eklenecek.
"""

import os

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from db import User

# Panelin tek yetkili kullanicisi. Prod'da env ile ezilebilir.
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "anilserdar.unal20@gmail.com").lower()

router = APIRouter(prefix="/admin", tags=["admin"])


def get_admin_user(user: User = Depends(get_current_user)) -> User:
    """get_current_user'in ustune yetki katmani: sadece ADMIN_EMAIL gecer."""
    if (user.email or "").lower() != ADMIN_EMAIL:
        raise HTTPException(403, "Bu alana erişim yetkiniz yok.")
    return user


@router.get("/me")
def admin_me(user: User = Depends(get_admin_user)):
    """Panel acilisinda token + yetki dogrulamasi. Frontend bununla kapiyi acar."""
    return {"email": user.email, "nickname": user.nickname, "admin": True}
