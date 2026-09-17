"""
AC-6: Like/Comment with counts updating immediately.

Edge case (Problem PRD Sec 4): "a post goes viral, huge spike in
likes/comments — system still updates smoothly without lag or crashing."
`Post.like_count`/`comment_count` are denormalized counters updated with
an atomic SQL increment (not a Python read-modify-write), so concurrent
likes on a viral post don't lose updates to a race condition, and reading
the feed never requires a COUNT(*) over the likes/comments tables.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import to_uuid
from app.models.models import Comment, Like, Post, User


async def like_post(db: AsyncSession, *, post_id: str, user_id: str) -> int:
    post_uuid = to_uuid(post_id)
    user_uuid = to_uuid(user_id)
    like = Like(post_id=post_uuid, user_id=user_uuid)
    db.add(like)
    try:
        await db.execute(
            update(Post)
            .where(Post.id == post_uuid)
            .values(like_count=Post.like_count + 1)
        )
        await db.commit()
    except IntegrityError:
        # UniqueConstraint on (post_id, user_id) — already liked, not an error.
        await db.rollback()

    result = await db.execute(select(Post.like_count).where(Post.id == post_uuid))
    count = result.scalar_one_or_none()
    if count is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return count


async def unlike_post(db: AsyncSession, *, post_id: str, user_id: str) -> int:
    """Removes the like (if any) and decrements the counter. A no-op —
    not an error — if the user hadn't liked the post, so a stray/repeat
    unlike request (e.g. a race with another tab) is harmless."""
    post_uuid = to_uuid(post_id)
    user_uuid = to_uuid(user_id)

    delete_result = await db.execute(
        delete(Like).where(Like.post_id == post_uuid, Like.user_id == user_uuid)
    )
    if delete_result.rowcount:
        # Guard against underflow the same way an unliked/never-liked
        # post can't go negative even under a duplicate/racing request.
        await db.execute(
            update(Post)
            .where(Post.id == post_uuid, Post.like_count > 0)
            .values(like_count=Post.like_count - 1)
        )
    await db.commit()

    result = await db.execute(select(Post.like_count).where(Post.id == post_uuid))
    count = result.scalar_one_or_none()
    if count is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return count


async def list_likes(
    db: AsyncSession, *, post_id: str, limit: int = 50
) -> list[tuple[Like, User]]:
    """(Like, User) pairs so the caller can show who liked a post —
    mirrors list_comments but needs the liker's identity, which Like
    alone doesn't carry beyond a bare user_id."""
    result = await db.execute(
        select(Like, User)
        .join(User, Like.user_id == User.id)
        .where(Like.post_id == to_uuid(post_id))
        .order_by(Like.created_at.desc())
        .limit(limit)
    )
    return list(result.all())


async def add_comment(
    db: AsyncSession, *, post_id: str, user_id: str, body: str
) -> Comment:
    comment = Comment(post_id=to_uuid(post_id), user_id=to_uuid(user_id), body=body)
    db.add(comment)
    await db.execute(
        update(Post)
        .where(Post.id == to_uuid(post_id))
        .values(comment_count=Post.comment_count + 1)
    )
    await db.commit()
    await db.refresh(comment)
    return comment


async def list_comments(
    db: AsyncSession, *, post_id: str, limit: int = 50
) -> list[Comment]:
    result = await db.execute(
        select(Comment)
        .where(Comment.post_id == to_uuid(post_id))
        .order_by(Comment.created_at)
        .limit(limit)
    )
    return list(result.scalars().all())
