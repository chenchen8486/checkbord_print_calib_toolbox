import sys
from typing import Callable

LogHandler = Callable[[str, str], None]
_handler: LogHandler | None = None


def set_log_handler(handler: LogHandler | None) -> None:
    global _handler
    _handler = handler


def log(level: str, message: str) -> None:
    level = level.upper()
    if _handler is not None:
        if level != "DEBUG":
            _handler(level, message)
        return
    if level == "DEBUG":
        return
    stream = sys.stderr if level in {"WARN", "ERROR"} else sys.stdout
    print(f"[{level}] {message}", file=stream)


def debug(message: str) -> None:
    log("DEBUG", message)


def info(message: str) -> None:
    log("INFO", message)


def warn(message: str) -> None:
    log("WARN", message)


def error(message: str) -> None:
    log("ERROR", message)
