import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    BASE_URL,
    build_short_link,
    create_access_token,
    create_short_code,
    detect_browser,
    detect_device_type,
    detect_os,
    get_current_api_user,
    make_qr_data_uri,
)
from ..database import get_db
from ..models import Click, ShortURL, User
from ..schemas import ShortenRequest

router = APIRouter(prefix="/api")


@router.post("/auth/token")
def login_api(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    from ..core import authenticate_user

    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/auth/me")
def me_api(current_user=Depends(get_current_api_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "is_admin": current_user.is_admin,
    }


@router.post("/shorten")
def shorten_api(
    original_url: str = Body(...),
    current_user=Depends(get_current_api_user),
    db: Session = Depends(get_db),
):
    code = secrets.token_urlsafe(6)[:6]
    new_url = ShortURL(original_url=original_url, short_code=code, owner_id=current_user.id)
    db.add(new_url)
    db.commit()
    short_link = build_short_link(code)
    return JSONResponse(
        {
            "original_url": original_url,
            "short_code": code,
            "short_url": short_link,
            "qr_data_uri": make_qr_data_uri(short_link),
        }
    )


@router.post("/shorten-json")
def shorten_api_json(
    payload: ShortenRequest = Body(...),
    current_user=Depends(get_current_api_user),
    db: Session = Depends(get_db),
):
    try:
        code = create_short_code(db, alias=payload.custom_alias)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    new_url = ShortURL(
        original_url=str(payload.original_url),
        short_code=code,
        custom_alias=payload.custom_alias,
        expires_at=payload.expires_at,
        owner_id=current_user.id,
    )
    db.add(new_url)
    db.commit()
    short_link = build_short_link(code)
    return {
        "original_url": str(payload.original_url),
        "short_code": code,
        "short_url": short_link,
        "qr_data_uri": make_qr_data_uri(short_link),
    }


@router.get("/my-urls")
def my_urls_api(current_user=Depends(get_current_api_user), db: Session = Depends(get_db)):
    urls = db.scalars(
        select(ShortURL).where(ShortURL.owner_id == current_user.id).order_by(ShortURL.id.desc())
    ).all()
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


@router.get("/url/{url_id}")
def get_url(url_id: int, current_user=Depends(get_current_api_user), db: Session = Depends(get_db)):
    record = db.scalar(select(ShortURL).where(ShortURL.id == url_id))
    if not record or record.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="URL not found")

    return {
        "id": record.id,
        "original_url": record.original_url,
        "short_code": record.short_code,
        "custom_alias": record.custom_alias,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "created_at": record.created_at.isoformat(),
    }


@router.put("/url/{url_id}")
def update_url(
    url_id: int,
    payload: ShortenRequest = Body(...),
    current_user=Depends(get_current_api_user),
    db: Session = Depends(get_db),
):
    record = db.scalar(select(ShortURL).where(ShortURL.id == url_id))
    if not record or record.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="URL not found")

    record.original_url = str(payload.original_url)
    db.commit()

    return {"status": "updated", "id": record.id}


@router.delete("/url/{url_id}")
def delete_url(url_id: int, current_user=Depends(get_current_api_user), db: Session = Depends(get_db)):
    record = db.scalar(select(ShortURL).where(ShortURL.id == url_id))
    if not record or record.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="URL not found")
    db.delete(record)
    db.commit()
    return {"status": "deleted", "id": url_id}


@router.get("/admin/users")
def admin_list_users(current_user=Depends(get_current_api_user), db: Session = Depends(get_db)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")

    users = db.scalars(select(User).order_by(User.id)).all()
    return [
        {"id": u.id, "username": u.username, "full_name": u.full_name, "is_admin": u.is_admin}
        for u in users
    ]


@router.post("/admin/users")
def admin_create_user(
    username: str = Body(...),
    password: str = Body(...),
    full_name: Optional[str] = Body(None),
    is_admin: bool = Body(False),
    current_user=Depends(get_current_api_user),
    db: Session = Depends(get_db),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")

    from ..core import ensure_unique_username, hash_password

    username = ensure_unique_username(db, username)
    user = User(
        username=username,
        full_name=full_name,
        hashed_password=hash_password(password),
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    return {"id": user.id, "username": user.username}


@router.get("/url/{url_id}/stats")
def url_stats(
    url_id: int,
    ip: Optional[str] = None,
    country: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by: str = "day",
    db: Session = Depends(get_db),
):
    record = db.scalar(select(ShortURL).where(ShortURL.id == url_id))
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

    def key_for_click(c: Click) -> str:
        if group_by == "month":
            return c.created_at.strftime("%Y-%m")
        return c.created_at.date().isoformat()

    stats: dict[str, dict[str, int]] = {}
    browser_totals: dict[str, int] = {}
    os_totals: dict[str, int] = {}

    for click in clicks:
        day = key_for_click(click)
        device = detect_device_type(click.user_agent)
        browser = detect_browser(click.user_agent)
        os_name = detect_os(click.user_agent)

        stats.setdefault(day, {"mobile": 0, "desktop": 0})
        stats[day][device] += 1

        browser_totals[browser] = browser_totals.get(browser, 0) + 1
        os_totals[os_name] = os_totals.get(os_name, 0) + 1

    labels = sorted(stats.keys())
    mobile = [stats[d]["mobile"] for d in labels]
    desktop = [stats[d]["desktop"] for d in labels]

    return {
        "labels": labels,
        "mobile": mobile,
        "desktop": desktop,
        "total_clicks": len(clicks),
        "browsers": browser_totals,
        "oses": os_totals,
    }


@router.get("/url/{url_id}/export")
def export_click_csv(
    url_id: int,
    ip: Optional[str] = None,
    country: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    record = db.scalar(select(ShortURL).where(ShortURL.id == url_id))
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

    def generate():
        import csv
        import io

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["timestamp", "ip", "country", "device", "browser", "os", "user_agent"])
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)

        for click in clicks:
            writer.writerow(
                [
                    click.created_at.isoformat(),
                    click.ip,
                    click.country or "",
                    detect_device_type(click.user_agent),
                    detect_browser(click.user_agent),
                    detect_os(click.user_agent),
                    click.user_agent or "",
                ]
            )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=clicks_{url_id}.csv"},
    )
