import logging
import sys
from contextvars import ContextVar

ctx_request_id: ContextVar[str] = ContextVar("request_id", default="-")

class FallbackLoggerAdapter:
    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def _format_msg(self, msg: str, kwargs: dict) -> str:
        req_id = ctx_request_id.get()
        if req_id != "-":
            kwargs["request_id"] = req_id
        if kwargs:
            kw_str = " ".join(f"{k}={v}" for k, v in kwargs.items())
            return f"{msg} | {kw_str}"
        return msg

    def info(self, msg: str, *args, **kwargs):
        self._logger.info(self._format_msg(msg, kwargs), *args)

    def warning(self, msg: str, *args, **kwargs):
        self._logger.warning(self._format_msg(msg, kwargs), *args)

    def error(self, msg: str, *args, **kwargs):
        self._logger.error(self._format_msg(msg, kwargs), *args)

    def debug(self, msg: str, *args, **kwargs):
        self._logger.debug(self._format_msg(msg, kwargs), *args)

def get_logger(name: str = "granth"):
    try:
        import structlog
        return structlog.get_logger(name)
    except ImportError:
        base_logger = logging.getLogger(name)
        return FallbackLoggerAdapter(base_logger)

def configure_logging(log_level: str = "INFO"):
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout, level=level)
