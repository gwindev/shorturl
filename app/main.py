from __future__ import annotations

import base64
import io
import secrets
from datetime import datetime, timedelta
from typing import Generator, Optional

import qrcode
from fastapi import Body, Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, HttpUrl
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

SECRET_KEY = "33e7bfde4f9106a0a2a2b037aab6777ae4753e7daac97800d2b62577c9c6a0a2"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
BASE_URL = "http://localhost:8000"

engine = create_engine("sqlite:///./shorturl.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def build_short_link(code: str) -> str:
    return f"{BASE_URL}/{code}"


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
    clicks: Mapped[list["Click"]] = relationship(back_populates="short_url", cascade="all, delete-orphan")


class Click(Base):
    __tablename__ = "clicks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    short_url_id: Mapped[int] = mapped_column(ForeignKey("short_urls.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ip: Mapped[str] = mapped_column(String(48))
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    short_url: Mapped[ShortURL] = relationship(back_populates="clicks")


class ShortenRequest(BaseModel):
    original_url: HttpUrl


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
    return templates.TemplateResponse("login.html", {"request": request, "error": None, "user": None})


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = authenticate_user(db, username, password)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "user": None},
        )

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


def get_short_url(db: Session, url_id: int) -> Optional[ShortURL]:
    return db.scalar(select(ShortURL).where(ShortURL.id == url_id))


def detect_device_type(user_agent: Optional[str]) -> str:
    if not user_agent:
        return "desktop"
    ua = user_agent.lower()
    mobile_keywords = ["mobile", "iphone", "ipad", "android", "blackberry", "phone", "tablet"]
    for kw in mobile_keywords:
        if kw in ua:
            return "mobile"
    return "desktop"


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
    short_link = build_short_link(code)
    qr = make_qr_data_uri(short_link)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": user, "urls": urls, "base_url": BASE_URL, "qr": qr, "latest_short_link": short_link},
    )


@app.get("/dashboard/url/{url_id}/edit", response_class=HTMLResponse)
def edit_url_page(url_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_web_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    record = get_short_url(db, url_id)
    if not record or record.owner_id != user.id:
        return HTMLResponse("<h3>404 ไม่พบลิงก์ที่ต้องการ</h3>", status_code=404)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "urls": db.scalars(select(ShortURL).where(ShortURL.owner_id == user.id).order_by(ShortURL.id.desc())).all(),
            "base_url": BASE_URL,
            "edit_url": record,
        },
    )


@app.get("/dashboard/url/{url_id}/stats")
def url_stats(
    url_id: int,
    ip: Optional[str] = None,
    country: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    record = get_short_url(db, url_id)
    if not record:
        raise HTTPException(status_code=404, detail="URL not found")

    query = select(Click).where(Click.short_url_id == url_id)
    if ip:
        query = query.where(Click.ip.contains(ip))
    if country:
        query = query.where(Click.country == country)
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
            query = query.where(Click.created_at >= start_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date")
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
            query = query.where(Click.created_at <= end_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date")

    clicks = db.scalars(query.order_by(Click.created_at)).all()

    stats: dict[str, dict[str, int]] = {}
    for click in clicks:
        day = click.created_at.date().isoformat()
        device = detect_device_type(click.user_agent)
        stats.setdefault(day, {"mobile": 0, "desktop": 0})
        stats[day][device] += 1

    labels = sorted(stats.keys())
    mobile = [stats[d]["mobile"] for d in labels]
    desktop = [stats[d]["desktop"] for d in labels]

    return {
        "labels": labels,
        "mobile": mobile,
        "desktop": desktop,
        "total_clicks": len(clicks),
    }


@app.post("/dashboard/url/{url_id}/edit", response_class=HTMLResponse)
def edit_url(url_id: int, request: Request, original_url: str = Form(...), db: Session = Depends(get_db)):
    user = get_web_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    record = get_short_url(db, url_id)
    if not record or record.owner_id != user.id:
        return HTMLResponse("<h3>404 ไม่พบลิงก์ที่ต้องการ</h3>", status_code=404)

    record.original_url = original_url
    db.commit()

    return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/dashboard/url/{url_id}/delete", response_class=HTMLResponse)
def delete_url(url_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_web_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    record = get_short_url(db, url_id)
    if record and record.owner_id == user.id:
        db.delete(record)
        db.commit()

    return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)


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


@app.get("/api/auth/me")
def me_api(current_user: User = Depends(get_current_api_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "is_admin": current_user.is_admin,
    }


@app.post("/api/shorten")
def shorten_api(original_url: str = Form(...), current_user: User = Depends(get_current_api_user), db: Session = Depends(get_db)):
    code = create_short_code(db)
    new_url = ShortURL(original_url=original_url, short_code=code, owner_id=current_user.id)
    db.add(new_url)
    db.commit()
    short_link = build_short_link(code)
    return JSONResponse({"original_url": original_url, "short_code": code, "short_url": short_link, "qr_data_uri": make_qr_data_uri(short_link)})


@app.post("/api/shorten-json")
def shorten_api_json(payload: ShortenRequest = Body(...), current_user: User = Depends(get_current_api_user), db: Session = Depends(get_db)):
    code = create_short_code(db)
    new_url = ShortURL(original_url=str(payload.original_url), short_code=code, owner_id=current_user.id)
    db.add(new_url)
    db.commit()
    short_link = build_short_link(code)
    return {
        "original_url": str(payload.original_url),
        "short_code": code,
        "short_url": short_link,
        "qr_data_uri": make_qr_data_uri(short_link),
    }


@app.get("/api/my-urls")
def my_urls_api(current_user: User = Depends(get_current_api_user), db: Session = Depends(get_db)):
    urls = db.scalars(select(ShortURL).where(ShortURL.owner_id == current_user.id).order_by(ShortURL.id.desc())).all()
    return [
        {
            "id": item.id,
            "original_url": item.original_url,
            "short_code": item.short_code,
            "short_url": build_short_link(item.short_code),
            "created_at": item.created_at.isoformat(),
        }
        for item in urls
    ]


@app.get("/s/{short_code}")
def redirect_short_url(short_code: str, request: Request, db: Session = Depends(get_db)):
    record = db.scalar(select(ShortURL).where(ShortURL.short_code == short_code))
    if not record:
        return HTMLResponse("<h3>404 ไม่พบลิงก์ที่ต้องการ</h3>", status_code=404)

    record_click(db, record, request)
    return RedirectResponse(record.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/{short_code}")
def redirect_short_url_root(short_code: str, request: Request, db: Session = Depends(get_db)):
    record = db.scalar(select(ShortURL).where(ShortURL.short_code == short_code))
    if not record:
        return HTMLResponse("<h3>404 ไม่พบลิงก์ที่ต้องการ</h3>", status_code=404)

    record_click(db, record, request)
    return RedirectResponse(record.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
