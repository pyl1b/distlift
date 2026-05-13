import logging

TRACE = 5
logging.addLevelName(TRACE, "TRACE")


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(levelname)s %(name)s: %(message)s",
        level=level,
    )
    if verbose:
        logging.getLogger("distlift").setLevel(TRACE)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
