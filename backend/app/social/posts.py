from __future__ import annotations

import os
import uuid

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.ids import to_uuid
from app.models.models import Like, MediaType, Post


async def save_uploaded_media(media_type: MediaType, file: UploadFile) -> str:
    """Writes the file to MEDIA_ROOT and returns the relative path stored
    on the Post row. Actual encoding/thumbnailing happens async in
    tasks/media_tasks.py so this stays fast for the request path."""
    ext = os.path.splitext(file.filename or "")[1] or (
        ".mp4" if media_type == MediaType.video else ".jpg"
    )
    subdir = "videos" if media_type == MediaType.video else "images"
    filename = f"{uuid.uuid4()}{ext}"

    absolute_dir = os.path.join(settings.media_root, subdir)
    os.makedirs(absolute_dir, exist_ok=True)
    absolute_path = os.path.join(absolute_dir, filename)

    contents = await file.read()
    with open(absolute_path, "wb") as f:
        f.write(contents)

    relative_path = f"{subdir}/{filename}"
    return relative_path


async def create_post(
    db: AsyncSession,
    *,
    author_id: str,
    media_type: MediaType,
    media_path: str,
    description: str,
) -> Post:
    post = Post(
        author_id=to_uuid(author_id),
        media_type=media_type,
        media_path=media_path,
        description=description,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


async def list_feed(
    db: AsyncSession, *, limit: int = 20, offset: int = 0
) -> list[Post]:
    result = await db.execute(
        select(Post).order_by(Post.created_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all())


async def list_posts_by_author(
    db: AsyncSession, *, author_id: str, limit: int = 20, offset: int = 0
) -> list[Post]:
    """A user's own uploaded posts, for the profile page."""
    result = await db.execute(
        select(Post)
        .where(Post.author_id == to_uuid(author_id))
        .order_by(Post.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def liked_post_ids(
    db: AsyncSession, *, user_id: str, post_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    """Which of `post_ids` the given user has liked — one query per page
    of posts, not one query per post. Used to fill in PostOut.liked_by_me
    so the heart renders correctly on load, not just after a click."""
    if not post_ids:
        return set()
    result = await db.execute(
        select(Like.post_id).where(
            Like.user_id == to_uuid(user_id), Like.post_id.in_(post_ids)
        )
    )
    return set(result.scalars().all())
