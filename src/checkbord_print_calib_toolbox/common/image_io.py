import os
from pathlib import Path
import struct

import cv2
import numpy as np

from checkbord_print_calib_toolbox.common import logger


EXTENSIONS = {".bmp", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


class ImageIoError(Exception):
    pass


def list_images(directory: str | os.PathLike[str]) -> list[str]:
    root = Path(directory).absolute()
    try:
        if not root.is_dir():
            raise ImageIoError(f"标定采图目录不存在或不可访问: {root}")
        paths = []
        for entry in root.iterdir():
            if not entry.is_file() or entry.suffix.lower() not in EXTENSIONS:
                continue
            stem = entry.stem
            if "demo" in stem.lower() or "副本" in stem:
                continue
            paths.append(str(entry.absolute()))
    except ImageIoError:
        raise
    except OSError as exc:
        raise ImageIoError(f"标定采图目录不存在或不可访问: {root}") from exc
    paths.sort()
    logger.info(f"输入目录 {root} 共发现 {len(paths)} 张图像")
    return paths


def _decode_bmp_manual(path: Path) -> np.ndarray | None:
    try:
        data = path.read_bytes()
        if len(data) < 54 or data[:2] != b"BM":
            return None
        data_offset = struct.unpack_from("<I", data, 10)[0]
        width, raw_height = struct.unpack_from("<ii", data, 18)
        planes, bit_count = struct.unpack_from("<HH", data, 26)
        compression = struct.unpack_from("<I", data, 30)[0]
        if planes != 1 or bit_count not in {24, 32} or compression not in {0, 3}:
            return None
        if width <= 0 or raw_height == 0:
            return None
        top_down = raw_height < 0
        height = -raw_height if top_down else raw_height
        channels = bit_count // 8
        stride = (width * channels + 3) & ~3
        required = stride * height
        if data_offset > len(data) or required > len(data) - data_offset:
            return None
        image = np.empty((height, width, channels), dtype=np.uint8)
        row_bytes = width * channels
        for y in range(height):
            source_row = y if top_down else height - 1 - y
            start = data_offset + source_row * stride
            image[y] = np.frombuffer(data[start:start + row_bytes], dtype=np.uint8).reshape(
                width, channels
            )
        logger.debug(f"手工 BMP 解码成功: {path} ({width}x{height}, {bit_count}bit)")
        return image
    except (OSError, ValueError, struct.error) as exc:
        logger.error(f"手工 BMP 解码异常: {path}，原因: {exc}")
        return None


def read_image(path: str | os.PathLike[str]) -> np.ndarray | None:
    image_path = Path(path)
    image = None
    try:
        image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    except cv2.error as exc:
        logger.warn(f"cv2.imread 异常，尝试手工 BMP 解码: {image_path}，原因: {exc}")
    if image is not None and image.size:
        return image
    image = _decode_bmp_manual(image_path)
    if image is None:
        logger.error(f"图像读取失败（OpenCV 与手工解码均失败）: {image_path}")
    return image


def to_gray8(image) -> np.ndarray | None:
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.size == 0:
        return None
    if image.ndim == 2 or (image.ndim == 3 and image.shape[2] == 1):
        return image
    try:
        if image.ndim == 3 and image.shape[2] == 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if image.ndim == 3 and image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    except cv2.error as exc:
        logger.error(f"图像灰度转换异常，原因: {exc}")
    return None


def save_image(path: str | os.PathLike[str], image: np.ndarray) -> bool:
    if not isinstance(image, np.ndarray) or image.size == 0:
        logger.error(f"图像保存失败，输入为空: {path}")
        return False
    try:
        if cv2.imwrite(str(path), image):
            return True
        logger.warn(f"cv2.imwrite 返回失败: {path}")
    except (cv2.error, OSError) as exc:
        logger.warn(f"cv2.imwrite 异常: {path}，原因: {exc}")
    logger.error(f"图像保存失败: {path}")
    return False
