from pathlib import Path
import re

import cv2

from checkbord_print_calib_toolbox.board.generator import generate_board
from checkbord_print_calib_toolbox.common.logger import set_log_handler
from checkbord_print_calib_toolbox.config.ini import load_config


DEFAULTS = {
    "square_mm": "15.0",
    "cols": "35",
    "rows": "28",
    "border_mm": "15.0",
    "paper_w_mm": "555.0",
    "paper_h_mm": "450.0",
}


def make_ini(tmp_path, **overrides):
    values = DEFAULTS | {key: str(value) for key, value in overrides.items()}
    values.setdefault("out_dir", "board")
    ini = tmp_path / "config.ini"
    ini.write_text(
        "[checkerboard]\n" + "".join(f"{key}={value}\n" for key, value in values.items()),
        encoding="utf-8",
    )
    return ini


def test_default_board_writes_pdf_preview_and_note(tmp_path):
    cfg = load_config(make_ini(tmp_path))
    messages = []
    set_log_handler(lambda level, message: messages.append(message))
    try:
        ok, err = generate_board(cfg)
    finally:
        set_log_handler(None)

    assert (ok, err) == (True, "")
    out = tmp_path / "board"
    assert {p.name for p in out.iterdir()} == {
        "checkerboard.pdf",
        "checkerboard_preview.png",
        "打印说明.txt",
    }
    pdf = (out / "checkerboard.pdf").read_bytes()
    match = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([0-9.]+)\s+([0-9.]+)\s*\]", pdf)
    assert match is not None
    width_mm = float(match.group(1)) * 25.4 / 72.0
    height_mm = float(match.group(2)) * 25.4 / 72.0
    assert abs(width_mm - 555.0) <= 0.1
    assert abs(height_mm - 450.0) <= 0.1
    preview = cv2.imread(str(out / "checkerboard_preview.png"), cv2.IMREAD_UNCHANGED)
    assert preview.shape == (1800, 2220, 3)
    note_bytes = (out / "打印说明.txt").read_bytes()
    assert note_bytes.startswith(b"\xef\xbb\xbf")
    note = note_bytes.decode("utf-8-sig")
    assert "左右各留 15 mm、上下各留 15 mm" in note
    assert "横向连续 10 个格子的总宽度：应为 150 mm" in note
    assert "纵向连续 10 个格子的总高度：应为 150 mm" in note
    assert "请勿当作脏点修掉" in note
    assert "100% 实际尺寸打印" in note
    assert any("仅供核对，勿用于打印" in message for message in messages)
    assert all(str(out / name) in "\n".join(messages) for name in (
        "checkerboard.pdf", "checkerboard_preview.png", "打印说明.txt"
    ))


def test_same_parity_fails(tmp_path):
    cfg = load_config(make_ini(tmp_path, rows=35, paper_w_mm=600, paper_h_mm=600))
    ok, err = generate_board(cfg)
    assert ok is False
    assert err == "横纵格数必须一奇一偶（当前 35x35 存在 180° 旋转歧义）"
    assert not (tmp_path / "board").exists()


def test_horizontal_border_failure_has_one_decimal(tmp_path):
    cfg = load_config(make_ini(tmp_path, paper_w_mm=500))
    ok, err = generate_board(cfg)
    assert (ok, err) == (False, "横向留白不足：需要至少 15.0mm，实际仅 -12.5mm")
    assert not (tmp_path / "board").exists()


def test_invalid_parameter_fails(tmp_path):
    cfg = load_config(make_ini(tmp_path, cols=1))
    ok, err = generate_board(cfg)
    assert (ok, err) == (False, "参数非法：格子边长/纸张尺寸必须为正，横纵格数必须不小于 2")


def test_intruding_marker_fails_without_outputs(tmp_path):
    cfg = load_config(make_ini(
        tmp_path, paper_w_mm=540, paper_h_mm=423, border_mm=0
    ))
    ok, err = generate_board(cfg)
    assert ok is False
    assert err == (
        "方向标记侵入棋盘图案（标记 [3,420.15,9,2.25]mm，"
        "图案 [7.5,1.5,525,420]mm），请加大纸张或留白，或减小格数/格边长"
    )
    assert not (tmp_path / "board").exists()


def test_small_board_uses_actual_span_counts(tmp_path):
    cfg = load_config(make_ini(
        tmp_path, cols=3, rows=2, square_mm=10,
        paper_w_mm=100, paper_h_mm=100, border_mm=10,
    ))
    ok, err = generate_board(cfg)
    assert (ok, err) == (True, "")
    note = (tmp_path / "board" / "打印说明.txt").read_text(encoding="utf-8-sig")
    assert "横向连续 3 个格子的总宽度：应为 30 mm" in note
    assert "纵向连续 2 个格子的总高度：应为 20 mm" in note
    assert "连续 10 个格子" not in note
    assert "所用格数不同时" in note


def test_larger_paper_note_uses_actual_margins(tmp_path):
    cfg = load_config(make_ini(tmp_path, paper_w_mm=600, paper_h_mm=500))
    ok, err = generate_board(cfg)
    assert (ok, err) == (True, "")
    note = (tmp_path / "board" / "打印说明.txt").read_text(encoding="utf-8-sig")
    assert "左右各留 37.5 mm、上下各留 40 mm" in note
    assert "四边各留 15" not in note


def test_output_directory_creation_failure_is_reported(tmp_path):
    (tmp_path / "board").write_text("not a directory", encoding="utf-8")
    cfg = load_config(make_ini(tmp_path))
    ok, err = generate_board(cfg)
    assert ok is False
    assert err.startswith(f"创建输出目录失败：{tmp_path / 'board'}（")
