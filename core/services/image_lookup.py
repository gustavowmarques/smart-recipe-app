import os
import logging
import requests
from urllib.parse import urlparse
from uuid import uuid4

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

log = logging.getLogger(__name__)

SPOON_URL = "https://api.spoonacular.com/recipes/complexSearch"


def spoonacular_image_for(title: str, api_key: str | None = None, timeout: int = 6) -> str | None:
    """
    Return a direct image URL from Spoonacular for a recipe title,
    or None if nothing found / API fails.
    """
    api_key = api_key or os.getenv("SPOONACULAR_API_KEY")
    if not api_key or not title:
        return None

    try:
        r = requests.get(
            SPOON_URL,
            params={"query": title, "number": 1, "apiKey": api_key},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json() or {}
        results = data.get("results") or []
        if results:
            return results[0].get("image")
    except Exception as e:
        log.warning("Spoonacular image lookup failed for %r: %s", title, e)

    return None


def cache_remote_image_to_storage(url: str, prefix: str = "recipe_images/") -> str | None:
    """
    OPTIONAL: Download a remote image and store it in Django's default storage (S3/local).
    Returns a public URL or None on failure.
    """
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()

        # Try to preserve extension
        path = urlparse(url).path
        ext = (path.rsplit(".", 1)[-1].lower() if "." in path else "jpg")
        key = f"{prefix}{uuid4().hex}.{ext}"

        default_storage.save(key, ContentFile(resp.content))
        return default_storage.url(key)
    except Exception as e:
        log.warning("Cache to storage failed for %s: %s", url, e)
        return None
