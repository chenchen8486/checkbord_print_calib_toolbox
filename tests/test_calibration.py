from datetime import datetime
from pathlib import Path
import re

import cv2
import numpy as np

from checkbord_print_calib_toolbox.calibration.calibrator import (
    CalibReport,
    calibrate_images,
)
from checkbord_print_calib_toolbox.config.ini import load_config


QA_NAMES = {
    "01_corners_overlay.bmp",
    "02_residual_vectors.bmp",
    "03_rectified.bmp",
    "04_verify_grid.bmp",
}


def make_config(tmp_path, debug="false", extra_checkerboard="", extra_calibrate=""):
    debug_section = "" if debug is None else f"[debug]\nsave_intermediate={debug}\n"
    ini = tmp_path / "config.ini"
    ini.write_text(
        "[checkerboard]\n" + extra_checkerboard +
        "[calibrate]\n"
        "out_xml=output/calib.xml\n"
        "qa_dir=qa\n"
        "target_mm_per_px=0.136\n" + extra_calibrate + debug_section,
        encoding="utf-8",
    )
    return load_config(ini)


def read_xml(path):
    fs = cv2.FileStorage(str(path), cv2.FILE_STORAGE_READ)
    assert fs.isOpened()
    names = (
        "camera_matrix", "dist_coeffs", "rvec", "tvec", "image_width",
        "image_height", "square_x_mm", "square_y_mm", "pattern_cols",
        "pattern_rows", "rms", "mm_per_px", "created",
    )
    values = {name: fs.getNode(name) for name in names}
    result = {}
    for name, node in values.items():
        if name in {"camera_matrix", "dist_coeffs", "rvec", "tvec"}:
            result[name] = node.mat()
        elif name == "created":
            result[name] = node.string()
        else:
            result[name] = node.real()
    fs.release()
    return result


def assert_xml_contract(xml, image, report):
    data = read_xml(xml)
    height, width = image.shape[:2]
    assert data["camera_matrix"].shape == (3, 3)
    assert data["camera_matrix"].dtype == np.float64
    assert data["dist_coeffs"].shape == (1, 5)
    assert data["dist_coeffs"].dtype == np.float64
    assert data["rvec"].shape == (3, 1)
    assert data["tvec"].shape == (3, 1)
    assert data["image_width"] == width
    assert data["image_height"] == height
    assert data["square_x_mm"] == 15.0
    assert data["square_y_mm"] == 15.0
    assert data["pattern_cols"] == 34
    assert data["pattern_rows"] == 27
    assert data["rms"] == report.rms
    assert data["mm_per_px"] == 0.136
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", data["created"])
    datetime.strptime(data["created"], "%Y-%m-%dT%H:%M:%S")
    matrix = data["camera_matrix"]
    assert matrix[0, 0] == matrix[1, 1]
    assert abs(matrix[0, 2] - (width - 1) / 2) <= 1e-6
    assert abs(matrix[1, 2] - (height - 1) / 2) <= 1e-6
    assert matrix[0, 1] == 0.0
    assert matrix[2, 0] == 0.0 and matrix[2, 1] == 0.0 and matrix[2, 2] == 1.0


def test_single_real_image_preserves_xml_and_four_qa_when_quality_fails(tmp_path, calibration_images):
    cfg = make_config(tmp_path, debug="true")
    report = CalibReport()

    ok, err, returned = calibrate_images([calibration_images[0]], cfg, report)

    assert ok is False
    assert err == (
        f"标定质量偏低：RMS {report.rms:.4f}px，校正验证 mean "
        f"{report.verify_mean_px:.3f}px（标定文件已输出: {report.xml_path}，"
        f"QA 图: {tmp_path / 'qa'}），请检查印刷精度与采图条件后重标"
    )
    assert returned is report
    assert report.xml_path == str((tmp_path / "output/calib.xml").absolute())
    assert report.rms > 0.3
    assert report.verify_mean_px > 0
    assert report.verify_p95_px > 0
    xml = Path(report.xml_path)
    assert_xml_contract(xml, calibration_images[0], report)
    qa_dir = tmp_path / "qa"
    assert {path.name for path in qa_dir.iterdir()} == QA_NAMES
    rectified = cv2.imread(str(qa_dir / "03_rectified.bmp"), cv2.IMREAD_UNCHANGED)
    assert rectified.shape == calibration_images[0].shape


def test_three_real_images_use_mean_and_debug_false_writes_no_qa(tmp_path, calibration_images):
    cfg = make_config(tmp_path, debug="false")
    (tmp_path / "qa").mkdir()

    ok, err, report = calibrate_images(calibration_images[:3], cfg)

    assert ok is False
    assert "QA 图" not in err
    assert report.rms > 0 and report.verify_mean_px > 0
    assert_xml_contract(Path(report.xml_path), calibration_images[0], report)
    assert list((tmp_path / "qa").iterdir()) == []


def test_synthetic_board_passes_quality_gate(tmp_path):
    image = np.full((900, 1200), 255, np.uint8)
    for row in range(6):
        for col in range(7):
            if (row + col) % 2 == 0:
                cv2.rectangle(
                    image, (250 + col * 100, 150 + row * 100),
                    (349 + col * 100, 249 + row * 100), 0, cv2.FILLED,
                )
    cfg = make_config(tmp_path, extra_checkerboard="cols=7\nrows=6\n")

    ok, err, report = calibrate_images([image], cfg)

    assert (ok, err) == (True, "")
    assert report.rms <= 0.3
    assert 0 < report.verify_mean_px <= 0.5


def test_empty_and_unsupported_inputs_have_fixed_errors(tmp_path):
    cfg = make_config(tmp_path)
    assert calibrate_images([], cfg)[:2] == (
        False, "无标定采图（图像列表为空），无法标定"
    )
    image = np.zeros((20, 20), np.float32)
    assert calibrate_images([image], cfg)[:2] == (
        False, "棋盘格图像格式不支持（须为 8UC1/8UC3/8UC4）"
    )


def test_blank_image_reports_missing_complete_board(tmp_path):
    cfg = make_config(tmp_path)
    ok, err, _ = calibrate_images([np.zeros((100, 100), np.uint8)], cfg)
    assert ok is False
    assert err == (
        "未检测到完整棋盘格（目标 34x27=918 个内角点），"
        "请检查标定板摆放与成像"
    )


def test_invalid_pattern_is_rejected_before_detection(tmp_path):
    cfg = make_config(tmp_path, extra_calibrate="pattern_cols=0\n")
    ok, err, _ = calibrate_images([np.zeros((20, 20), np.uint8)], cfg)
    assert (ok, err) == (False, "内角点配置非法: 0x27")


def test_second_image_size_mismatch_is_reported(tmp_path, calibration_images):
    cfg = make_config(tmp_path)
    other = cv2.resize(calibration_images[1], (100, 80))
    ok, err, _ = calibrate_images([calibration_images[0], other], cfg)
    assert ok is False
    assert err == "第 2 张标定采图尺寸 (100, 80) 与首张 (5472, 3648) 不一致"


def test_second_image_format_mismatch_is_reported(tmp_path, calibration_images):
    cfg = make_config(tmp_path)
    other = calibration_images[1].astype(np.float32)
    ok, err, _ = calibrate_images([calibration_images[0], other], cfg)
    assert (ok, err) == (False, "第 2 张标定采图格式不支持（须为 8UC1/8UC3/8UC4）")


def test_second_image_missing_corners_is_reported(tmp_path, calibration_images):
    cfg = make_config(tmp_path)
    blank = np.zeros_like(calibration_images[0])
    ok, err, _ = calibrate_images([calibration_images[0], blank], cfg)
    assert ok is False
    assert err.startswith("第 2 张标定采图角点检测失败: 未检测到完整棋盘格")
