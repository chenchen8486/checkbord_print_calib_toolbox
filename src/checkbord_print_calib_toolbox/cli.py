import argparse
import sys

from checkbord_print_calib_toolbox import calibrate, make_board
from checkbord_print_calib_toolbox.common.image_io import ImageIoError, list_images, read_image
from checkbord_print_calib_toolbox.config.ini import ConfigError, load_config


USAGE = "checkbord-toolbox make-board --ini <ini路径>；checkbord-toolbox calibrate --ini <ini路径> [--image <路径> ...]"


class UsageError(Exception):
    pass


class ChineseArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = ChineseArgumentParser(prog="checkbord-toolbox", description="棋盘格制板与相机标定工具箱")
    subparsers = parser.add_subparsers(dest="command", required=True)
    board = subparsers.add_parser("make-board", help="生成标定板打印三件套")
    board.add_argument("--ini", required=True, help="配置文件路径")
    calibration = subparsers.add_parser("calibrate", help="执行相机标定与质量验证")
    calibration.add_argument("--ini", required=True, help="配置文件路径")
    calibration.add_argument(
        "--image", action="append", nargs="+", metavar="路径",
        help="显式采图路径，可写多个路径或重复使用本参数；缺省时读取 input_dir",
    )
    return parser


def _read_images(paths: list[str]):
    images = []
    for path in paths:
        image = read_image(path)
        if image is None:
            print(f"图像读取失败: {path}", file=sys.stderr)
            return None
        images.append(image)
    return images


def _run_calibrate(args) -> int:
    if args.image:
        paths = [path for group in args.image for path in group]
    else:
        try:
            cfg = load_config(args.ini)
            paths = list_images(cfg.calibrate.input_dir)
        except (ConfigError, ImageIoError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if not paths:
            print(
                f"标定采图目录为空，请先把棋盘格采图放入: {cfg.calibrate.input_dir}",
                file=sys.stderr,
            )
            return 1
    images = _read_images(paths)
    if images is None:
        return 1
    ok, err, report = calibrate(images, args.ini)
    if report._solved:
        print(
            f"RMS {report.rms:.4f} px, verify mean {report.verify_mean_px:.3f} px, "
            f"p95 {report.verify_p95_px:.3f} px"
        )
    if report._xml_written:
        print(f"标定文件: {report.xml_path}")
    if not ok:
        print(f"标定失败: {err}", file=sys.stderr)
        return 1
    print("标定成功，质量门禁通过")
    return 0


def main(argv=None) -> int:
    try:
        args = _build_parser().parse_args(argv)
    except UsageError:
        print(f"参数错误。\n用法: {USAGE}", file=sys.stderr)
        return 2
    if args.command == "make-board":
        ok, err = make_board(args.ini)
        if not ok:
            print(f"制板失败: {err}", file=sys.stderr)
            return 1
        print("标定板生成成功")
        return 0
    if args.command == "calibrate":
        return _run_calibrate(args)
    print(f"参数错误。\n用法: {USAGE}", file=sys.stderr)
    return 2
