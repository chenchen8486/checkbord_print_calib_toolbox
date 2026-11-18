from pathlib import Path

import cv2
import numpy as np

import checkbord_print_calib_toolbox as toolbox
from checkbord_print_calib_toolbox.cli import main


def write_config(tmp_path, input_dir="images"):
    ini = tmp_path / "config.ini"
    ini.write_text(
        "[checkerboard]\n"
        "out_dir=board\n"
        "[calibrate]\n"
        f"input_dir={input_dir}\n"
        "out_xml=output/calib.xml\n"
        "qa_dir=qa\n"
        "target_mm_per_px=0.136\n"
        "[debug]\n"
        "save_intermediate=false\n",
        encoding="utf-8",
    )
    return ini


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


def test_version_and_facade_never_throw(tmp_path):
    assert toolbox.version() == "1.0.0"
    assert toolbox.__version__ == "1.0.0"
    missing = tmp_path / "missing.ini"
    ok, err = toolbox.make_board(missing)
    assert (ok, err) == (False, f"无法打开配置文件: {missing.absolute()}")
    ok, err, _ = toolbox.calibrate([], missing)
    assert ok is False
    assert err == f"读取标定配置失败: 无法打开配置文件: {missing.absolute()}"


def test_calibrate_empty_returns_supplied_report_with_xml_path(tmp_path):
    ini = write_config(tmp_path)
    report = toolbox.CalibReport(rms=99, verify_mean_px=99, verify_p95_px=99)
    ok, err, returned = toolbox.calibrate([], ini, report)
    assert (ok, err) == (False, "无标定采图（图像列表为空），无法标定")
    assert returned is report
    assert report.rms == 0 and report.verify_mean_px == 0 and report.verify_p95_px == 0
    assert report.xml_path == str((tmp_path / "output/calib.xml").absolute())


def test_facade_rejects_bad_image_without_throwing(tmp_path):
    ini = write_config(tmp_path)
    ok, err, _ = toolbox.calibrate([object()], ini)
    assert (ok, err) == (False, "棋盘格图像格式不支持（须为 8UC1/8UC3/8UC4）")


def test_cli_make_board_returns_zero_and_writes_outputs(tmp_path, capsys):
    ini = write_config(tmp_path)
    code = main(["make-board", "--ini", str(ini)])
    captured = capsys.readouterr()
    assert code == 0
    assert "标定板生成成功" in captured.out
    assert (tmp_path / "board" / "checkerboard.pdf").is_file()


def test_cli_calibrate_accepts_multiple_images_after_one_option(tmp_path, capsys):
    ini = write_config(tmp_path)
    ini.write_text(
        ini.read_text(encoding="utf-8").replace("[checkerboard]\n", "[checkerboard]\ncols=7\nrows=6\n"),
        encoding="utf-8",
    )
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    cv2.imwrite(str(first), synthetic_board())
    cv2.imwrite(str(second), synthetic_board())

    code = main([
        "calibrate", "--ini", str(ini), "--image", str(first), str(second),
    ])

    captured = capsys.readouterr()
    assert code == 0
    assert "RMS" in captured.out and "mean" in captured.out and "p95" in captured.out
    assert (tmp_path / "output" / "calib.xml").is_file()


def test_cli_bad_image_fails_whole_run(tmp_path, capsys):
    ini = write_config(tmp_path)
    bad = tmp_path / "bad.bmp"
    bad.write_bytes(b"bad")
    code = main(["calibrate", "--ini", str(ini), "--image", str(bad)])
    captured = capsys.readouterr()
    assert code == 1
    assert f"图像读取失败: {bad}" in captured.err
    assert not (tmp_path / "output" / "calib.xml").exists()


def test_cli_missing_and_empty_input_directories(tmp_path, capsys):
    missing = tmp_path / "missing"
    ini = write_config(tmp_path, input_dir=missing)
    assert main(["calibrate", "--ini", str(ini)]) == 1
    assert f"标定采图目录不存在或不可访问: {missing}" in capsys.readouterr().err

    empty = tmp_path / "empty"
    empty.mkdir()
    ini = write_config(tmp_path, input_dir=empty)
    assert main(["calibrate", "--ini", str(ini)]) == 1
    assert f"标定采图目录为空，请先把棋盘格采图放入: {empty}" in capsys.readouterr().err


def test_cli_unknown_command_is_chinese_usage_error(capsys):
    code = main(["unknown"])
    captured = capsys.readouterr()
    assert code == 2
    assert "参数错误" in captured.err
    assert "用法" in captured.err


def test_invalid_report_object_does_not_escape_facade():
    ok, err, report = toolbox.calibrate([], "unused.ini", object())
    assert ok is False
    assert err == "标定内部异常: report 必须为 CalibReport 或 None"
    assert isinstance(report, toolbox.CalibReport)


def test_cli_does_not_advertise_stale_xml_after_detection_failure(tmp_path, capsys):
    ini = write_config(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    (output / "calib.xml").write_text("old result", encoding="utf-8")
    blank = tmp_path / "blank.png"
    cv2.imwrite(str(blank), np.zeros((100, 100), np.uint8))

    code = main(["calibrate", "--ini", str(ini), "--image", str(blank)])

    captured = capsys.readouterr()
    assert code == 1
    assert "标定文件:" not in captured.out
    assert "未检测到完整棋盘格" in captured.err
