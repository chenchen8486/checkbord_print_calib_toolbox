from pathlib import Path
import subprocess
import sys

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = """
import os
import sys
import run
run.EXE_OUTER_DIR = sys.argv[1]
run.INI_PATH = os.path.join(sys.argv[1], "config.ini")
run.main()
"""


def write_config(tmp_path, cols=5, rows=4, save_intermediate=False):
    (tmp_path / "images").mkdir()
    (tmp_path / "config.ini").write_text(
        "[checkerboard]\n"
        "square_mm=10\n"
        f"cols={cols}\n"
        f"rows={rows}\n"
        "border_mm=10\n"
        "paper_w_mm=100\n"
        "paper_h_mm=80\n"
        "out_dir=board\n"
        "[calibrate]\n"
        "input_dir=images\n"
        "out_xml=output/calib.xml\n"
        "qa_dir=qa\n"
        "[debug]\n"
        f"save_intermediate={str(save_intermediate).lower()}\n",
        encoding="utf-8",
    )


def invoke_launcher(tmp_path, choices):
    return subprocess.run(
        [sys.executable, "-c", LAUNCHER, str(tmp_path)],
        cwd=ROOT,
        input=choices,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


def synthetic_board():
    image = np.full((900, 1200), 255, np.uint8)
    for row in range(6):
        for col in range(7):
            if (row + col) % 2 == 0:
                cv2.rectangle(
                    image,
                    (250 + col * 100, 150 + row * 100),
                    (349 + col * 100, 249 + row * 100),
                    0,
                    cv2.FILLED,
                )
    return image


def test_launcher_makes_board_and_prints_output_paths(tmp_path):
    write_config(tmp_path)

    completed = invoke_launcher(tmp_path, "1\n0\n\n")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "制板成功" in completed.stdout
    for name in ("checkerboard.pdf", "checkerboard_preview.png", "打印说明.txt"):
        output = tmp_path / "board" / name
        assert output.is_file()
        assert str(output) in completed.stdout


def test_launcher_empty_calibration_returns_to_menu(tmp_path):
    write_config(tmp_path)

    completed = invoke_launcher(tmp_path, "2\n0\n\n")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    expected = f"标定采图目录为空，请先把棋盘格采图放入: {tmp_path / 'images'}"
    assert expected in completed.stdout
    assert completed.stdout.count("请选择功能号码") == 2


def test_launcher_bad_calibration_image_returns_to_menu(tmp_path):
    write_config(tmp_path)
    bad_image = tmp_path / "images" / "bad.bmp"
    bad_image.write_bytes(b"bad")

    completed = invoke_launcher(tmp_path, "2\n0\n\n")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert f"图像读取失败: {bad_image}" in completed.stdout
    assert completed.stdout.count("请选择功能号码") == 2


def test_launcher_calibration_prints_result_and_quality_metrics(tmp_path):
    write_config(tmp_path, cols=7, rows=6, save_intermediate=True)
    cv2.imwrite(str(tmp_path / "images" / "board.png"), synthetic_board())

    completed = invoke_launcher(tmp_path, "2\n0\n\n")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "标定成功，质量门禁通过" in completed.stdout
    assert "RMS" in completed.stdout
    assert "verify mean" in completed.stdout
    assert "p95" in completed.stdout
    assert f"标定文件: {tmp_path / 'output' / 'calib.xml'}" in completed.stdout
    assert f"QA 目录: {tmp_path / 'qa'}" in completed.stdout
    assert (tmp_path / "output" / "calib.xml").is_file()
    assert (tmp_path / "qa" / "04_verify_grid.bmp").is_file()


def test_launcher_reloads_config_and_returns_to_menu(tmp_path):
    write_config(tmp_path)

    completed = invoke_launcher(tmp_path, "3\n0\n\n")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert f"配置文件已重新加载: {tmp_path / 'config.ini'}" in completed.stdout
    assert completed.stdout.count("请选择功能号码") == 2


def test_launcher_missing_config_reload_shows_error_and_continues(tmp_path):
    completed = invoke_launcher(tmp_path, "3\n0\n\n")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert f"无法打开配置文件: {tmp_path / 'config.ini'}" in completed.stdout
    assert completed.stdout.count("请选择功能号码") == 2
