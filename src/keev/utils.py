import logging
import os
from typing import Any, Dict, Optional
import orjson
from datetime import datetime

COLORS = {
    'RESET': '\033[0m',
    'RED': '\033[31m',
    'GREEN': '\033[32m',
    'YELLOW': '\033[33m',
    'BLUE': '\033[34m',
    'MAGENTA': '\033[35m',
    'CYAN': '\033[36m',
    'WHITE': '\033[37m',
    'BOLD': '\033[1m'
}

class ColoredFormatter(logging.Formatter):
    level_colors = {
        logging.DEBUG: COLORS['BLUE'],
        logging.INFO: COLORS['GREEN'],
        logging.WARNING: COLORS['YELLOW'],
        logging.ERROR: COLORS['RED'] + COLORS['BOLD'],
        logging.CRITICAL: COLORS['RED'] + COLORS['BOLD']
    }

    def format(self, record):
        # Add color to level name
        level_color = self.level_colors.get(record.levelno, COLORS['RESET'])
        colored_level = f"{level_color}{record.levelname}{COLORS['RESET']}"

        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        colored_timestamp = f"{COLORS['CYAN']}{timestamp}{COLORS['RESET']}"

        # Format name
        colored_name = f"{COLORS['MAGENTA']}{record.name}{COLORS['RESET']}"

        # Build message
        message = f"{colored_timestamp} [{colored_level}] {colored_name}: {record.getMessage()}"

        # Add method and path if available
        if hasattr(record, 'method'):
            message = f"{message} [{COLORS['YELLOW']}{record.method}{COLORS['RESET']}]"
        if hasattr(record, 'path'):
            message = f"{message} {COLORS['CYAN']}{record.path}{COLORS['RESET']}"

        # Add exception info if available
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            message = f"{message}\n{COLORS['RED']}{record.exc_text}{COLORS['RESET']}"

        return message

def setup_logging(level: int = logging.INFO) -> None:
    """Set up logging with colored output"""
    root_logger = logging.getLogger("keev")
    if root_logger.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(ColoredFormatter())
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name"""
    if not name.startswith("keev."):
        name = f"keev.{name}"
    logger = logging.getLogger(name)
    if not logger.handlers and not logger.parent.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(ColoredFormatter())
        logger.addHandler(handler)
    return logger

def validate_type(value: Any, expected_type: type, name: str) -> None:
    """Validate that a value is of the expected type"""
    if not isinstance(value, expected_type):
        raise TypeError(f"{name} must be of type {expected_type.__name__}")

def merge_dicts(dict1: Dict, dict2: Dict) -> Dict:
    """Merge two dictionaries"""
    return {**dict1, **dict2}

def get_env_var(name: str, default: Optional[str] = None) -> str:
    """Get an environment variable with optional default"""
    value = os.getenv(name, default)
    if value is None:
        raise ValueError(f"Environment variable {name} is required")
    return value

def json_dumps(data: Any) -> bytes:
    """Convert data to JSON bytes using orjson"""
    return orjson.dumps(data)

def json_loads(data: bytes) -> Any:
    """Parse JSON bytes using orjson"""
    return orjson.loads(data)