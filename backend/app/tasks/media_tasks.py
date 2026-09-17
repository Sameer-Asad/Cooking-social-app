from app.celery_app import celery_app


@celery_app.task(name="tasks.process_uploaded_media")
def process_uploaded_media(media_path: str, media_type: str) -> None:
    """Placeholder for post-upload processing (transcoding, thumbnail
    generation, virus scanning, etc.) — kept out of the request path per
    Sec 6's async discipline. No concrete transcoding library is specified
    in either PRD, so this is intentionally a stub to wire up later."""
    # e.g. ffmpeg-based thumbnail extraction for videos would go here.
    pass
