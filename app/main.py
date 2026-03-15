from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

from .core import hash_password
from .database import Base, SessionLocal, engine
from .models import User
from .routers import api_router, web_router


def _ensure_sqlite_columns() -> None:
    with engine.connect() as conn:
        try:
            rows = conn.execute(text("PRAGMA table_info('short_urls')")).fetchall()
        except Exception:
            return

        existing_columns = {r[1] for r in rows}
        if "custom_alias" not in existing_columns:
            conn.execute(text("ALTER TABLE short_urls ADD COLUMN custom_alias VARCHAR(30)"))
        if "expires_at" not in existing_columns:
            conn.execute(text("ALTER TABLE short_urls ADD COLUMN expires_at DATETIME"))


app = FastAPI(
    title="IT375 Mini Project - Short URL + QR",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(web_router)
app.include_router(api_router)


@app.on_event("startup")
def startup_event() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()

    db = SessionLocal()
    try:
        if not db.scalar(select(User).where(User.username == "admin")):
            db.add(
                User(
                    username="admin",
                    full_name="System Admin",
                    hashed_password=hash_password("admin123"),
                    is_admin=True,
                )
            )
        if not db.scalar(select(User).where(User.username == "student")):
            db.add(
                User(
                    username="student",
                    full_name="Demo Student",
                    hashed_password=hash_password("student123"),
                    is_admin=False,
                )
            )
        db.commit()
    finally:
        db.close()
