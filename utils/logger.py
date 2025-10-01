import logging
import sys


_configured = False


def configure_logging(level: int | None = None) -> None:
    global _configured
    if _configured:
        return

    log_level = level if level is not None else logging.INFO

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(log_level)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.addHandler(handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


