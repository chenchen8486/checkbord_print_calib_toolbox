import math
from typing import TYPE_CHECKING

import cv2
import numpy as np

from checkbord_print_calib_toolbox.common import logger
from checkbord_print_calib_toolbox.common.image_io import to_gray8

if TYPE_CHECKING:
    from checkbord_print_calib_toolbox.calibration.calibrator import CalibrationResult


class RectifierError(Exception):
    pass


class Rectifier:
    def __init__(self, calib: "CalibrationResult", target_mm_per_px: float) -> None:
        if not math.isfinite(target_mm_per_px) or target_mm_per_px <= 0:
            raise RectifierError(f"目标像素当量必须为正数，实际: {target_mm_per_px}")
        self.calib = calib
        self.mm_per_px = float(target_mm_per_px)
        self.width, self.height = calib.image_size
        self.cx = (self.width - 1) / 2.0
        self.cy = (self.height - 1) / 2.0
        self.center_x_mm, self.center_y_mm = self._plane_intersect(self.cx, self.cy)
        self.sign_x = 1.0
        self.sign_y = 1.0
        self._build_maps()

    def _plane_intersect(self, x: float, y: float) -> tuple[float, float]:
        try:
            normalized = cv2.undistortPoints(
                np.array([[[x, y]]], dtype=np.float64),
                self.calib.camera_matrix,
                self.calib.dist_coeffs,
            )
            rotation, _ = cv2.Rodrigues(self.calib.rvec)
        except cv2.error as exc:
            raise RectifierError(f"去畸变归一化失败: {exc}") from exc
        rt = rotation.T
        ray = np.array([normalized[0, 0, 0], normalized[0, 0, 1], 1.0], dtype=np.float64)
        a = rt @ ray
        b = -(rt @ self.calib.tvec.reshape(3))
        if abs(a[2]) < 1e-12:
            raise RectifierError("视线方向与板面近似平行，无法求交（标定外参异常）")
        point = (-b[2] / a[2]) * a + b
        return float(point[0]), float(point[1])

    def _project_board(self, points: np.ndarray) -> np.ndarray:
        projected, _ = cv2.projectPoints(
            points,
            self.calib.rvec,
            self.calib.tvec,
            self.calib.camera_matrix,
            self.calib.dist_coeffs,
        )
        return projected.reshape(-1, 2)

    def _build_maps(self) -> None:
        try:
            projected = self._project_board(np.array([
                [self.center_x_mm, self.center_y_mm, 0.0],
                [self.center_x_mm + 1.0, self.center_y_mm, 0.0],
                [self.center_x_mm, self.center_y_mm + 1.0, 0.0],
            ], dtype=np.float64))
        except cv2.error as exc:
            raise RectifierError(f"方向符号投影计算失败: {exc}") from exc
        delta_x = projected[1] - projected[0]
        delta_y = projected[2] - projected[0]
        self.sign_x = 1.0 if delta_x[0] >= 0 else -1.0
        self.sign_y = 1.0 if delta_y[1] >= 0 else -1.0
        if abs(delta_x[1]) > abs(delta_x[0]):
            logger.warn(
                "板面 X 轴在图像中更接近竖直方向，相机可能旋转了约 90°，"
                "标定照常进行，但请确认安装方向"
            )
        self.map_x = np.empty((self.height, self.width), dtype=np.float32)
        self.map_y = np.empty((self.height, self.width), dtype=np.float32)
        u = np.arange(self.width, dtype=np.float64)
        x = self.center_x_mm + self.sign_x * (u - self.cx) * self.mm_per_px
        try:
            for y0 in range(0, self.height, 256):
                rows = min(256, self.height - y0)
                v = np.arange(y0, y0 + rows, dtype=np.float64)
                y = self.center_y_mm + self.sign_y * (v - self.cy) * self.mm_per_px
                points = np.empty((rows * self.width, 3), dtype=np.float64)
                points[:, 0] = np.tile(x, rows)
                points[:, 1] = np.repeat(y, self.width)
                points[:, 2] = 0.0
                projected = self._project_board(points).reshape(rows, self.width, 2)
                self.map_x[y0:y0 + rows] = projected[:, :, 0].astype(np.float32)
                self.map_y[y0:y0 + rows] = projected[:, :, 1].astype(np.float32)
        except (cv2.error, MemoryError) as exc:
            raise RectifierError(f"正射映射表构建失败: {exc}") from exc
        logger.info(
            f"正射映射表已生成: {self.width}x{self.height}, "
            f"1px={self.mm_per_px:.4f}mm, 中心锚点 "
            f"({self.center_x_mm:.1f}, {self.center_y_mm:.1f})mm"
        )

    def rectify(self, image: np.ndarray) -> np.ndarray | None:
        if not isinstance(image, np.ndarray) or image.size == 0:
            logger.error("正射矫正输入为空图")
            return None
        if image.shape[1] != self.width or image.shape[0] != self.height:
            logger.error(
                f"图像尺寸 ({image.shape[1]}, {image.shape[0]}) 与标定尺寸 "
                f"({self.width}, {self.height}) 不一致，请用同机位同分辨率采图标定"
            )
            return None
        gray = image
        if image.ndim == 3 and image.shape[2] != 1:
            logger.warn("正射矫正输入非单通道，已自动转灰度")
            gray = to_gray8(image)
        if gray is None or gray.dtype != np.uint8:
            logger.error("正射矫正仅支持 8 位图像")
            return None
        try:
            return cv2.remap(
                gray, self.map_x, self.map_y, cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT, borderValue=0,
            )
        except cv2.error as exc:
            logger.error(f"正射矫正失败: {exc}")
            return None

    def board_mm_to_px(self, x_mm, y_mm):
        u = self.cx + self.sign_x * (np.asarray(x_mm) - self.center_x_mm) / self.mm_per_px
        v = self.cy + self.sign_y * (np.asarray(y_mm) - self.center_y_mm) / self.mm_per_px
        return u, v
