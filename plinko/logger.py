"""Module handling internal and dependency logging."""
import logging

import logzero

from plinko.config import PLINKO_DATA_DIR


def setup_logzero(level="info", path="logs/plinko.log"):
    # plinko_path = Path(os.environ.get("PLINKO_DIRECTORY", "")).absolute()
    path = PLINKO_DATA_DIR.joinpath(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    log_fmt = "%(color)s[%(levelname)s %(asctime)s]%(end_color)s %(message)s"
    if level == "debug":
        level = logging.DEBUG
        log_fmt = (
            "%(color)s[%(levelname)1.1s %(asctime)s %(module)s:%(lineno)d]"
            "%(end_color)s %(message)s"
        )
    elif level == "info":
        level = logging.INFO
    elif level == "warning":
        level = logging.WARNING
    elif level == "error":
        level = logging.ERROR
    elif level == "critical":
        level = logging.CRITICAL

    formatter = logzero.LogFormatter(fmt=log_fmt)
    logzero.setup_default_logger(formatter=formatter)
    logzero.loglevel(level)
    logzero.logfile(
        str(path), loglevel=level, maxBytes=1e9, backupCount=3, formatter=formatter
    )


setup_logzero()
