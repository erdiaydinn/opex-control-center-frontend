from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
import secrets

router = APIRouter(prefix="/auth", tags=["auth"])

# Demo user store. Production'da DB tablosu kullanılmalı.
USERS = {
    "erdi@example.com": {"username": "erdi", "role": "ADMIN"},
    "super@example.com": {"username": "super", "role": "SUPERUSER"},
    "user@example.com": {"username": "user", "role": "USER"},
}

RESET_TOKENS = {}

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    email = req.email.lower().strip()
    if email not in USERS:
        raise HTTPException(status_code=404, detail="Bu mail adresi kayıtlı değil.")

    token = secrets.token_urlsafe(32)
    RESET_TOKENS[token] = {
        "email": email,
        "expires_at": datetime.utcnow() + timedelta(minutes=30),
    }

    # Burada SMTP/SendGrid/Google Workspace mail gönderimi bağlanmalı.
    # reset_url = f"https://planogrameay.opex.com/reset-password?token={token}"
    print(f"[PASSWORD_RESET] email={email} token={token}")

    return {
        "success": True,
        "message": "Şifre sıfırlama maili gönderildi.",
    }
