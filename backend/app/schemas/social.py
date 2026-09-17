from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.models import MediaType


class PostOut(BaseModel):
    id: UUID
    author_id: UUID
    media_type: MediaType
    media_path: str
    description: str
    like_count: int
    comment_count: int
    created_at: datetime
    # Whether the requesting user has liked this post — lets the heart
    # icon render filled/empty correctly on load, not just after a click
    # this session. Computed per-request in routes_feed.py (it isn't a
    # column on Post itself), so it's always accurate for whoever asked.
    liked_by_me: bool = False

    class Config:
        from_attributes = True


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class CommentOut(BaseModel):
    id: UUID
    post_id: UUID
    user_id: UUID
    body: str
    created_at: datetime

    class Config:
        from_attributes = True


class LikeResponse(BaseModel):
    post_id: UUID
    like_count: int


class LikerOut(BaseModel):
    """One entry in 'who liked this post' (Instagram-style)."""

    user_id: UUID
    username: str | None
    display_name: str
    created_at: datetime


class ProfileOut(BaseModel):
    """A user's own profile: their info + their uploaded posts."""

    id: UUID
    email: str
    username: str | None
    display_name: str
    is_paid_tier: bool
    created_at: datetime
    posts: list[PostOut]
