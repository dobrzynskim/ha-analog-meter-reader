"""Przetwarzanie obrazu (Pillow, synchroniczne - uruchamiane przez
hass.async_add_executor_job): odbicie lustrzane, przycięcie do ROI z cyframi,
powiększenie pod OCR."""
from __future__ import annotations

from io import BytesIO

from PIL import Image


def load_and_orient(raw_bytes: bytes, *, flip_horizontal: bool) -> Image.Image:
    """Dekoduje zdjęcie z kamery; część kamer montowanych przy liczniku daje
    obraz lustrzany - stąd opcjonalne odbicie."""
    image = Image.open(BytesIO(raw_bytes)).convert("RGB")
    if flip_horizontal:
        image = image.transpose(Image.FLIP_LEFT_RIGHT)
    return image


def crop_for_ocr(image: Image.Image, box: tuple[int, int, int, int], scale: int = 4) -> Image.Image:
    """box = (left, top, right, bottom) w pikselach już zorientowanego zdjęcia."""
    crop = image.crop(box)
    if scale != 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    return crop


def to_jpeg_bytes(image: Image.Image, quality: int = 95) -> bytes:
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()
