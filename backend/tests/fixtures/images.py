"""Deterministic in-memory image fixtures for offline screenshot tests."""

from __future__ import annotations

from io import BytesIO
from typing import Final

from PIL import Image, ImageFilter


def _encoded_image(
    image_format: str,
    *,
    blurred: bool = False,
) -> bytes:
    image = Image.new("RGB", (24, 16), color=(42, 124, 180))
    if blurred:
        for x in range(image.width):
            for y in range(image.height):
                color = (245, 245, 245) if (x // 3 + y // 3) % 2 else (10, 10, 10)
                image.putpixel((x, y), color)
        image = image.filter(ImageFilter.GaussianBlur(radius=8))
    output = BytesIO()
    image.save(output, format=image_format, quality=90)
    return output.getvalue()


JPEG_SCREENSHOT: Final = _encoded_image("JPEG")
PNG_SCREENSHOT: Final = _encoded_image("PNG")
WEBP_SCREENSHOT: Final = _encoded_image("WEBP")
BLURRED_PNG_SCREENSHOT: Final = _encoded_image("PNG", blurred=True)


__all__ = [
    "BLURRED_PNG_SCREENSHOT",
    "JPEG_SCREENSHOT",
    "PNG_SCREENSHOT",
    "WEBP_SCREENSHOT",
]
