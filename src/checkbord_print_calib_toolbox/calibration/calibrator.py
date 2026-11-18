from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path

import cv2
import numpy as np

from checkbord_print_calib_toolbox.calibration.rectifier import Rectifier, RectifierError
from checkbord_print_calib_toolbox.common import logger
from checkbord_print_calib_toolbox.common.image_io import save_image, to_gray8
from checkbord_print_calib_toolbox.config.ini import AppConfig, CalibrateConfig


@dataclass
class CalibReport:
    rms: float = 0.0
    verify_mean_px: float = 0.0
    verify_p95_px: float = 0.0
    xml_path: str = ""

    def __post_init__(self) -> None:
        self._solved = False
        self._xml_written = False

    def _reset(self) -> None:
        self.rms = 0.0
        self.verify_mean_px = 0.0
        self.verify_p95_px = 0.0
        self.xml_path = ""
        self._solved = False
        self._xml_written = False


@dataclass
class CalibrationResult:
    camera_matrix: np.ndarray
    dist_coeffs: np.ndarray
    rvec: np.ndarray
    tvec: np.ndarray
    image_size: tuple[int, int]
    square_x_mm: float
    square_y_mm: float
    pattern_size: tuple[int, int]
    rms: float
    mm_per_px: float
    created: str = ""


class CalibrationError(Exception):
    pass


def _build_object_grid(cfg: CalibrateConfig) -> np.ndarray:
    grid = np.zeros((cfg.pattern_cols * cfg.pattern_rows, 3), dtype=np.float32)
    index = 0
    for row in range(cfg.pattern_rows):
        for col in range(cfg.pattern_cols):
            grid[index] = (col * cfg.square_x_mm, row * cfg.square_y_mm, 0.0)
            index += 1
    return grid


def _mean_corners(corners_list: list[np.ndarray]) -> np.ndarray:
    mean = np.zeros_like(corners_list[0], dtype=np.float32)
    for corners in corners_list:
        mean += corners.reshape(-1, 2).astype(np.float32)
    mean *= np.float32(1.0 / len(corners_list))
    return mean


def detect_board_corners(image: np.ndarray, pattern_cols: int, pattern_rows: int) -> np.ndarray:
    if pattern_cols <= 0 or pattern_rows <= 0:
        raise CalibrationError(f"内角点配置非法: {pattern_cols}x{pattern_rows}")
    gray = to_gray8(image)
    if gray is None:
        raise CalibrationError("棋盘格图像格式不支持（须为 8UC1/8UC3/8UC4）")
    try:
        found, corners = cv2.findChessboardCornersSB(
            gray, (pattern_cols, pattern_rows), flags=cv2.CALIB_CB_NORMALIZE_IMAGE
        )
    except cv2.error as exc:
        raise CalibrationError(f"棋盘格检测异常: {exc}") from exc
    expected = pattern_cols * pattern_rows
    count = 0 if corners is None else int(corners.reshape(-1, 2).shape[0])
    if not found or count != expected:
        raise CalibrationError(
            f"未检测到完整棋盘格（目标 {pattern_cols}x{pattern_rows}={expected} 个内角点），"
            "请检查标定板摆放与成像"
        )
    corners = corners.reshape(-1, 1, 2).astype(np.float32, copy=False)
    try:
        corners = cv2.cornerSubPix(
            gray,
            corners,
            winSize=(21, 21),
            zeroZone=(-1, -1),
            criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.01),
        )
    except cv2.error as exc:
        raise CalibrationError(f"角点亚像素细化异常: {exc}") from exc
    logger.info(f"棋盘格角点检测成功: {expected} 个")
    return corners.reshape(-1, 2)


def _save_calibration_xml(path: str, calib: CalibrationResult) -> None:
    output = Path(path)
    parent = output.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CalibrationError(f"创建标定输出目录失败: {parent}，{exc}") from exc
    fs = None
    try:
        fs = cv2.FileStorage(str(output), cv2.FILE_STORAGE_WRITE)
        if not fs.isOpened():
            raise CalibrationError(f"标定文件无法写入: {output}")
        fs.write("camera_matrix", calib.camera_matrix)
        fs.write("dist_coeffs", calib.dist_coeffs)
        fs.write("rvec", calib.rvec)
        fs.write("tvec", calib.tvec)
        fs.write("image_width", calib.image_size[0])
        fs.write("image_height", calib.image_size[1])
        fs.write("square_x_mm", calib.square_x_mm)
        fs.write("square_y_mm", calib.square_y_mm)
        fs.write("pattern_cols", calib.pattern_size[0])
        fs.write("pattern_rows", calib.pattern_size[1])
        fs.write("rms", calib.rms)
        fs.write("mm_per_px", calib.mm_per_px)
        fs.write("created", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    except CalibrationError:
        raise
    except Exception as exc:
        raise CalibrationError(f"标定文件写入异常: {output}，{exc}") from exc
    finally:
        if fs is not None:
            fs.release()
    logger.info(f"标定参数已保存: {output}")


def _read_node(fs, name: str):
    node = fs.getNode(name)
    if node.empty():
        raise CalibrationError(f"字段缺失: {name}")
    return node


def load_calibration_xml(path: str) -> CalibrationResult:
    fs = None
    try:
        fs = cv2.FileStorage(str(path), cv2.FILE_STORAGE_READ)
        if not fs.isOpened():
            raise CalibrationError(f"标定文件不存在或无法打开: {path}")
        camera_matrix = _read_node(fs, "camera_matrix").mat()
        dist_coeffs = _read_node(fs, "dist_coeffs").mat()
        rvec = _read_node(fs, "rvec").mat()
        tvec = _read_node(fs, "tvec").mat()
        width = int(_read_node(fs, "image_width").real())
        height = int(_read_node(fs, "image_height").real())
        square_x = float(_read_node(fs, "square_x_mm").real())
        square_y = float(_read_node(fs, "square_y_mm").real())
        pattern_cols = int(_read_node(fs, "pattern_cols").real())
        pattern_rows = int(_read_node(fs, "pattern_rows").real())
        rms = float(_read_node(fs, "rms").real())
        mm_per_px = float(_read_node(fs, "mm_per_px").real())
        created = _read_node(fs, "created").string()
    except CalibrationError:
        raise
    except Exception as exc:
        raise CalibrationError(f"标定文件解析失败: {path}，{exc}") from exc
    finally:
        if fs is not None:
            fs.release()
    if (
        camera_matrix is None or camera_matrix.shape != (3, 3)
        or dist_coeffs is None or dist_coeffs.size != 5
        or rvec is None or rvec.size != 3
        or tvec is None or tvec.size != 3
        or width <= 0 or height <= 0 or pattern_cols <= 0 or pattern_rows <= 0
    ):
        raise CalibrationError(f"标定文件字段缺失或损坏: {path}")
    calib = CalibrationResult(
        camera_matrix=np.asarray(camera_matrix, dtype=np.float64).reshape(3, 3),
        dist_coeffs=np.asarray(dist_coeffs, dtype=np.float64).reshape(1, 5),
        rvec=np.asarray(rvec, dtype=np.float64).reshape(3, 1),
        tvec=np.asarray(tvec, dtype=np.float64).reshape(3, 1),
        image_size=(width, height),
        square_x_mm=square_x,
        square_y_mm=square_y,
        pattern_size=(pattern_cols, pattern_rows),
        rms=rms,
        mm_per_px=mm_per_px,
        created=created,
    )
    logger.info(f"标定参数已加载: {path}（RMS {rms:.4f}px, 标定时间 {created}）")
    return calib


def _solve_and_save(
    corners_list: list[np.ndarray], image_size: tuple[int, int], cfg: CalibrateConfig
) -> tuple[bool, str]:
    if not corners_list:
        raise CalibrationError("无角点集合，无法标定")
    count = int(corners_list[0].reshape(-1, 2).shape[0])
    if any(int(corners.reshape(-1, 2).shape[0]) != count for corners in corners_list):
        raise CalibrationError("各图角点数量不一致")
    expected = cfg.pattern_cols * cfg.pattern_rows
    if count != expected:
        raise CalibrationError(
            f"角点数量 {count} 与内角点配置 {cfg.pattern_cols}x{cfg.pattern_rows}={expected} 不符"
        )
    if image_size[0] <= 0 or image_size[1] <= 0:
        raise CalibrationError("标定图尺寸非法")
    mean_corners = _mean_corners(corners_list)
    logger.info(f"角点集合 {len(corners_list)} 张取均值，每张 {count} 点")
    try:
        rms, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
            [_build_object_grid(cfg)],
            [mean_corners.astype(np.float32, copy=False)],
            image_size,
            np.empty((0, 0), dtype=np.float64),
            np.empty((0, 0), dtype=np.float64),
            flags=cv2.CALIB_FIX_ASPECT_RATIO | cv2.CALIB_FIX_PRINCIPAL_POINT,
        )
    except Exception as exc:
        raise CalibrationError(f"标定求解失败: {exc}") from exc
    if not rvecs or not tvecs or not math.isfinite(rms):
        raise CalibrationError("标定求解结果非法（外参缺失或 RMS 非有限值）")
    if camera_matrix is None or camera_matrix.shape != (3, 3) or dist_coeffs.size != 5:
        raise CalibrationError("标定求解结果非法（外参缺失或 RMS 非有限值）")
    calib = CalibrationResult(
        camera_matrix=np.asarray(camera_matrix, dtype=np.float64),
        dist_coeffs=np.asarray(dist_coeffs, dtype=np.float64).reshape(1, 5),
        rvec=np.asarray(rvecs[0], dtype=np.float64).reshape(3, 1),
        tvec=np.asarray(tvecs[0], dtype=np.float64).reshape(3, 1),
        image_size=image_size,
        square_x_mm=cfg.square_x_mm,
        square_y_mm=cfg.square_y_mm,
        pattern_size=(cfg.pattern_cols, cfg.pattern_rows),
        rms=float(rms),
        mm_per_px=cfg.target_mm_per_px,
    )
    if rms <= 0.1:
        logger.info(f"标定 RMS 重投影误差 {rms:.4f} px（达标 ≤0.1）")
    elif rms <= 0.3:
        logger.warn(f"标定 RMS 重投影误差 {rms:.4f} px（偏高，建议检查印刷与采图）")
    else:
        logger.warn(f"标定 RMS 重投影误差 {rms:.4f} px（超 0.3 告警线，残差矢量图排查印刷缺陷）")
    distortion = " ".join(f"{value:.4f}" for value in calib.dist_coeffs[0])
    logger.info(f"焦距 {calib.camera_matrix[0, 0]:.1f} px，畸变系数 [{distortion}]")
    _save_calibration_xml(cfg.out_xml, calib)
    if rms > 0.3:
        message = (
            f"标定质量偏低：RMS {rms:.4f} px 超过 0.3 px 门禁"
            f"（标定文件仍已写出: {cfg.out_xml}），请检查印刷精度与采图条件后重标"
        )
        logger.warn(message)
        return False, message
    return True, ""


def _put_qa_text(image: np.ndarray, text: str) -> None:
    cv2.putText(
        image, text, (40, 60), cv2.FONT_HERSHEY_SIMPLEX,
        1.3, (0, 220, 220), 2, cv2.LINE_AA,
    )


def _cv_round(value: float) -> int:
    return int(round(float(value)))


def _save_residual_qa(
    gray: np.ndarray,
    corners: np.ndarray,
    calib: CalibrationResult,
    cfg: CalibrateConfig,
    path: Path,
) -> None:
    try:
        projected, _ = cv2.projectPoints(
            _build_object_grid(cfg), calib.rvec, calib.tvec,
            calib.camera_matrix, calib.dist_coeffs,
        )
    except cv2.error as exc:
        raise CalibrationError(f"重投影计算失败: {exc}") from exc
    projected = projected.reshape(-1, 2)
    errors = np.linalg.norm(projected.astype(np.float64) - corners.astype(np.float64), axis=1)
    canvas = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for detected, model in zip(corners, projected):
        p0 = (_cv_round(detected[0]), _cv_round(detected[1]))
        tip = (
            _cv_round(detected[0] + (model[0] - detected[0]) * 50.0),
            _cv_round(detected[1] + (model[1] - detected[1]) * 50.0),
        )
        cv2.arrowedLine(canvas, p0, tip, (0, 0, 255), 2, cv2.LINE_AA, 0, 8.0)
        cv2.circle(canvas, p0, 3, (0, 220, 0), -1, cv2.LINE_AA)
    _put_qa_text(
        canvas,
        f"residual x50  mean {errors.mean():.3f}px  "
        f"p95 {np.percentile(errors, 95):.3f}px  max {errors.max():.3f}px",
    )
    save_image(path, canvas)


def _straightness(corners: np.ndarray, indices: list[np.ndarray]) -> float:
    worst = 0.0
    for index in indices:
        points = corners[index].astype(np.float32)
        line = cv2.fitLine(points, cv2.DIST_L2, 0, 0.01, 0.01).reshape(-1)
        vx, vy, x0, y0 = line
        distances = np.abs((points[:, 0] - x0) * vy - (points[:, 1] - y0) * vx)
        worst = max(worst, float(distances.max()))
    return worst


def _quality_error(calib: CalibrationResult, cfg: AppConfig, mean: float | None) -> str:
    verify = "未通过" if mean is None else f"{mean:.3f}px"
    qa = f"，QA 图: {cfg.calibrate.qa_dir}" if cfg.debug.save_intermediate else ""
    return (
        f"标定质量偏低：RMS {calib.rms:.4f}px，校正验证 mean {verify}"
        f"（标定文件已输出: {cfg.calibrate.out_xml}{qa}），"
        "请检查印刷精度与采图条件后重标"
    )


def _finish_calibration(
    gray: np.ndarray,
    corners_list: list[np.ndarray],
    cfg: AppConfig,
    solve_ok: bool,
    report: CalibReport,
) -> tuple[bool, str]:
    try:
        calib = load_calibration_xml(cfg.calibrate.out_xml)
    except CalibrationError as exc:
        message = f"标定文件回读失败: {exc}"
        logger.error(message)
        return False, message
    report.rms = calib.rms
    qa_dir = Path(cfg.calibrate.qa_dir)
    if cfg.debug.save_intermediate:
        try:
            qa_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            message = f"创建 QA 目录失败: {qa_dir}，{exc}"
            logger.error(message)
            return False, message
        logger.info(f"QA 目录: {qa_dir}")
    corners = _mean_corners(corners_list)
    pattern = (cfg.calibrate.pattern_cols, cfg.calibrate.pattern_rows)
    if cfg.debug.save_intermediate:
        overlay = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        overlay = cv2.drawChessboardCorners(
            overlay, pattern, corners.reshape(-1, 1, 2).astype(np.float32), True
        )
        _put_qa_text(overlay, f"corners {pattern[0]}x{pattern[1]}={len(corners)}")
        save_image(qa_dir / "01_corners_overlay.bmp", overlay)
        _save_residual_qa(
            gray, corners, calib, cfg.calibrate, qa_dir / "02_residual_vectors.bmp"
        )
    try:
        rectifier = Rectifier(calib, cfg.calibrate.target_mm_per_px)
    except RectifierError as exc:
        message = f"构建正射矫正映射失败: {exc}"
        logger.error(message)
        return False, message
    rectified = rectifier.rectify(gray)
    if rectified is None or rectified.size == 0:
        logger.error("正射矫正输出为空")
        return False, "正射矫正输出为空"
    if cfg.debug.save_intermediate:
        save_image(qa_dir / "03_rectified.bmp", rectified)
    mean_px = None
    try:
        corners2 = detect_board_corners(
            rectified, cfg.calibrate.pattern_cols, cfg.calibrate.pattern_rows
        )
    except CalibrationError as exc:
        logger.error(f"正射校正图角点重检失败，验证闭环中断: {exc}")
    else:
        grid = _build_object_grid(cfg.calibrate)
        ideal_u, ideal_v = rectifier.board_mm_to_px(grid[:, 0], grid[:, 1])
        ideal = np.column_stack((ideal_u, ideal_v))
        errors = np.linalg.norm(corners2.astype(np.float64) - ideal, axis=1)
        mean_px = float(errors.mean())
        p95_px = float(np.percentile(errors, 95))
        max_px = float(errors.max())
        report.verify_mean_px = mean_px
        report.verify_p95_px = p95_px
        rows = [np.arange(r * pattern[0], (r + 1) * pattern[0])
                for r in range(pattern[1])]
        cols = [np.arange(c, len(corners2), pattern[0]) for c in range(pattern[0])]
        row_straightness = _straightness(corners2, rows)
        col_straightness = _straightness(corners2, cols)
        logger.info(
            f"校正验证: 残差 mean {mean_px:.3f}px / p95 {p95_px:.3f}px / "
            f"max {max_px:.3f}px（{max_px * rectifier.mm_per_px:.4f}mm），"
            f"行直线度 {row_straightness:.3f}px，列直线度 {col_straightness:.3f}px"
        )
        if cfg.debug.save_intermediate:
            qa = cv2.cvtColor(rectified, cv2.COLOR_GRAY2BGR)
            for expected, detected in zip(ideal, corners2):
                cv2.circle(qa, (_cv_round(expected[0]), _cv_round(expected[1])),
                           5, (0, 220, 0), 1, cv2.LINE_AA)
                cv2.circle(qa, (_cv_round(detected[0]), _cv_round(detected[1])),
                           3, (0, 0, 255), -1, cv2.LINE_AA)
            _put_qa_text(
                qa,
                f"rectified residual  mean {mean_px:.2f}px  max {max_px:.2f}px "
                f"({max_px * rectifier.mm_per_px:.3f}mm)",
            )
            save_image(qa_dir / "04_verify_grid.bmp", qa)
    logger.info(
        f"标定完成: RMS {calib.rms:.4f}px, 焦距 {calib.camera_matrix[0, 0]:.1f}px, "
        f"参数文件 {cfg.calibrate.out_xml}"
    )
    if cfg.debug.save_intermediate:
        logger.info(f"质检图见 {qa_dir}")
    if not solve_ok or mean_px is None or mean_px > 0.5 or not math.isfinite(mean_px):
        message = _quality_error(calib, cfg, mean_px)
        logger.warn(message)
        logger.warn("禁止现场在 ok=false（或命令行非 0）后启用该 XML 做生产测量")
        return False, message
    return True, ""


def _calibrate(board_images, cfg: AppConfig, report: CalibReport) -> tuple[bool, str]:
    if len(board_images) == 0:
        return False, "无标定采图（图像列表为空），无法标定"
    square_x = cfg.calibrate.square_x_mm
    square_y = cfg.calibrate.square_y_mm
    if not all(math.isfinite(value) and value > 0 for value in (square_x, square_y)):
        return False, "标定格距配置非法: square_x_mm 与 square_y_mm 必须为有限正数"
    pattern_cols = cfg.calibrate.pattern_cols
    pattern_rows = cfg.calibrate.pattern_rows
    corners_list = []
    gray_first = None
    for index, image in enumerate(board_images):
        gray = to_gray8(image)
        if gray is None:
            if len(board_images) == 1:
                return False, "棋盘格图像格式不支持（须为 8UC1/8UC3/8UC4）"
            return False, f"第 {index + 1} 张标定采图格式不支持（须为 8UC1/8UC3/8UC4）"
        if gray_first is None:
            gray_first = gray
        elif gray.shape[:2] != gray_first.shape[:2]:
            return False, (
                f"第 {index + 1} 张标定采图尺寸 ({gray.shape[1]}, {gray.shape[0]}) "
                f"与首张 ({gray_first.shape[1]}, {gray_first.shape[0]}) 不一致"
            )
        try:
            corners = detect_board_corners(gray, pattern_cols, pattern_rows)
        except CalibrationError as exc:
            if len(board_images) == 1:
                return False, str(exc)
            return False, f"第 {index + 1} 张标定采图角点检测失败: {exc}"
        corners_list.append(corners)
    if len(board_images) > 1:
        logger.info(f"多图标定采图 {len(board_images)} 张全部检测成功，角点取均值降噪")
    image_size = (gray_first.shape[1], gray_first.shape[0])
    solve_ok, _ = _solve_and_save(corners_list, image_size, cfg.calibrate)
    report._solved = True
    report._xml_written = True
    return _finish_calibration(gray_first, corners_list, cfg, solve_ok, report)


def calibrate_images(
    board_images, cfg: AppConfig, report: CalibReport | None = None
) -> tuple[bool, str, CalibReport]:
    if report is not None and not isinstance(report, CalibReport):
        return False, "标定内部异常: report 必须为 CalibReport 或 None", CalibReport()
    result = CalibReport() if report is None else report
    result._reset()
    try:
        result.xml_path = cfg.calibrate.out_xml
        ok, err = _calibrate(board_images, cfg, result)
        return ok, err, result
    except CalibrationError as exc:
        logger.error(str(exc))
        return False, str(exc), result
    except Exception as exc:
        message = f"标定内部异常: {exc}"
        logger.error(message)
        return False, message, result
