"""Logging helpers for distlift (including a custom TRACE level)."""

import logging

TRACE = 5
logging.addLevelName(TRACE, "TRACE")


def configure_logging(verbose: bool) -> None:
    """Configure root logging for CLI runs.

    Args:
        verbose: When True, set the root level to DEBUG and distlift loggers
            to TRACE; otherwise use INFO on the root logger.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(levelname)s %(name)s: %(message)s",
        level=level,
    )

    # Allow deeper tracing inside distlift when the user passes --verbose
    if verbose:
        logging.getLogger("distlift").setLevel(TRACE)


def get_logger(name: str) -> logging.Logger:
    """Return a standard library logger for ``name``.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.
    """
    return logging.getLogger(name)
