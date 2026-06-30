"""Shared logging setup — imported by both bgc_web (Python 3.12) and
bgc_worker (Python 3.7), so this module must stay Python 3.7-compatible."""
import logging
import sys
import time

logging.Formatter.converter = time.gmtime  # timestamps in UTC

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s UTC [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

logger = logging.getLogger("plantbgc")