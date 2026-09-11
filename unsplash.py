"""Fetch a random portrait photo from the Unsplash API, size-constrained."""

from __future__ import annotations

import logging
import uuid

import requests
from PIL import Image
import io

logger = logging.getLogger("daily_image")

UNSPLASH_API_BASE = "https://api.unsplash.com"


def fetch_random_photo(access_key: str, query: str | None = None) -> dict:
    """Return metadata for a random portrait-oriented Unsplash photo.

    Unsplash's /photos/random sits behind a CDN that caches responses by the
    exact request URL, so two calls with an identical query string can return
    the same cached photo instead of a fresh random pick. `_cb` is an unused
    parameter that only exists to vary the URL per call and bust that cache.
    """
    params = {
        "orientation": "portrait",
        "content_filter": "high",
        "_cb": uuid.uuid4().hex,
    }
    if query:
        params["query"] = query

    resp = requests.get(
        f"{UNSPLASH_API_BASE}/photos/random",
        headers={"Authorization": f"Client-ID {access_key}"},
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def notify_download(photo: dict, access_key: str) -> None:
    """Ping Unsplash's download-tracking endpoint, per their API guidelines."""
    download_location = photo.get("links", {}).get("download_location")
    if not download_location:
        return
    try:
        resp = requests.get(
            download_location,
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Failed to register Unsplash download event: %s", exc)


def download_constrained_image(photo: dict, width: int, height: int) -> Image.Image:
    """Download the photo cropped/resized to exactly width x height.

    Uses Unsplash's imgix-backed URL query parameters (w, h, fit=crop) on the
    `raw` image URL so the server returns an image already constrained to the
    requested dimensions, rather than fetching a full-size image and cropping
    client-side.
    """
    raw_url = photo["urls"]["raw"]
    params = {
        "w": width,
        "h": height,
        "fit": "crop",
        "crop": "entropy",
        "q": 90,
        "fm": "jpg",
    }
    resp = requests.get(raw_url, params=params, timeout=30)
    resp.raise_for_status()

    image = Image.open(io.BytesIO(resp.content)).convert("RGB")
    if image.size != (width, height):
        image = image.resize((width, height), Image.LANCZOS)
    return image
