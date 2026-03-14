from __future__ import annotations

import base64
import io
import secrets
from datetime import datetime, timedelta
from typing import Generator, Optional

import qrcode
from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

SECRET_KEY = "change-this-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
BASE_URL = "http://localhost:8000"

engine = create_engine("sqlite:///./shorturl.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    urls: Mapped[list[ShortURL]] = relationship(back_populates="owner")


class ShortURL(Base):
    __tablename__ = "short_urls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    original_url: Mapped[str] = mapped_column(String(2048))
    short_code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    owner: Mapped[User] = relationship(back_populates="urls")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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


def create_short_code(db: Session, length: int = 6) -> str:
    while True:
        code = secrets.token_urlsafe(length)[:length]
        exists = db.scalar(select(ShortURL).where(ShortURL.short_code == code))
        if not exists:
            return code


def make_qr_data_uri(data: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=5, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


app = FastAPI(title="IT375 Mini Project - Short URL + QR")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def startup_event() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    if not get_user_by_username(db, "admin"):
        db.add(User(username="admin", full_name="System Admin", hashed_password=hash_password("admin123"), is_admin=True))
    if not get_user_by_username(db, "student"):
        db.add(User(username="student", full_name="Demo Student", hashed_password=hash_password("student123"), is_admin=False))
    db.commit()
    db.close()


def get_current_user_from_token(token: str, db: Session) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
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


def get_web_user(request: Request, db: Session) -> Optional[User]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        return get_current_user_from_token(token, db)
    except HTTPException:
        return None


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = get_web_user(request, db)
    return templates.TemplateResponse("home.html", {"request": request, "user": user})


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = authenticate_user(db, username, password)
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"})

    token = create_access_token({"sub": user.username}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie("access_token", token, httponly=True, samesite="lax")
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_web_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    urls = db.scalars(select(ShortURL).where(ShortURL.owner_id == user.id).order_by(ShortURL.id.desc())).all()
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user, "urls": urls, "base_url": BASE_URL, "qr": None})


@app.post("/dashboard/shorten", response_class=HTMLResponse)
def shorten_from_web(request: Request, original_url: str = Form(...), db: Session = Depends(get_db)):
    user = get_web_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    code = create_short_code(db)
    new_url = ShortURL(original_url=original_url, short_code=code, owner_id=user.id)
    db.add(new_url)
    db.commit()

    urls = db.scalars(select(ShortURL).where(ShortURL.owner_id == user.id).order_by(ShortURL.id.desc())).all()
    short_link = f"{BASE_URL}/s/{code}"
    qr = make_qr_data_uri(short_link)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": user, "urls": urls, "base_url": BASE_URL, "qr": qr, "latest_short_link": short_link},
    )


@app.get("/admin", response_class=HTMLResponse)
def admin_panel(request: Request, db: Session = Depends(get_db)):
    user = get_web_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    if not user.is_admin:
        return HTMLResponse("<h3>403 Forbidden</h3>", status_code=403)

    users = db.scalars(select(User).order_by(User.id)).all()
    urls = db.scalars(select(ShortURL).order_by(ShortURL.id.desc())).all()
    return templates.TemplateResponse("admin.html", {"request": request, "user": user, "users": users, "urls": urls})


@app.post("/api/auth/token")
def login_api(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user.username}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/api/shorten")
def shorten_api(original_url: str = Form(...), current_user: User = Depends(get_current_api_user), db: Session = Depends(get_db)):
    code = create_short_code(db)
    new_url = ShortURL(original_url=original_url, short_code=code, owner_id=current_user.id)
    db.add(new_url)
    db.commit()
    short_link = f"{BASE_URL}/s/{code}"
    return JSONResponse({"original_url": original_url, "short_code": code, "short_url": short_link, "qr_data_uri": make_qr_data_uri(short_link)})


@app.get("/api/my-urls")
def my_urls_api(current_user: User = Depends(get_current_api_user), db: Session = Depends(get_db)):
    urls = db.scalars(select(ShortURL).where(ShortURL.owner_id == current_user.id).order_by(ShortURL.id.desc())).all()
    return [
        {
            "id": item.id,
            "original_url": item.original_url,
            "short_code": item.short_code,
            "short_url": f"{BASE_URL}/s/{item.short_code}",
            "created_at": item.created_at.isoformat(),
        }
        for item in urls
    ]


@app.get("/s/{short_code}")
def redirect_short_url(short_code: str, db: Session = Depends(get_db)):
    record = db.scalar(select(ShortURL).where(ShortURL.short_code == short_code))
    if not record:
        return HTMLResponse("<h3>404 ไม่พบลิงก์ที่ต้องการ</h3>", status_code=404)
    return RedirectResponse(record.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
