"""Image lookup helpers for recipes when an upstream source lacks images."""

import logging
import os
import re
import uuid
import mimetypes
from typing import Optional
import requests
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from uuid import uuid4

logger = logging.getLogger(__name__)

# -------- Spoonacular: title -> representative image URL --------
SPOON_KEY = os.getenv("SPOONACULAR_API_KEY")


def spoonacular_image_for(title: str) -> Optional[str]:
    """
    Best-effort: look up a representative image URL for a recipe title using Spoonacular.
    Returns a direct image URL (string) or None on error/limit/no match.
    """
    title = (title or "").strip()
    if not title or not SPOON_KEY:
        return None

    try:
        r = requests.get(
            "https://api.spoonacular.com/recipes/complexSearch",
            params={
                "apiKey": SPOON_KEY,
                "query": title,
                "number": 1,
                "addRecipeInformation": True,  # ensures 'image' is present/reliable
                "sort": "popularity",
                "instructionsRequired": False,
            },
            timeout=12,
        )
        if r.status_code in (402, 429) or r.status_code != 200:
            return None

        payload = r.json() or {}
        results = payload.get("results") or []
        if not results:
            return None
        img = (results[0].get("image") or "").strip()
        return img or None
    except Exception:
        return None


# -------- Cache remote image via Django storage (local in dev, S3 in prod) --------
SAFE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
CONTENT_TYPE_MAP = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _safe_slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9\-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or uuid.uuid4().hex


def _guess_ext(url: str, content_type: str | None) -> str:
    if content_type:
        ext = CONTENT_TYPE_MAP.get(content_type.split(";")[0].strip().lower())
        if ext:
            return ext
    url_ext = os.path.splitext(url.split("?")[0])[1].lower()
    if url_ext in SAFE_EXTS:
        return url_ext
    if content_type:
        ext = (
            mimetypes.guess_extension(content_type.split(";")[0].strip().lower())
            or ".jpg"
        )
        if ext == ".jpe":
            ext = ".jpg"
        if ext not in SAFE_EXTS:
            ext = ".jpg"
        return ext
    return ".jpg"


def cache_remote_image_to_storage(
    url, storage=None, subdir="recipe_images", filename_slug=None
):
    """Download a remote image, save to S3/local storage, and return its URL."""

    storage = storage or default_storage

    if not url:
        return None
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        ext = ".jpg"
        name = f"{folder}{uuid4().hex}{ext}"
        storage.save(name, ContentFile(resp.content))
        return storage.url(name)
    except Exception as exc:
        logger.warning("Image cache failed: %s", exc, exc_info=False)
        return None
