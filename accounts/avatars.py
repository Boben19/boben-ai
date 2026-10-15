"""Validates an uploaded picture and shrinks it to a small square JPEG."""
import io

from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


class AvatarError(ValueError):
    pass


def process_avatar(uploaded_file):
    """Returns JPEG bytes (square, AVATAR_SIZE px). Raises AvatarError with a friendly message."""
    if uploaded_file.size > settings.AVATAR_MAX_UPLOAD_BYTES:
        raise AvatarError("That picture is too large. Please use one under %d MB." % (settings.AVATAR_MAX_UPLOAD_BYTES // (1024 * 1024)))
    try:
        img = Image.open(uploaded_file)
        if img.format not in ALLOWED_FORMATS:
            raise AvatarError("Please upload a JPG, PNG, WebP or GIF picture.")
        img.load()                                         # fully decode, so broken files fail here
    except AvatarError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise AvatarError("That file doesn't look like a valid picture.")

    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.getchannel("A"))
        img = background
    else:
        img = img.convert("RGB")
    img = ImageOps.fit(img, (settings.AVATAR_SIZE, settings.AVATAR_SIZE), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=86, optimize=True)   # always re-encoded: nothing the user uploaded is served as-is
    return out.getvalue()
