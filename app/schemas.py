from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, HttpUrl


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class ShortenRequest(BaseModel):
    original_url: HttpUrl
