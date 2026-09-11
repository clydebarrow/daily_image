"""Upload a Pillow image to Google Cloud Storage as a PNG."""

import io

from google.cloud import storage
from PIL import Image


def upload_png(
    bucket_name: str,
    object_name: str,
    image: Image.Image,
) -> str:
    """Save `image` as a PNG and upload it to gs://bucket_name/object_name.

    PNG is lossless, so the dithered image's exact 6 palette colours survive
    upload untouched -- unlike JPEG, which introduces chroma-subsampling
    bleed at colour edges and can't cleanly represent the dithering noise.
    Saving a palette ('P' mode) image keeps the file small despite that
    noise, since PNG only needs to store 1-of-6 indices per pixel.

    Returns the blob's public URL. The bucket itself must already grant
    public read (uniform bucket-level access + an allUsers objectViewer IAM
    binding) -- see README.md -- since object-level ACLs require the bucket
    to use fine-grained access, which is not the recommended configuration.
    """
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    buf.seek(0)

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    # The object changes at most once a day (or on an ad-hoc manual run), so
    # force every fetch to revalidate against GCS's ETag rather than risk
    # serving a stale image out of a browser/CDN cache for up to max-age.
    # must-revalidate keeps this cheap: unchanged fetches get a 304, not a
    # full re-download.
    blob.cache_control = "no-cache, must-revalidate"
    blob.upload_from_file(buf, content_type="image/png")
    return blob.public_url
