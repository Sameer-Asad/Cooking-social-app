"""Small shared helper: how a user's name is shown wherever a display
name is needed (likes, comments, profile) — username if they've set one,
otherwise the local part of their email as a readable fallback."""

from app.models.models import User


def display_name(user: User) -> str:
    return user.username or user.email.split("@")[0]
