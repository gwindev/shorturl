import os
import secrets
import urllib.parse

import httpx
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from ..core import (
    BASE_URL,
    build_short_link,
    create_access_token,
    create_user,
    ensure_unique_username,
    get_current_user_from_token,
    get_google_oauth_config,
    hash_password,
    make_qr_data_uri,
)
from ..database import get_db
from ..models import Click, ShortURL, User

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


def build_dashboard_context(request: Request, user: User, urls: list[ShortURL], top_links: Optional[list[dict]] = None, **extra):
    total_clicks = sum(len(item.clicks) for item in urls)
    context = {
        "request": request,
        "user": user,
        "urls": urls,
        "base_url": BASE_URL,
        "qr": None,
        "total_clicks": total_clicks,
        "top_links": top_links or [],
    }
    context.update(extra)
    return context


def get_web_user(request: Request, db):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        return get_current_user_from_token(token, db)
    except Exception:
        return None




@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request, db=Depends(get_db)):
    user = get_web_user(request, db)
    return templates.TemplateResponse("home.html", {"request": request, "user": user})


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request):
    google_enabled = bool(get_google_oauth_config())
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": None, "user": None, "google_enabled": google_enabled}
    )


@router.get("/register", response_class=HTMLResponse, include_in_schema=False)
def register_page(request: Request):
    google_enabled = bool(get_google_oauth_config())
    return templates.TemplateResponse(
        "register.html", {"request": request, "error": None, "user": None, "google_enabled": google_enabled}
    )


@router.post("/login", response_class=HTMLResponse, include_in_schema=False)
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db=Depends(get_db),
):
    from ..core import authenticate_user

    user = authenticate_user(db, username, password)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "user": None},
        )

    token = create_access_token({"sub": user.username}, timedelta(minutes=60))
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie("access_token", token, httponly=True, samesite="lax")
    return response


@router.post("/register", response_class=HTMLResponse, include_in_schema=False)
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    full_name: Optional[str] = Form(None),
    db=Depends(get_db),
):
    # Prevent registering reserved usernames
    if username.lower() in {"admin", "student"}:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "ชื่อผู้ใช้ไม่สามารถใช้ชื่อระบบได้", "user": None},
        )

    if db.scalar(select(User).where(User.username == username)):
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "ชื่อผู้ใช้นี้ถูกใช้งานแล้ว", "user": None},
        )

    create_user(db, username, password, full_name)

    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login/google", include_in_schema=False)
def login_google(request: Request):
    config = get_google_oauth_config()
    if not config:
        return HTMLResponse(
            "<h3>Google OAuth ยังไม่ได้ตั้งค่า (ตั้งค่า GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)</h3>",
            status_code=400,
        )

    # Use the request URL for the redirect unless overridden by env.
    redirect_uri = config.get("redirect_uri") or request.url_for("google_callback")

    params = {
        "client_id": config["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth"
    query = urllib.parse.urlencode(params)
    return RedirectResponse(f"{url}?{query}", status_code=status.HTTP_302_FOUND)


@router.get("/auth/google/callback", include_in_schema=False)
def google_callback(request: Request, code: Optional[str] = None, db=Depends(get_db)):
    config = get_google_oauth_config()
    if not config:
        return HTMLResponse(
            "<h3>Google OAuth ยังไม่ได้ตั้งค่า</h3>",
            status_code=400,
        )

    if not code:
        return HTMLResponse("<h3>Missing code from Google</h3>", status_code=400)

    token_url = "https://oauth2.googleapis.com/token"
    redirect_uri = config.get("redirect_uri") or request.url_for("google_callback")

    token_resp = httpx.post(
        token_url,
        data={
            "code": code,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    token_resp.raise_for_status()
    token_data = token_resp.json()

    userinfo_resp = httpx.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {token_data.get('access_token')}"},
        timeout=10,
    )
    userinfo_resp.raise_for_status()
    profile = userinfo_resp.json()

    email = profile.get("email")
    name = profile.get("name") or email.split("@")[0]
    if not email:
        return HTMLResponse("<h3>ไม่สามารถดึง email จาก Google ได้</h3>", status_code=400)

    user = db.scalar(select(User).where(User.username == email))
    if not user:
        # create new user with email as username
        user = create_user(db, email, secrets.token_urlsafe(16), full_name=name)

    token = create_access_token({"sub": user.username}, timedelta(minutes=60))
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie("access_token", token, httponly=True, samesite="lax")
    return response


@router.get("/logout", include_in_schema=False)
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request, db=Depends(get_db)):
    user = get_web_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    urls = db.scalars(
        select(ShortURL).where(ShortURL.owner_id == user.id).order_by(ShortURL.id.desc())
    ).all()

    one_week_ago = datetime.utcnow() - timedelta(days=7)
    top_links_rows = db.execute(
        select(
            ShortURL.id,
            ShortURL.short_code,
            ShortURL.custom_alias,
            ShortURL.original_url,
            func.count(Click.id).label("clicks"),
        )
        .join(Click, Click.short_url_id == ShortURL.id)
        .where(ShortURL.owner_id == user.id)
        .where(Click.created_at >= one_week_ago)
        .group_by(ShortURL.id)
        .order_by(func.count(Click.id).desc())
        .limit(5)
    ).all()

    top_links = [
        {
            "id": r[0],
            "short_code": r[1],
            "custom_alias": r[2],
            "original_url": r[3],
            "clicks": r[4],
        }
        for r in top_links_rows
    ]

    return templates.TemplateResponse(
        "dashboard.html",
        build_dashboard_context(request, user, urls, top_links=top_links),
    )


@router.post("/dashboard/shorten", response_class=HTMLResponse, include_in_schema=False)
def shorten_from_web(
    request: Request,
    original_url: str = Form(...),
    alias: Optional[str] = Form(None),
    expires_at: Optional[str] = Form(None),
    db=Depends(get_db),
):
    user = get_web_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    from ..core import create_short_code

    expiry_dt = None
    if expires_at:
        try:
            expiry_dt = datetime.fromisoformat(expires_at)
        except ValueError:
            expiry_dt = None

    try:
        code = create_short_code(db, alias=alias)
    except ValueError as exc:
        urls = db.scalars(
            select(ShortURL).where(ShortURL.owner_id == user.id).order_by(ShortURL.id.desc())
        ).all()
        return templates.TemplateResponse(
            "dashboard.html",
            build_dashboard_context(
                request,
                user,
                urls,
                error=str(exc),
            ),
        )

    new_url = ShortURL(
        original_url=original_url,
        short_code=code,
        custom_alias=alias.strip() if alias else None,
        expires_at=expiry_dt,
        owner_id=user.id,
    )
    db.add(new_url)
    db.commit()

    urls = db.scalars(
        select(ShortURL).where(ShortURL.owner_id == user.id).order_by(ShortURL.id.desc())
    ).all()
    short_link = build_short_link(code)
    qr = make_qr_data_uri(short_link)

    return templates.TemplateResponse(
        "dashboard.html",
        build_dashboard_context(
            request,
            user,
            urls,
            qr=qr,
            latest_short_link=short_link,
        ),
    )


@router.get("/dashboard/url/{url_id}/edit", response_class=HTMLResponse, include_in_schema=False)
def edit_url_page(url_id: int, request: Request, db=Depends(get_db)):
    user = get_web_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    record = db.scalar(select(ShortURL).where(ShortURL.id == url_id))
    if not record or record.owner_id != user.id:
        return HTMLResponse("<h3>404 ไม่พบลิงก์ที่ต้องการ</h3>", status_code=404)

    urls = db.scalars(select(ShortURL).where(ShortURL.owner_id == user.id).order_by(ShortURL.id.desc())).all()
    return templates.TemplateResponse("dashboard.html", build_dashboard_context(request, user, urls, edit_url=record))


@router.post("/dashboard/url/{url_id}/edit", response_class=HTMLResponse, include_in_schema=False)
def edit_url(url_id: int, request: Request, original_url: str = Form(...), db=Depends(get_db)):
    user = get_web_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    record = db.scalar(select(ShortURL).where(ShortURL.id == url_id))
    if not record or record.owner_id != user.id:
        return HTMLResponse("<h3>404 ไม่พบลิงก์ที่ต้องการ</h3>", status_code=404)

    record.original_url = original_url
    db.commit()

    return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/dashboard/url/{url_id}/delete", response_class=HTMLResponse, include_in_schema=False)
def delete_url(url_id: int, request: Request, db=Depends(get_db)):
    user = get_web_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    record = db.scalar(select(ShortURL).where(ShortURL.id == url_id))
    if record and record.owner_id == user.id:
        db.delete(record)
        db.commit()

    return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_panel(request: Request, db=Depends(get_db)):
    user = get_web_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    if not user.is_admin:
        return HTMLResponse("<h3>403 Forbidden</h3>", status_code=403)

    users = db.scalars(select(User).order_by(User.id)).all()
    urls = db.scalars(select(ShortURL).order_by(ShortURL.id.desc())).all()
    total_clicks = sum(len(item.clicks) for item in urls)
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "user": user, "users": users, "urls": urls, "total_clicks": total_clicks},
    )


@router.post("/admin/users/create", response_class=HTMLResponse, include_in_schema=False)
def admin_create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    full_name: Optional[str] = Form(None),
    is_admin: Optional[str] = Form(None),
    db=Depends(get_db),
):
    user = get_web_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    if not user.is_admin:
        return HTMLResponse("<h3>403 Forbidden</h3>", status_code=403)

    create_user(db, username, password, full_name, is_admin=bool(is_admin))
    return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/s/{short_code}", include_in_schema=False)
def redirect_short_url(short_code: str, request: Request, db=Depends(get_db)):
    record = db.scalar(
        select(ShortURL).where(
            (ShortURL.short_code == short_code) | (ShortURL.custom_alias == short_code)
        )
    )
    if not record:
        return HTMLResponse("<h3>404 ไม่พบลิงก์ที่ต้องการ</h3>", status_code=404)

    if record.expires_at and record.expires_at < datetime.utcnow():
        return HTMLResponse("<h3>ลิงก์นี้หมดอายุแล้ว</h3>", status_code=410)

    from ..core import record_click

    record_click(db, record, request)
    return RedirectResponse(record.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/{short_code}", include_in_schema=False)
def redirect_short_url_root(short_code: str, request: Request, db=Depends(get_db)):
    record = db.scalar(
        select(ShortURL).where(
            (ShortURL.short_code == short_code) | (ShortURL.custom_alias == short_code)
        )
    )
    if not record:
        return HTMLResponse("<h3>404 ไม่พบลิงก์ที่ต้องการ</h3>", status_code=404)

    if record.expires_at and record.expires_at < datetime.utcnow():
        return HTMLResponse("<h3>ลิงก์นี้หมดอายุแล้ว</h3>", status_code=410)

    from ..core import record_click

    record_click(db, record, request)
    return RedirectResponse(record.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
