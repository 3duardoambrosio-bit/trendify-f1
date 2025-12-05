import logging
import json
import sys
from typing import Dict, Any
from infra.settings import settings


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "module": record.module,
            "function": record.funcName,
            "message": record.getMessage(),
        }

        # Add extra fields if they exist
        if hasattr(record, "extra_data"):
            log_entry.update(getattr(record, "extra_data"))

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging() -> None:
    log_level_name = settings.get("logging.level", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    log_format = settings.get("logging.format", "json")

    if log_format == "json":
        formatter: logging.Formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    logging.basicConfig(level=log_level, handlers=[handler])


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
