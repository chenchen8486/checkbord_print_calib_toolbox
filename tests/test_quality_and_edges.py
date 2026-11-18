from pathlib import Path

import cv2
import numpy as np

import checkbord_print_calib_toolbox.calibration.calibrator as calibrator_module
from checkbord_print_calib_toolbox.calibration.calibrator import calibrate_images
from checkbord_print_calib_toolbox.config.ini import load_config


def synthetic_board():
    image = np.full((900, 1200), 255, np.uint8)
    for row in range(6):
        for col in range(7):
            if (row + col) % 2 == 0:
                cv2.rectangle(
                    image, (250 + col * 100, 150 + row * 100),
                    (349 + col * 100, 249 + row * 100), 0, cv2.FILLED,
                )
    return image


def edge_config(tmp_path, debug="false", target=0.136):
    debug_text = "" if debug is None else f"[debug]\nsave_intermediate={debug}\n"
    ini = tmp_path / "config.ini"
    ini.write_text(
        "[checkerboard]\ncols=7\nrows=6\n"
        "[calibrate]\n"
        "out_xml=output/calib.xml\n"
        "qa_dir=qa\n"
        f"target_mm_per_px={target}\n" + debug_text,
        encoding="utf-8",
    )
    return load_config(ini)


def test_missing_debug_key_matches_false(tmp_path):
    cfg = edge_config(tmp_path, debug=None)
    ok, err, report = calibrate_images([synthetic_board()], cfg)
    assert (ok, err) == (True, "")
    assert Path(report.xml_path).is_file()
    assert not (tmp_path / "qa").exists()


def test_rectified_redetection_failure_keeps_only_first_three_qa(tmp_path):
    cfg = edge_config(tmp_path, debug="true", target=10.0)
    ok, err, report = calibrate_images([synthetic_board()], cfg)

    assert ok is False
    assert report.rms <= 0.3
    assert report.verify_mean_px == 0 and report.verify_p95_px == 0
    assert err == (
        f"标定质量偏低：RMS {report.rms:.4f}px，校正验证 mean 未通过"
        f"（标定文件已输出: {report.xml_path}，QA 图: {tmp_path / 'qa'}），"
        "请检查印刷精度与采图条件后重标"
    )
    assert Path(report.xml_path).is_file()
    assert {path.name for path in (tmp_path / "qa").iterdir()} == {
        "01_corners_overlay.bmp", "02_residual_vectors.bmp", "03_rectified.bmp"
    }


def test_qa_directory_creation_failure_preserves_xml(tmp_path):
    (tmp_path / "qa").write_text("not a directory", encoding="utf-8")
    cfg = edge_config(tmp_path, debug="true")
    ok, err, report = calibrate_images([synthetic_board()], cfg)

    assert ok is False
    assert err.startswith(f"创建 QA 目录失败: {tmp_path / 'qa'}，")
    assert report.rms > 0
    assert report.verify_mean_px == 0
    assert Path(report.xml_path).is_file()


def test_single_qa_write_failure_does_not_fail_calibration(tmp_path, monkeypatch):
    cfg = edge_config(tmp_path, debug="true")
    monkeypatch.setattr(calibrator_module, "save_image", lambda *args: False)

    ok, err, report = calibrate_images([synthetic_board()], cfg)

    assert (ok, err) == (True, "")
    assert report.verify_mean_px <= 0.5
    assert (tmp_path / "qa").is_dir()
    assert list((tmp_path / "qa").iterdir()) == []


def test_invalid_square_distances_are_rejected_before_solving(tmp_path):
    for x_mm, y_mm in ((-15.0, 15.0), (-15.0, -15.0), (0.0, 15.0),
                       (float("nan"), 15.0), (float("inf"), 15.0), (15.0, 0.0)):
        cfg = edge_config(tmp_path)
        cfg.calibrate.square_x_mm = x_mm
        cfg.calibrate.square_y_mm = y_mm

        ok, err, _ = calibrate_images([synthetic_board()], cfg)

        assert (ok, err) == (
            False, "标定格距配置非法: square_x_mm 与 square_y_mm 必须为有限正数"
        )
