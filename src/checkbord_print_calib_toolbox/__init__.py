from checkbord_print_calib_toolbox.board.generator import generate_board
from checkbord_print_calib_toolbox.calibration.calibrator import CalibReport, calibrate_images
from checkbord_print_calib_toolbox.config.ini import ConfigError, load_config


__version__ = "1.0.0"
__all__ = ["CalibReport", "version", "make_board", "calibrate"]


def version() -> str:
    return __version__


def make_board(ini_path) -> tuple[bool, str]:
    try:
        return generate_board(load_config(ini_path))
    except ConfigError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"制板内部异常: {exc}"


def calibrate(
    board_images, ini_path, report: CalibReport | None = None
) -> tuple[bool, str, CalibReport]:
    try:
        if report is not None and not isinstance(report, CalibReport):
            return False, "标定内部异常: report 必须为 CalibReport 或 None", CalibReport()
        result = CalibReport() if report is None else report
        result._reset()
        cfg = load_config(ini_path)
    except ConfigError as exc:
        return False, f"读取标定配置失败: {exc}", result
    except Exception as exc:
        return False, f"读取配置失败: {exc}", result
    try:
        return calibrate_images(board_images, cfg, result)
    except Exception as exc:
        return False, f"标定内部异常: {exc}", result
