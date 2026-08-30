from io import BytesIO

from PIL import Image

from image import crop_for_ocr, load_and_orient, to_jpeg_bytes


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
