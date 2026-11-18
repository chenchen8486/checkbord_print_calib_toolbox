from dataclasses import dataclass
import os
from pathlib import Path
import re

from checkbord_print_calib_toolbox.common import logger


class ConfigError(Exception):
    pass


@dataclass
class CheckerboardConfig:
    square_mm: float = 15.0
    cols: int = 35
    rows: int = 28
    border_mm: float = 15.0
    paper_w_mm: float = 555.0
    paper_h_mm: float = 450.0
    out_dir: str = "assets/checkerboard"


@dataclass
class CalibrateConfig:
    input_dir: str = "assets/test_data/calibration"
    out_xml: str = "assets/calibration/checkerboard_calib.xml"
    target_mm_per_px: float = 0.136
    qa_dir: str = "temp/calibration_qa"
    pattern_cols: int = 34
    pattern_rows: int = 27
    square_x_mm: float = 15.0
    square_y_mm: float = 15.0


@dataclass
class DebugConfig:
    save_intermediate: bool = False


@dataclass
class AppConfig:
    checkerboard: CheckerboardConfig
    calibrate: CalibrateConfig
    debug: DebugConfig


_FLOAT_PREFIX = re.compile(
    r"^[+-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|inf(?:inity)?|nan)",
    re.IGNORECASE,
)
_INT_PREFIX = re.compile(r"^[+-]?\d+")


class IniFile:
    def __init__(self) -> None:
        self.data: dict[str, dict[str, str]] = {}

    def load(self, path: str) -> None:
        try:
            raw = Path(path).read_bytes()
        except OSError as exc:
            raise ConfigError(f"无法打开配置文件: {path}") from exc
        try:
            text = raw.decode("utf-8-sig")
            section = ""
            for line_no, original in enumerate(text.splitlines(), 1):
                cuts = [pos for pos in (original.find("#"), original.find(";")) if pos >= 0]
                line = original[:min(cuts)].strip() if cuts else original.strip()
                if not line:
                    continue
                if line.startswith("["):
                    right = line.find("]")
                    name = line[1:right].strip() if right >= 0 else ""
                    if right < 0 or not name:
                        raise ConfigError(f"配置文件第 {line_no} 行段头格式错误: {line}")
                    section = name
                    continue
                if "=" not in line:
                    logger.warn(f"配置文件第 {line_no} 行缺少 '='，已忽略: {line}")
                    continue
                if not section:
                    logger.warn(f"配置文件第 {line_no} 行位于任何段之外，已忽略: {line}")
                    continue
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip()
                if not key:
                    logger.warn(f"配置文件第 {line_no} 行键名为空，已忽略")
                    continue
                self.data.setdefault(section, {})[key] = value
        except ConfigError:
            raise
        except Exception as exc:
            raise ConfigError(f"解析配置文件异常: {path}，原因: {exc}") from exc
        logger.info(f"配置文件加载成功: {path}")

    def has(self, section: str, key: str) -> bool:
        return key in self.data.get(section, {})

    def get_string(self, section: str, key: str, fallback: str) -> str:
        return self.data.get(section, {}).get(key, fallback)

    def get_double(self, section: str, key: str, fallback: float) -> float:
        value = self.get_string(section, key, "")
        if not value:
            return fallback
        match = _FLOAT_PREFIX.match(value)
        if match is None:
            logger.warn(f"配置项 [{section}] {key} 无法解析为浮点数: {value}，使用默认值")
            return fallback
        try:
            number = float(match.group(0))
        except ValueError:
            logger.warn(f"配置项 [{section}] {key} 无法解析为浮点数: {value}，使用默认值")
            return fallback
        if match.end() != len(value):
            logger.warn(f"配置项 [{section}] {key} 数值含多余字符: {value}")
        return number

    def get_int(self, section: str, key: str, fallback: int) -> int:
        value = self.get_string(section, key, "")
        if not value:
            return fallback
        match = _INT_PREFIX.match(value)
        if match is None:
            logger.warn(f"配置项 [{section}] {key} 无法解析为整数: {value}，使用默认值")
            return fallback
        try:
            number = int(match.group(0))
        except ValueError:
            logger.warn(f"配置项 [{section}] {key} 无法解析为整数: {value}，使用默认值")
            return fallback
        if match.end() != len(value):
            logger.warn(f"配置项 [{section}] {key} 数值含多余字符: {value}")
        return number

    def get_bool(self, section: str, key: str, fallback: bool) -> bool:
        value = self.get_string(section, key, "")
        if not value:
            return fallback
        lowered = value.lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        logger.warn(f"配置项 [{section}] {key} 无法解析为布尔值: {value}，使用默认值")
        return fallback


def _resolve_path(value: str, base_dir: Path) -> str:
    if not value:
        return ""
    if ":" in value or value.startswith(("/", "\\")):
        return value
    return str((base_dir / value).absolute())


def load_config(ini_path: str | os.PathLike[str]) -> AppConfig:
    path = Path(ini_path).absolute()
    ini = IniFile()
    ini.load(str(path))
    board = CheckerboardConfig(
        square_mm=ini.get_double("checkerboard", "square_mm", 15.0),
        cols=ini.get_int("checkerboard", "cols", 35),
        rows=ini.get_int("checkerboard", "rows", 28),
        border_mm=ini.get_double("checkerboard", "border_mm", 15.0),
        paper_w_mm=ini.get_double("checkerboard", "paper_w_mm", 555.0),
        paper_h_mm=ini.get_double("checkerboard", "paper_h_mm", 450.0),
        out_dir=ini.get_string("checkerboard", "out_dir", "assets/checkerboard"),
    )
    calibrate = CalibrateConfig(
        input_dir=ini.get_string("calibrate", "input_dir", "assets/test_data/calibration"),
        out_xml=ini.get_string("calibrate", "out_xml", "assets/calibration/checkerboard_calib.xml"),
        target_mm_per_px=ini.get_double("calibrate", "target_mm_per_px", 0.136),
        qa_dir=ini.get_string("calibrate", "qa_dir", "temp/calibration_qa"),
        pattern_cols=ini.get_int("calibrate", "pattern_cols", board.cols - 1),
        pattern_rows=ini.get_int("calibrate", "pattern_rows", board.rows - 1),
        square_x_mm=ini.get_double("calibrate", "square_x_mm", board.square_mm),
        square_y_mm=ini.get_double("calibrate", "square_y_mm", board.square_mm),
    )
    debug = DebugConfig(ini.get_bool("debug", "save_intermediate", False))
    base_dir = path.parent
    board.out_dir = _resolve_path(board.out_dir, base_dir)
    calibrate.input_dir = _resolve_path(calibrate.input_dir, base_dir)
    calibrate.out_xml = _resolve_path(calibrate.out_xml, base_dir)
    calibrate.qa_dir = _resolve_path(calibrate.qa_dir, base_dir)
    if any(not ini.has("calibrate", key) for key in (
        "pattern_cols", "pattern_rows", "square_x_mm", "square_y_mm"
    )):
        logger.info(
            "标定参数缺省项跟随 [checkerboard]: 内角点 "
            f"{calibrate.pattern_cols}x{calibrate.pattern_rows}，标称格距 "
            f"{calibrate.square_x_mm:g} mm"
        )
    if not ini.has("calibrate", "square_x_mm") and not ini.has("calibrate", "square_y_mm"):
        logger.warn(
            f"未配置实测格距，按名义 {board.square_mm:.1f}mm 计算；"
            "打印缩放误差将直接进入测量结果，务必实测后重标"
        )
    logger.info(f"配置加载完成: {path}")
    return AppConfig(board, calibrate, debug)
