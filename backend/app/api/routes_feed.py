from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.display import display_name
from app.models.models import User
from app.schemas.social import (
    CommentIn,
    CommentOut,
    LikeResponse,
    LikerOut,
    PostOut,
    ProfileOut,
)
from app.social.engagement import (
    add_comment,
    like_post,
    list_comments,
    list_likes,
    unlike_post,
)
from app.social.media_validation import validate_single_media
from app.social.posts import (
    create_post,
    liked_post_ids,
    list_feed,
    list_posts_by_author,
    save_uploaded_media,
)
from app.tasks.media_tasks import process_uploaded_media

router = APIRouter(prefix="/feed", tags=["feed"])


async def _to_post_out(post, liked_ids: set) -> PostOut:
    return PostOut(
        id=post.id,
        author_id=post.author_id,
        media_type=post.media_type,
        media_path=post.media_path,
        description=post.description,
        like_count=post.like_count,
        comment_count=post.comment_count,
        created_at=post.created_at,
        liked_by_me=post.id in liked_ids,
    )


@router.post("/posts", response_model=PostOut)
async def upload_post(
    description: str = Form(...),
    video: UploadFile | None = File(default=None),
    image: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    media_type, file = validate_single_media(video, image)
    media_path = await save_uploaded_media(media_type, file)

    post = await create_post(
        db,
        author_id=str(user.id),
        media_type=media_type,
        media_path=media_path,
        description=description,
    )

    try:
        process_uploaded_media.delay(media_path, media_type.value)
    except Exception:
        pass

    # A brand-new post was obviously not liked yet by its own author.
    return await _to_post_out(post, liked_ids=set())


@router.get("/posts", response_model=list[PostOut])
async def browse_feed(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    posts = await list_feed(db, limit=limit, offset=offset)
    liked_ids = await liked_post_ids(
        db, user_id=str(user.id), post_ids=[p.id for p in posts]
    )
    return [await _to_post_out(p, liked_ids) for p in posts]


@router.get("/profile", response_model=ProfileOut)
async def my_profile(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    """A user's own info plus their uploaded posts."""
    posts = await list_posts_by_author(db, author_id=str(user.id), limit=100, offset=0)
    liked_ids = await liked_post_ids(
        db, user_id=str(user.id), post_ids=[p.id for p in posts]
    )
    return ProfileOut(
        id=user.id,
        email=user.email,
        username=user.username,
        display_name=display_name(user),
        is_paid_tier=user.is_paid_tier,
        created_at=user.created_at,
        posts=[await _to_post_out(p, liked_ids) for p in posts],
    )


@router.post("/posts/{post_id}/like", response_model=LikeResponse)
async def like(
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = await like_post(db, post_id=str(post_id), user_id=str(user.id))
    return LikeResponse(post_id=post_id, like_count=count)


@router.delete("/posts/{post_id}/like", response_model=LikeResponse)
async def unlike(
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = await unlike_post(db, post_id=str(post_id), user_id=str(user.id))
    return LikeResponse(post_id=post_id, like_count=count)


@router.get("/posts/{post_id}/likes", response_model=list[LikerOut])
async def get_likes(post_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Who liked this post — Instagram-style."""
    pairs = await list_likes(db, post_id=str(post_id))
    return [
        LikerOut(
            user_id=liker.id,
            username=liker.username,
            display_name=display_name(liker),
            created_at=like.created_at,
        )
        for like, liker in pairs
    ]


@router.get("/posts/{post_id}/comments", response_model=list[CommentOut])
async def get_comments(post_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await list_comments(db, post_id=str(post_id))


@router.post("/posts/{post_id}/comments", response_model=CommentOut)
async def comment(
    post_id: uuid.UUID,
    body: CommentIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await add_comment(
        db, post_id=str(post_id), user_id=str(user.id), body=body.body
    )
