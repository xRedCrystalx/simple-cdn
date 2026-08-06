"""
Central logging configuration for the service.

Every module logs through the stdlib `logging` module under the `cdn.*` namespace and
lets the root logger, configured here exactly once during startup, decide where those
records end up. `setup()` installs three sinks:

  - the console, so `journalctl -u simple-cdn` follows the live service,
  - `<LOG_DIR>/daily_log`, a midnight rotating file holding the full log,
  - `<LOG_DIR>/error_log`, the same stream filtered down to WARNING and above so that
    failures stay greppable without wading through per request noise.
"""

import logging, sys
from logging import Formatter, LogRecord, Logger, StreamHandler
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from types import TracebackType

from utils.general import ENV


DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
CONSOLE_FORMAT: str = "%(asctime)s %(levelname)s %(name)-20s %(message)s"
FILE_FORMAT: str = "[%(asctime)s] [%(levelname)-8s] [%(process)d/%(threadName)s] %(name)s: %(message)s"

# uvicorn.access logs one line per request, which is noise at anything but debug level.
_ACCESS_LOGGER: str = "uvicorn.access"

_RESET: str = "\x1b[0m"
_LEVEL_COLORS: dict[int, str] = {
    logging.DEBUG:      "\x1b[36m",     # cyan
    logging.INFO:       "\x1b[32m",     # green
    logging.WARNING:    "\x1b[33m",     # yellow
    logging.ERROR:      "\x1b[31m",     # red
    logging.CRITICAL:   "\x1b[1;31m"    # bold red
}

logger: Logger = logging.getLogger("cdn.logger")


class _ConsoleFormatter(Formatter):
    """
    Console formatter that colours the level name when the stream is a terminal.

    Padding is applied before the escape codes are added, otherwise the invisible bytes
    would count towards the column width and the output would no longer line up.
    """

    def __init__(self, fmt: str, datefmt: str, use_color: bool) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self._use_color: bool = use_color

    def format(self, record: LogRecord) -> str:
        original: str = record.levelname

        # The record is shared with the file handlers, so the change has to be undone
        # again before this returns, hence the try/finally.
        color: str = _LEVEL_COLORS.get(record.levelno, "") if self._use_color else ""
        record.levelname = f"{color}{original:<8}{_RESET}" if color else f"{original:<8}"

        try:
            return super().format(record)

        finally:
            record.levelname = original


def resolve_level() -> int:
    """
    Work out the level the service should log at.

    An explicit LOG_LEVEL wins, otherwise DEBUG decides between debug and info.
    """
    if ENV.DEBUG:
        return logging.DEBUG

    configured: str = ENV.LOG_LEVEL.strip().upper()
    if not configured:
        return logging.INFO

    level: int | str = logging._nameToLevel.get(configured)

    if not isinstance(level, int):
        print(f"Unknown LOG_LEVEL '{ENV.LOG_LEVEL}', falling back to INFO.", file=sys.stderr)
        return logging.INFO

    return level

def _handle_exception(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
    """
    Last resort hook for exceptions that reached the top of a thread or the interpreter.

    Ctrl-C is deliberately passed through to the default hook so an operator stopping the
    service by hand does not get a stack trace logged as a crash.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return

    logging.getLogger("cdn.unhandled").critical("Unhandled exception.", exc_info=(exc_type, exc, tb))


def _build_console_handler(level: int) -> StreamHandler:
    """
    Build the stdout handler. Colour is only used on a real terminal, so the escape codes
    never reach journald or a redirected log file.
    """
    handler = StreamHandler(stream=sys.stdout)
    handler.set_name("console")
    handler.setLevel(level)
    handler.setFormatter(
        _ConsoleFormatter(CONSOLE_FORMAT, DATE_FORMAT, use_color=sys.stdout.isatty())
    )

    return handler

def _build_file_handler(name: str, path: Path, level: int) -> TimedRotatingFileHandler:
    """
    Build a midnight rotating file handler keeping LOG_RETENTION_DAYS of history.

    Rotated files are suffixed with the day they cover (`daily_log.2026-08-03`), which is
    what makes them easy to hand to log shipping or to delete by hand.
    """
    handler = TimedRotatingFileHandler(
        filename=path, when="midnight", backupCount=ENV.LOG_RETENTION_DAYS, encoding="utf-8", utc=False
    )
    handler.set_name(name)
    handler.setLevel(level)
    handler.suffix = "%Y-%m-%d"
    handler.setFormatter(Formatter(FILE_FORMAT, datefmt=DATE_FORMAT))

    return handler


def setup() -> None:
    """
    Configure the root logger. Safe to call more than once, later calls do nothing.
    """

    # cnd root logger setup
    level: int = resolve_level()

    root_logger: Logger = logging.getLogger()
    root_logger.setLevel(level)
    sys.excepthook = _handle_exception


    root_logger.addHandler(_build_console_handler(level))
    log_dir = Path("logs")

    try:
        log_dir.mkdir(parents=True, exist_ok=True)

        root_logger.addHandler(_build_file_handler("daily", log_dir / "daily_log", level))
        root_logger.addHandler(_build_file_handler("error", log_dir / "error_log", logging.WARNING))

    except OSError as e:
        print(f"Could not open log files in '{log_dir}', logging to console only: {e}", file=sys.stderr)


    logger.info(f"Logging started at level {ENV.LOG_LEVEL.strip().upper()}, writing to logs.")
    logger.debug(f"Active handlers: {', '.join(h.get_name() for h in root_logger.handlers)}, retention {ENV.LOG_RETENTION_DAYS} days.")


