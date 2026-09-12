"""Tests for runtime/advisor_photo.py — normalizes a REAL uploaded photo
into a predictable square JPEG. Never generates or alters a face; see
the module's own docstring for why that distinction is the whole point.
"""

from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

Image = pytest.importorskip("PIL.Image")

from runtime.advisor_photo import normalize_advisor_photo  # noqa: E402


def _data_uri(size=(200, 300), fmt="PNG", color=(120, 40, 200)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    mime = {"PNG": "png", "JPEG": "jpeg", "WEBP": "webp"}[fmt]
    return f"data:image/{mime};base64,{encoded}"


def _decode(data_uri: str) -> "Image.Image":
    header, encoded = data_uri.split(",", 1)
    return Image.open(io.BytesIO(base64.b64decode(encoded)))


class TestNormalizeAdvisorPhoto:
    def test_accepts_png_and_returns_a_jpeg_data_uri(self):
        result = normalize_advisor_photo(_data_uri(fmt="PNG"))
        assert result.startswith("data:image/jpeg;base64,")

    def test_accepts_jpeg(self):
        result = normalize_advisor_photo(_data_uri(fmt="JPEG"))
        assert result.startswith("data:image/jpeg;base64,")

    def test_accepts_webp(self):
        result = normalize_advisor_photo(_data_uri(fmt="WEBP"))
        assert result.startswith("data:image/jpeg;base64,")

    def test_result_is_a_square_at_the_target_size(self):
        result = normalize_advisor_photo(_data_uri(size=(600, 900)))
        image = _decode(result)
        assert image.size == (320, 320)

    def test_a_landscape_photo_is_center_cropped_not_squashed(self):
        # A wide image with distinct left/right colors -- if it were
        # squashed instead of center-cropped, the resulting square would
        # still show both colors; center-cropping keeps only the middle.
        buffer = io.BytesIO()
        wide = Image.new("RGB", (400, 200))
        for x in range(400):
            for y in range(200):
                wide.putpixel((x, y), (255, 0, 0) if x < 200 else (0, 0, 255))
        wide.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        result = normalize_advisor_photo(f"data:image/png;base64,{encoded}")
        image = _decode(result).convert("RGB")
        # center crop of a 400x200 image keeps x in [100, 300) -- pure red
        # and pure blue both appear in that band, so the exact center
        # column sits right at the seam. Sample near, not at, the edges.
        left_pixel = image.getpixel((20, 160))
        right_pixel = image.getpixel((300, 160))
        assert left_pixel != right_pixel  # both halves of the crop survived

    def test_rejects_non_data_uri_strings(self):
        with pytest.raises(ValueError, match="Formato inválido"):
            normalize_advisor_photo("not-a-data-uri")

    def test_rejects_unsupported_mime_type(self):
        with pytest.raises(ValueError, match="Formato inválido"):
            normalize_advisor_photo("data:image/gif;base64,R0lGODlhAQABAAAAACw=")

    def test_rejects_invalid_base64(self):
        with pytest.raises(ValueError, match="decodificar"):
            normalize_advisor_photo("data:image/png;base64,not-valid-base64!!!")

    def test_rejects_a_data_uri_that_isnt_actually_an_image(self):
        encoded = base64.b64encode(b"not an image, just text").decode("ascii")
        with pytest.raises(ValueError, match="não reconhecido"):
            normalize_advisor_photo(f"data:image/png;base64,{encoded}")

    def test_rejects_an_oversized_payload(self):
        from runtime.advisor_photo import _MAX_DECODED_BYTES

        huge = base64.b64encode(b"0" * (_MAX_DECODED_BYTES + 1)).decode("ascii")
        with pytest.raises(ValueError, match="muito grande"):
            normalize_advisor_photo(f"data:image/png;base64,{huge}")

    def test_rejects_empty_payload(self):
        with pytest.raises(ValueError, match="vazia"):
            normalize_advisor_photo("data:image/png;base64,")
