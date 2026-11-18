from pathlib import Path

import pytest

from checkbord_print_calib_toolbox.config.ini import ConfigError, load_config
from checkbord_print_calib_toolbox.common.logger import set_log_handler


def test_bom_comments_paths_and_independent_fallbacks(tmp_path):
    ini = tmp_path / "settings.ini"
    ini.write_text(
        "outside=ignored\n"
        "[checkerboard] ; comment\n"
        "square_mm = 16.5mm # prefix\n"
        "cols = 9cells\n"
        "rows = 8\n"
        "out_dir = output/board\n"
        "[calibrate]\n"
        "pattern_cols = 7\n"
        "input_dir = images\n"
        "[debug]\n",
        encoding="utf-8-sig",
    )
    messages = []
    set_log_handler(lambda level, message: messages.append((level, message)))
    try:
        cfg = load_config(ini)
    finally:
        set_log_handler(None)

    assert cfg.checkerboard.square_mm == 16.5
    assert cfg.checkerboard.cols == 9
    assert cfg.checkerboard.out_dir == str((tmp_path / "output/board").absolute())
    assert cfg.calibrate.pattern_cols == 7
    assert cfg.calibrate.pattern_rows == 7
    assert cfg.calibrate.square_x_mm == 16.5
    assert cfg.calibrate.square_y_mm == 16.5
    assert cfg.calibrate.input_dir == str((tmp_path / "images").absolute())
    assert cfg.debug.save_intermediate is False
    assert any("数值含多余字符" in message for _, message in messages)
    assert any("未配置实测格距，按名义 16.5mm" in message for _, message in messages)


def test_explicit_square_values_suppress_nominal_warning(tmp_path):
    ini = tmp_path / "settings.ini"
    ini.write_text(
        "[checkerboard]\nsquare_mm=18\n"
        "[calibrate]\nsquare_x_mm=15.0\nsquare_y_mm=15.0\n",
        encoding="utf-8",
    )
    messages = []
    set_log_handler(lambda level, message: messages.append(message))
    try:
        cfg = load_config(ini)
    finally:
        set_log_handler(None)

    assert cfg.calibrate.square_x_mm == 15.0
    assert cfg.calibrate.square_y_mm == 15.0
    assert not any("未配置实测格距" in message for message in messages)


def test_partial_square_override_uses_fallback_for_other_axis(tmp_path):
    ini = tmp_path / "settings.ini"
    ini.write_text(
        "[checkerboard]\nsquare_mm=18.5\n"
        "[calibrate]\nsquare_x_mm=15.0\n",
        encoding="utf-8",
    )
    messages = []
    set_log_handler(lambda level, message: messages.append(message))
    try:
        cfg = load_config(ini)
    finally:
        set_log_handler(None)

    assert cfg.calibrate.square_x_mm == 15.0
    assert cfg.calibrate.square_y_mm == 18.5
    assert not any("未配置实测格距" in message for message in messages)


def test_bad_section_header_has_fixed_error(tmp_path):
    ini = tmp_path / "bad.ini"
    ini.write_text("[checkerboard\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_config(ini)
    assert str(exc.value) == "配置文件第 1 行段头格式错误: [checkerboard"


def test_missing_file_has_fixed_error(tmp_path):
    ini = tmp_path / "missing.ini"
    with pytest.raises(ConfigError) as exc:
        load_config(ini)
    assert str(exc.value) == f"无法打开配置文件: {ini.absolute()}"


def test_invalid_bool_uses_false_default(tmp_path):
    ini = tmp_path / "bool.ini"
    ini.write_text("[debug]\nsave_intermediate=maybe\n", encoding="utf-8")
    cfg = load_config(ini)
    assert cfg.debug.save_intermediate is False
