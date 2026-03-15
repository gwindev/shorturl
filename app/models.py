from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    urls: Mapped[list["ShortURL"]] = relationship(back_populates="owner")


class ShortURL(Base):
    __tablename__ = "short_urls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    original_url: Mapped[str] = mapped_column(String(2048))
    short_code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    custom_alias: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
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
