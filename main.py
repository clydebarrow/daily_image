"""Entrypoint for the daily_image Cloud Run Job.

Fetches a random portrait photo from Unsplash, dithers it to the E Ink
Spectra E6 six-colour palette, and uploads it as a PNG to a fixed object
name in a public GCS bucket so the resulting URL never changes day to day.
"""

import logging
import os
import sys
from datetime import datetime, timezone

from caption import add_attribution
from dither import dither_to_spectra_e6, snap_to_spectra_e6
from storage import upload_png
from unsplash import download_constrained_image, fetch_random_photo, notify_download

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("daily_image")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> None:
    unsplash_access_key = _require_env("UNSPLASH_ACCESS_KEY")
    gcs_bucket = _require_env("GCS_BUCKET")

    image_width = int(os.environ.get("IMAGE_WIDTH", "1200"))
    image_height = int(os.environ.get("IMAGE_HEIGHT", "1600"))
    object_name = os.environ.get("OBJECT_NAME", "latest.png")
    archive_objects = os.environ.get("ARCHIVE_OBJECTS", "false").lower() == "true"
    unsplash_query = os.environ.get("UNSPLASH_QUERY") or None

    logger.info("Fetching random portrait photo from Unsplash")
    photo = fetch_random_photo(unsplash_access_key, query=unsplash_query)
    logger.info("Selected photo id=%s by %s", photo.get("id"), photo.get("user", {}).get("name"))
    notify_download(photo, unsplash_access_key)

    logger.info("Downloading image constrained to %sx%s", image_width, image_height)
    image = download_constrained_image(photo, image_width, image_height)

    logger.info("Dithering to Spectra E6 six-colour palette")
    dithered = dither_to_spectra_e6(image)

    photographer = photo.get("user", {}).get("name")
    if photographer:
        logger.info("Overlaying attribution for %s", photographer)
        dithered = snap_to_spectra_e6(add_attribution(dithered, photographer))

    logger.info("Uploading to gs://%s/%s", gcs_bucket, object_name)
    public_url = upload_png(gcs_bucket, object_name, dithered)
    logger.info("Public URL: %s", public_url)

    if archive_objects:
        archive_name = f"archive/{datetime.now(timezone.utc):%Y-%m-%d}.png"
        upload_png(gcs_bucket, archive_name, dithered)
        logger.info("Archived copy at gs://%s/%s", gcs_bucket, archive_name)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("daily_image job failed")
        sys.exit(1)
