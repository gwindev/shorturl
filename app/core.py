import base64
import io
import secrets
from datetime import datetime, timedelta
from typing import Optional

import qrcode
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Click, ShortURL, User


import os

from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SHORTQR_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
BASE_URL = os.getenv("SHORTQR_BASE_URL")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def build_short_link(code: str) -> str:
    return f"{BASE_URL}/{code}"


def make_qr_data_uri(data: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=5, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.scalar(select(User).where(User.username == username))


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = get_user_by_username(db, username)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def ensure_unique_username(db: Session, username: str) -> str:
    base = username
    counter = 1
    while db.scalar(select(User).where(User.username == username)):
        username = f"{base}{counter}"
        counter += 1
    return username


def create_user(db: Session, username: str, password: str, full_name: Optional[str] = None, is_admin: bool = False) -> User:
    username = ensure_unique_username(db, username)
    user = User(
        username=username,
        full_name=full_name,
        hashed_password=hash_password(password),
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    return user


def create_short_code(db: Session, length: int = 6, alias: Optional[str] = None) -> str:
    from .models import ShortURL

    if alias:
        cleaned = alias.strip()
        if not cleaned:
            raise ValueError("Alias cannot be empty")
        # allow url-safe characters
        if not all(c.isalnum() or c in "_-" for c in cleaned):
            raise ValueError("Alias can only contain letters, numbers, '-' and '_'")
        if len(cleaned) > 30:
            raise ValueError("Alias too long")
        # Ensure alias is not already used as a short code or a custom alias
        exists = db.scalar(
            select(ShortURL).where(
                (ShortURL.short_code == cleaned) | (ShortURL.custom_alias == cleaned)
            )
        )
        if exists:
            raise ValueError("Alias already in use")
        return cleaned

    while True:
        code = secrets.token_urlsafe(length)[:length]
        exists = db.scalar(select(ShortURL).where(ShortURL.short_code == code))
        if not exists:
            return code


def get_current_user_from_token(token: str, db: Session) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    user = get_user_by_username(db, username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_api_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    return get_current_user_from_token(token, db)


def detect_device_type(user_agent: Optional[str]) -> str:
    if not user_agent:
        return "desktop"
    ua = user_agent.lower()
    mobile_keywords = ["mobile", "iphone", "ipad", "android", "blackberry", "phone", "tablet"]
    for kw in mobile_keywords:
        if kw in ua:
            return "mobile"
    return "desktop"


def detect_browser(user_agent: Optional[str]) -> str:
    if not user_agent:
        return "Unknown"
    ua = user_agent.lower()
    if "edge" in ua or "edg" in ua:
        return "Edge"
    if "opr" in ua or "opera" in ua:
        return "Opera"
    if "chrome" in ua and "chromium" not in ua and "edge" not in ua:
        return "Chrome"
    if "safari" in ua and "chrome" not in ua:
        return "Safari"
    if "firefox" in ua:
        return "Firefox"
    if "msie" in ua or "trident" in ua:
        return "Internet Explorer"
    return "Other"


def detect_os(user_agent: Optional[str]) -> str:
    if not user_agent:
        return "Unknown"
    ua = user_agent.lower()
    if "windows" in ua:
        return "Windows"
    if "mac os" in ua or "macintosh" in ua:
        return "macOS"
    if "linux" in ua and "android" not in ua:
        return "Linux"
    if "android" in ua:
        return "Android"
    if "iphone" in ua or "ipad" in ua or "ipod" in ua:
        return "iOS"
    return "Other"


def record_click(db: Session, url: ShortURL, request: Request) -> None:
    country = request.headers.get("CF-IPCountry") or request.headers.get("X-Country")
    click = Click(
        short_url_id=url.id,
        ip=(request.client.host if request.client else ""),
        user_agent=request.headers.get("User-Agent"),
        country=country,
    )
    db.add(click)
    db.commit()


def get_google_oauth_config():
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }
