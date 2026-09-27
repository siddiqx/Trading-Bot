"""Structured logging setup for the Forex Live Signal Bot."""

import logging
import sys
from typing import Optional


class SecretFilter(logging.Filter):
    """Filter to ensure tokens, webhook secrets, and private keys never leak to logs."""

    def __init__(self, secrets_to_mask: Optional[list] = None):
        super().__init__()
        self.secrets_to_mask = [s for s in (secrets_to_mask or []) if s and len(s) > 4]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for sec in self.secrets_to_mask:
            if sec in msg:
                record.msg = str(record.msg).replace(sec, "[REDACTED_SECRET]")
        return True


def setup_logger(name: str = "forex_signal_bot") -> logging.Logger:
    """Configure and return application logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        logger.propagate = False
    return logger


logger = setup_logger()
