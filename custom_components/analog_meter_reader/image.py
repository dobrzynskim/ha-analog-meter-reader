"""Przetwarzanie obrazu (Pillow, synchroniczne - uruchamiane przez
hass.async_add_executor_job): odbicie lustrzane, przycięcie do ROI z cyframi,
powiększenie pod OCR, podgląd jako data URI (kalibracja w config_flow)."""
from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image


class InvalidCropBox(Exception):
    """Ramka przycięcia jest pusta albo wykracza poza granice zdjęcia."""


def load_and_orient(raw_bytes: bytes, flip_horizontal: bool) -> Image.Image:
    """Dekoduje zdjęcie z kamery; część kamer montowanych przy liczniku daje
    obraz lustrzany - stąd opcjonalne odbicie.

    UWAGA: flip_horizontal jest celowo pozycyjny (nie keyword-only) - funkcja
    jest wywoływana przez hass.async_add_executor_job(func, *args), który nie
    przekazuje kwargs. Keyword-only tutaj wywalało się w praniu (TypeError:
    takes 1 positional argument but 2 were given) w config_flow i coordinatorze.
    """
    image = Image.open(BytesIO(raw_bytes)).convert("RGB")
    if flip_horizontal:
        image = image.transpose(Image.FLIP_LEFT_RIGHT)
    return image


def crop_for_ocr(image: Image.Image, box: tuple[int, int, int, int], scale: int = 4) -> Image.Image:
    """box = (left, top, right, bottom) w pikselach już zorientowanego zdjęcia.

    Podnosi InvalidCropBox zamiast po cichu zwracać puste/ucięte zdjęcie -
    PIL.Image.crop() samo w sobie nie waliduje granic (dopełnia czarnym poza
    oryginałem), co przy błędnej kalibracji dawałoby mylący podgląd zamiast
    czytelnego błędu.
    """
    left, top, right, bottom = box
    if right <= left or bottom <= top:
        raise InvalidCropBox(f"Pusta lub odwrócona ramka: {box}")
    if left < 0 or top < 0 or right > image.width or bottom > image.height:
        raise InvalidCropBox(
            f"Ramka {box} wykracza poza zdjęcie {image.width}x{image.height}"
        )
    crop = image.crop(box)
    if scale != 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    return crop


def to_jpeg_bytes(image: Image.Image, quality: int = 95) -> bytes:
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def to_data_uri(image: Image.Image, quality: int = 85) -> str:
    """Data URI do osadzenia jako podgląd (markdown ![]()) w krokach config_flow."""
    encoded = base64.b64encode(to_jpeg_bytes(image, quality=quality)).decode()
    return f"data:image/jpeg;base64,{encoded}"
