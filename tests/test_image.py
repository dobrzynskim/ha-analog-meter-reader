from io import BytesIO

import pytest
from PIL import Image

from image import (
    BOX_COLOR,
    GRID_COLOR,
    InvalidCropBox,
    crop_for_ocr,
    draw_calibration_overlay,
    draw_timestamp,
    load_and_orient,
    to_data_uri,
    to_jpeg_bytes,
)


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


def _solid_image(width=100, height=100, color=(255, 255, 255)) -> Image.Image:
    return Image.new("RGB", (width, height), color)


def test_draw_calibration_overlay_does_not_mutate_original():
    image = _solid_image()
    original_pixel = image.getpixel((25, 25))

    draw_calibration_overlay(image, box=None, grid_step=50)

    assert image.getpixel((25, 25)) == original_pixel


def test_draw_calibration_overlay_draws_grid_line_at_origin():
    image = _solid_image()
    overlay = draw_calibration_overlay(image, box=None, grid_step=50)
    # Linia pionowa x=0 na całej wysokosci - punkt z dala od etykiet tekstowych.
    assert overlay.getpixel((0, 80)) == GRID_COLOR


def test_draw_calibration_overlay_leaves_area_between_gridlines_untouched():
    image = _solid_image()
    overlay = draw_calibration_overlay(image, box=None, grid_step=50)
    # Punkt w połowie odstępu między liniami siatki (x=25,y=25) - poza zasięgiem
    # etykiet (rysowanych tuż przy liniach) i poza samymi liniami.
    assert overlay.getpixel((25, 25)) == (255, 255, 255)


def test_draw_calibration_overlay_draws_box_outline():
    image = _solid_image()
    overlay = draw_calibration_overlay(image, box=(10, 10, 40, 40), grid_step=50)
    # Środek górnej krawędzi ramki (x=25, y=10) powinien być czerwony.
    assert overlay.getpixel((25, 10)) == BOX_COLOR
    # Środek ramki na pewno poza obrysem - kolor tła bez zmian.
    assert overlay.getpixel((25, 25)) == (255, 255, 255)


def test_draw_timestamp_does_not_mutate_original():
    image = _solid_image(width=300, height=150)
    original_pixel = image.getpixel((10, 10))

    draw_timestamp(image, "2026-08-31 14:09:27")

    assert image.getpixel((10, 10)) == original_pixel


def test_draw_timestamp_draws_dark_box_in_bottom_right_corner():
    image = _solid_image(width=300, height=150, color=(255, 255, 255))
    stamped = draw_timestamp(image, "2026-08-31 14:09:27")
    # Tuż przy prawym dolnym rogu, ale w obrębie marginesu (6px) - w obrębie
    # czarnego tła znacznika, nie za jego krawędzią.
    assert stamped.getpixel((293, 143)) == (0, 0, 0)


def test_draw_timestamp_leaves_top_left_untouched():
    image = _solid_image(width=300, height=150, color=(255, 255, 255))
    stamped = draw_timestamp(image, "2026-08-31 14:09:27")
    assert stamped.getpixel((5, 5)) == (255, 255, 255)
