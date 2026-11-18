from dataclasses import dataclass
import math
from pathlib import Path

import cv2
import numpy as np
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

from checkbord_print_calib_toolbox.common import logger
from checkbord_print_calib_toolbox.config.ini import AppConfig, CheckerboardConfig


@dataclass(frozen=True)
class MmRect:
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class BoardLayout:
    rects: list[MmRect]
    ox: float
    oy: float
    pattern_w: float
    pattern_h: float


class BoardError(Exception):
    pass


def _fmt_g(value: float) -> str:
    return f"{value:.6g}"


def layout_board(cfg: CheckerboardConfig) -> BoardLayout:
    numeric = (
        cfg.square_mm, cfg.paper_w_mm, cfg.paper_h_mm, cfg.border_mm,
    )
    if (
        not all(math.isfinite(value) for value in numeric)
        or cfg.square_mm <= 0
        or cfg.paper_w_mm <= 0
        or cfg.paper_h_mm <= 0
        or cfg.cols < 2
        or cfg.rows < 2
        or cfg.border_mm < 0
    ):
        raise BoardError("参数非法：格子边长/纸张尺寸必须为正，横纵格数必须不小于 2")
    pattern_w = cfg.square_mm * cfg.cols
    pattern_h = cfg.square_mm * cfg.rows
    ox = (cfg.paper_w_mm - pattern_w) / 2.0
    oy = (cfg.paper_h_mm - pattern_h) / 2.0
    if ox < cfg.border_mm:
        raise BoardError(f"横向留白不足：需要至少 {cfg.border_mm:.1f}mm，实际仅 {ox:.1f}mm")
    if oy < cfg.border_mm:
        raise BoardError(f"纵向留白不足：需要至少 {cfg.border_mm:.1f}mm，实际仅 {oy:.1f}mm")
    if cfg.cols % 2 == cfg.rows % 2:
        raise BoardError(
            f"横纵格数必须一奇一偶（当前 {cfg.cols}x{cfg.rows} 存在 180° 旋转歧义）"
        )
    rects = [
        MmRect(ox + col * cfg.square_mm, oy + row * cfg.square_mm,
               cfg.square_mm, cfg.square_mm)
        for row in range(cfg.rows)
        for col in range(cfg.cols)
        if (row + col) % 2 == 0
    ]
    mark_w = 0.6 * cfg.square_mm
    mark_h = 0.15 * cfg.square_mm
    mark = MmRect(ox * 0.4, cfg.paper_h_mm - oy * 0.4 - mark_h, mark_w, mark_h)
    separated = (
        mark.x + mark.w < ox
        or ox + pattern_w < mark.x
        or mark.y + mark.h < oy
        or oy + pattern_h < mark.y
    )
    if not separated:
        values = (
            mark.x, mark.y, mark.w, mark.h, ox, oy, pattern_w, pattern_h,
        )
        mark_text = ",".join(_fmt_g(value) for value in values[:4])
        pattern_text = ",".join(_fmt_g(value) for value in values[4:])
        raise BoardError(
            f"方向标记侵入棋盘图案（标记 [{mark_text}]mm，图案 [{pattern_text}]mm），"
            "请加大纸张或留白，或减小格数/格边长"
        )
    rects.append(mark)
    return BoardLayout(rects, ox, oy, pattern_w, pattern_h)


def _write_pdf(path: Path, cfg: CheckerboardConfig, layout: BoardLayout) -> None:
    try:
        pdf = canvas.Canvas(str(path), pagesize=(cfg.paper_w_mm * mm, cfg.paper_h_mm * mm))
    except Exception as exc:
        raise BoardError(f"无法创建文件：{path}") from exc
    try:
        pdf.setFillColorRGB(0, 0, 0)
        for rect in layout.rects:
            pdf.rect(rect.x * mm, rect.y * mm, rect.w * mm, rect.h * mm, stroke=0, fill=1)
        pdf.showPage()
        pdf.save()
    except Exception as exc:
        raise BoardError(f"写入文件失败：{path}") from exc


def _render_preview(cfg: CheckerboardConfig, layout: BoardLayout) -> np.ndarray:
    scale = 4.0
    width = round(cfg.paper_w_mm * scale)
    height = round(cfg.paper_h_mm * scale)
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    for rect in layout.rects:
        x0 = round(rect.x * scale)
        y0 = round((cfg.paper_h_mm - rect.y - rect.h) * scale)
        x1 = round((rect.x + rect.w) * scale)
        y1 = round((cfg.paper_h_mm - rect.y) * scale)
        cv2.rectangle(image, (x0, y0), (x1, y1), (0, 0, 0), cv2.FILLED)
    cv2.rectangle(image, (0, 0), (width - 1, height - 1), (180, 180, 180), 1)
    return image


def _build_print_note(cfg: CheckerboardConfig, layout: BoardLayout) -> str:
    nx, ny = min(10, cfg.cols), min(10, cfg.rows)
    values = {
        "paper_w": _fmt_g(cfg.paper_w_mm),
        "paper_h": _fmt_g(cfg.paper_h_mm),
        "square": _fmt_g(cfg.square_mm),
        "pattern_w": _fmt_g(layout.pattern_w),
        "pattern_h": _fmt_g(layout.pattern_h),
        "ox": _fmt_g(layout.ox),
        "oy": _fmt_g(layout.oy),
        "span_x": _fmt_g(nx * cfg.square_mm),
        "span_y": _fmt_g(ny * cfg.square_mm),
    }
    return f"""棋盘格标定板打印说明
============================================================

一、交付文件
- checkerboard.pdf：矢量打印文件（只需打印这一个文件）

二、成品规格
- 纸张成品尺寸：{values['paper_w']} × {values['paper_h']} mm（宽 × 高），幅面需 A1 及以上，印后裁切
- 棋盘格图案：{cfg.cols} 列 × {cfg.rows} 行，格子边长 {values['square']} mm（黑白相间）
- 图案区域：{values['pattern_w']} × {values['pattern_h']} mm，左右各留 {values['ox']} mm、上下各留 {values['oy']} mm 白色边距
- 方向标记：左上角白边内有一根黑色细长条，用于辨识摆放方向，属正常设计，
  请勿当作脏点修掉

三、打印要求（重要，请逐条落实）
1. 请用 PDF 原文件直接输出，不要转成 JPG/PNG 图片后再打印；
2. 必须 100% 实际尺寸打印，关闭"适应页面 / 适合纸张 / 自动缩放"等一切缩放选项；
3. 打印分辨率不低于 600 DPI，建议 1200 DPI；
4. 纸张用哑光厚卡纸或铜版纸（克重 ≥200g），黑白打印、纯黑实底；
   不要覆亮膜（反光会影响后续拍照）；
5. 印后按 {values['paper_w']} × {values['paper_h']} mm 裁切成品（裁切偏差 ±1mm 内可接受，
   图案本身的尺寸精度才是关键）。

四、印后验收指标（请配合实测后告诉我们数值）
1. 横向连续 {nx} 个格子的总宽度：应为 {values['span_x']} mm，偏差不超过 ±0.5 mm；
2. 纵向连续 {ny} 个格子的总高度：应为 {values['span_y']} mm，偏差不超过 ±0.5 mm；
3. 横向与纵向须比例一致：所用格数相同时，两条实测跨距之差不超过 0.3 mm；
   所用格数不同时，先各自除以格数得到单格边长再比较，差不超过 0.03 mm；
4. 格子边缘平直无锯齿，黑白分明无灰边。
如任何一项不达标，请先不要裁切交付，联系我们调整后再印。
"""


def _write_note(path: Path, text: str) -> None:
    try:
        stream = path.open("w", encoding="utf-8-sig", newline="\n")
    except OSError as exc:
        raise BoardError(f"无法创建文件：{path}") from exc
    try:
        with stream:
            stream.write(text)
    except OSError as exc:
        raise BoardError(f"写入文件失败：{path}") from exc


def generate_board(cfg: AppConfig | CheckerboardConfig) -> tuple[bool, str]:
    board = cfg.checkerboard if hasattr(cfg, "checkerboard") else cfg
    try:
        layout = layout_board(board)
    except BoardError as exc:
        logger.error(str(exc))
        return False, str(exc)
    out_dir = Path(board.out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        message = f"创建输出目录失败：{out_dir}（{exc}）"
        logger.error(message)
        return False, message
    pdf_path = out_dir / "checkerboard.pdf"
    preview_path = out_dir / "checkerboard_preview.png"
    note_path = out_dir / "打印说明.txt"
    try:
        _write_pdf(pdf_path, board, layout)
    except BoardError as exc:
        logger.error(str(exc))
        return False, str(exc)
    logger.info(f"矢量 PDF 已生成: {pdf_path}（{len(layout.rects) - 1} 个黑格）")
    try:
        if not cv2.imwrite(str(preview_path), _render_preview(board, layout)):
            raise cv2.error("cv2.imwrite 返回失败")
    except Exception as exc:
        message = f"保存预览图失败：{preview_path}"
        logger.error(f"{message}，原因: {exc}")
        return False, message
    logger.info(f"预览图已生成: {preview_path}（仅供核对，勿用于打印）")
    try:
        _write_note(note_path, _build_print_note(board, layout))
    except BoardError as exc:
        logger.error(str(exc))
        return False, str(exc)
    logger.info(f"打印说明已生成: {note_path}")
    logger.info(
        f"纸张 {_fmt_g(board.paper_w_mm)}x{_fmt_g(board.paper_h_mm)}mm，"
        f"图案 {board.cols}x{board.rows} 格（{_fmt_g(board.square_mm)}mm/格），"
        f"内角点 {board.cols - 1}x{board.rows - 1}="
        f"{(board.cols - 1) * (board.rows - 1)} 个，角点覆盖跨度 "
        f"{_fmt_g((board.cols - 2) * board.square_mm)}x"
        f"{_fmt_g((board.rows - 2) * board.square_mm)}mm"
    )
    return True, ""
