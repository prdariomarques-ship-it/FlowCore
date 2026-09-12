"""Advisor profile photo normalization.

api/dashboard_routes.py's AdvisorProfileUpdate originally shipped with no
photo field at all -- see its own docstring: generating a realistic photo
of the app's real named user would fabricate a likeness of a real person,
a different and more serious problem than the demo clients' fictitious
names. This module exists for the case that docstring explicitly left
open: an advisor uploading a real photo of themselves. It never generates
or alters a face -- it only re-encodes whatever real image bytes were
uploaded into one predictable shape (a square JPEG capped at a sane
size), the same way an avatar-upload flow works on any real product.
"""
from __future__ import annotations

import base64
import binascii
import io
import re

from PIL import Image, UnidentifiedImageError

_DATA_URI_RE = re.compile(r"^data:image/(png|jpe?g|webp);base64,(.*)$", re.IGNORECASE | re.DOTALL)

# 8MB raw upload ceiling before decoding -- a phone camera photo comfortably
# fits; this only exists to reject something absurd, not to be a tight budget.
_MAX_DECODED_BYTES = 8 * 1024 * 1024

# Square, matches the largest avatar actually rendered (the advisor card,
# 56px) with real headroom for high-DPI screens -- bigger than that just
# inflates the stored JSON for no visible gain.
_TARGET_SIZE = 320


def normalize_advisor_photo(data_uri: str) -> str:
    """Validates, center-crops to a square, resizes to _TARGET_SIZE and
    re-encodes as JPEG. Raises ValueError (safe to surface to the caller
    as-is) on anything that isn't a real, reasonably-sized image."""
    match = _DATA_URI_RE.match(data_uri.strip())
    if not match:
        raise ValueError("Formato inválido — envie uma imagem PNG, JPEG ou WEBP como data URI.")
    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Não foi possível decodificar a imagem enviada.")
    if not raw:
        raise ValueError("Imagem vazia.")
    if len(raw) > _MAX_DECODED_BYTES:
        raise ValueError(f"Imagem muito grande (máx. {_MAX_DECODED_BYTES // (1024 * 1024)}MB).")
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except UnidentifiedImageError:
        raise ValueError("Arquivo não reconhecido como imagem válida.")

    image = image.convert("RGB")
    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    image = image.crop((left, top, left + side, top + side)).resize(
        (_TARGET_SIZE, _TARGET_SIZE), Image.LANCZOS
    )

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"
