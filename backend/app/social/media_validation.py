"""AC-5 / Edge case: upload accepts exactly one media type (video OR
image), never both, plus a text description."""

from fastapi import HTTPException, UploadFile

from app.models.models import MediaType

_VIDEO_CONTENT_TYPES = {"video/mp4", "video/quicktime", "video/webm"}
_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def validate_single_media(
    video: UploadFile | None, image: UploadFile | None
) -> tuple[MediaType, UploadFile]:
    if video and image:
        raise HTTPException(
            status_code=400,
            detail="Upload only one media type per post — a video or an image, not both.",
        )
    if not video and not image:
        raise HTTPException(
            status_code=400, detail="Attach a video or an image to your post."
        )

    if video:
        if video.content_type not in _VIDEO_CONTENT_TYPES:
            raise HTTPException(
                status_code=400, detail=f"Unsupported video type: {video.content_type}"
            )
        return MediaType.video, video

    if image.content_type not in _IMAGE_CONTENT_TYPES:
        raise HTTPException(
            status_code=400, detail=f"Unsupported image type: {image.content_type}"
        )
    return MediaType.image, image
