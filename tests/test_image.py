from io import BytesIO

import pytest
from PIL import Image

from image import InvalidCropBox, crop_for_ocr, load_and_orient, to_data_uri, to_jpeg_bytes


def _make_test_image_bytes(width=20, height=10) -> bytes:
    # Lewa polowa czarna, prawa polowa biala - wystarczy zeby wykryc, czy
    # odbicie lustrzane faktycznie zamienilo strony.
    im = Image.new("RGB", (width, height), "white")
    for x in range(width // 2):
        for y in range(height):
            im.putpixel((x, y), (0, 0, 0))
    buf = BytesIO()
    im.save(buf, format="JPEG")
    return buf.getvalue()


def test_load_and_orient_without_flip_keeps_left_side_black():
    image = load_and_orient(_make_test_image_bytes(), flip_horizontal=False)
    assert image.getpixel((0, 0)) == (0, 0, 0)
    assert image.getpixel((19, 0)) == (255, 255, 255)


def test_load_and_orient_with_flip_swaps_sides():
    image = load_and_orient(_make_test_image_bytes(), flip_horizontal=True)
    assert image.getpixel((0, 0)) == (255, 255, 255)
    assert image.getpixel((19, 0)) == (0, 0, 0)


def test_load_and_orient_accepts_positional_flip_arg():
    """Regresja: hass.async_add_executor_job(func, *args) przekazuje tylko
    argumenty pozycyjne - jeśli flip_horizontal byłby keyword-only, wywołanie
    z config_flow/coordinator wywala się z TypeError (widziane na żywo)."""
    image = load_and_orient(_make_test_image_bytes(), True)
    assert image.getpixel((0, 0)) == (255, 255, 255)


def test_crop_for_ocr_scales_by_factor():
    image = load_and_orient(_make_test_image_bytes(width=40, height=20), flip_horizontal=False)
    crop = crop_for_ocr(image, box=(0, 0, 10, 10), scale=4)
    assert crop.size == (40, 40)


def test_crop_for_ocr_scale_one_keeps_original_size():
    image = load_and_orient(_make_test_image_bytes(width=40, height=20), flip_horizontal=False)
    crop = crop_for_ocr(image, box=(0, 0, 10, 10), scale=1)
    assert crop.size == (10, 10)


def test_to_jpeg_bytes_round_trips():
    image = load_and_orient(_make_test_image_bytes(), flip_horizontal=False)
    data = to_jpeg_bytes(image)
    decoded = Image.open(BytesIO(data))
    assert decoded.size == image.size


def test_crop_for_ocr_rejects_box_beyond_image_bounds():
    image = load_and_orient(_make_test_image_bytes(width=40, height=20), flip_horizontal=False)
    with pytest.raises(InvalidCropBox):
        crop_for_ocr(image, box=(0, 0, 41, 20))


def test_crop_for_ocr_rejects_negative_origin():
    image = load_and_orient(_make_test_image_bytes(width=40, height=20), flip_horizontal=False)
    with pytest.raises(InvalidCropBox):
        crop_for_ocr(image, box=(-1, 0, 10, 10))


def test_crop_for_ocr_rejects_empty_or_inverted_box():
    image = load_and_orient(_make_test_image_bytes(width=40, height=20), flip_horizontal=False)
    with pytest.raises(InvalidCropBox):
        crop_for_ocr(image, box=(10, 10, 10, 10))
    with pytest.raises(InvalidCropBox):
        crop_for_ocr(image, box=(20, 10, 5, 15))


def test_to_data_uri_has_jpeg_prefix_and_decodes_back():
    import base64

    image = load_and_orient(_make_test_image_bytes(), flip_horizontal=False)
    uri = to_data_uri(image)

    assert uri.startswith("data:image/jpeg;base64,")
    decoded_bytes = base64.b64decode(uri.split(",", 1)[1])
    decoded = Image.open(BytesIO(decoded_bytes))
    assert decoded.size == image.size
