import struct

import cv2
import numpy as np
import pytest

from checkbord_print_calib_toolbox.common.image_io import (
    ImageIoError,
    list_images,
    read_image,
    to_gray8,
)


def test_list_images_filters_skips_and_sorts(tmp_path):
    for name in ("b.JPG", "A.PNG", "z.tiff", "demo2.bmp", "myDEMO.tif", "图副本.png", "note.txt"):
        (tmp_path / name).write_bytes(b"")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "inside.bmp").write_bytes(b"")

    paths = list_images(tmp_path)

    assert [path.rsplit("\\", 1)[-1] for path in paths] == ["A.PNG", "b.JPG", "z.tiff"]


def test_list_images_rejects_missing_directory(tmp_path):
    with pytest.raises(ImageIoError) as exc:
        list_images(tmp_path / "missing")
    assert str(exc.value) == f"标定采图目录不存在或不可访问: {(tmp_path / 'missing').absolute()}"


def test_gray_conversion_accepts_only_8uc1_8uc3_8uc4():
    gray = np.full((2, 3), 17, np.uint8)
    bgr = np.zeros((2, 3, 3), np.uint8)
    bgr[:] = (10, 20, 30)
    bgra = np.dstack((bgr, np.full((2, 3), 255, np.uint8)))

    assert to_gray8(gray) is gray
    assert np.array_equal(to_gray8(bgr), cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
    assert np.array_equal(to_gray8(bgra), cv2.cvtColor(bgra, cv2.COLOR_BGRA2GRAY))
    assert to_gray8(np.zeros((2, 3), np.float32)) is None
    assert to_gray8(np.empty((0, 0), np.uint8)) is None


def _write_bmp(path, pixels, bit_count, top_down=False, compression=0):
    height = len(pixels)
    width = len(pixels[0])
    channels = bit_count // 8
    stride = (width * channels + 3) & ~3
    rows = pixels if top_down else list(reversed(pixels))
    body = bytearray()
    for row in rows:
        for pixel in row:
            body.extend(pixel)
        body.extend(b"\0" * (stride - width * channels))
    signed_height = -height if top_down else height
    header = b"BM" + struct.pack("<IHHI", 54 + len(body), 0, 0, 54)
    header += struct.pack(
        "<IiiHHIIiiII", 40, width, signed_height, 1, bit_count,
        compression, len(body), 0, 0, 0, 0,
    )
    path.write_bytes(header + body)


@pytest.mark.parametrize(
    ("bit_count", "top_down", "compression", "pixel"),
    [
        (24, False, 0, (1, 2, 3)),
        (32, True, 3, (1, 2, 3, 4)),
    ],
)
def test_manual_bmp_fallback_formats_and_orientation(
    tmp_path, monkeypatch, bit_count, top_down, compression, pixel
):
    path = tmp_path / "manual.bmp"
    empty = (0,) * (bit_count // 8)
    _write_bmp(path, [[pixel, empty], [empty, empty]], bit_count, top_down, compression)
    monkeypatch.setattr(cv2, "imread", lambda *args: None)

    image = read_image(path)

    assert image.shape == (2, 2, bit_count // 8)
    assert tuple(image[0, 0]) == pixel
    assert not image[1, 0].any()


def test_read_failure_is_distinct_from_unsupported_array(tmp_path):
    path = tmp_path / "broken.bmp"
    path.write_bytes(b"not a bitmap")
    assert read_image(path) is None
