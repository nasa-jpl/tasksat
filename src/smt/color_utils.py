"""
Terminal color utilities for TaskSAT output.

Provides cross-platform ANSI color codes for enhanced terminal output.
"""

import sys
import os


class Colors:
    """ANSI color codes for terminal output."""

    # Check if colors should be enabled
    # Disable colors if NO_COLOR env var is set, or if not a TTY
    _enabled = (
        not os.environ.get('NO_COLOR') and
        sys.stdout.isatty()
    )

    # Color codes
    RED = '\033[91m' if _enabled else ''
    GREEN = '\033[92m' if _enabled else ''
    YELLOW = '\033[93m' if _enabled else ''
    BLUE = '\033[94m' if _enabled else ''
    MAGENTA = '\033[95m' if _enabled else ''
    CYAN = '\033[96m' if _enabled else ''
    WHITE = '\033[97m' if _enabled else ''

    # Styles
    BOLD = '\033[1m' if _enabled else ''
    DIM = '\033[2m' if _enabled else ''
    RESET = '\033[0m' if _enabled else ''

    # Semantic colors
    ERROR = RED
    SUCCESS = GREEN
    WARNING = YELLOW
    INFO = CYAN
    HEADER = BOLD + BLUE


def color_text(text: str, color: str) -> str:
    """Wrap text with color codes."""
    if not Colors._enabled:
        return text
    return f"{color}{text}{Colors.RESET}"


def error(text: str) -> str:
    """Format text as an error (red)."""
    return color_text(text, Colors.ERROR)


def success(text: str) -> str:
    """Format text as success (green)."""
    return color_text(text, Colors.SUCCESS)


def warning(text: str) -> str:
    """Format text as warning (yellow)."""
    return color_text(text, Colors.WARNING)


def info(text: str) -> str:
    """Format text as info (cyan)."""
    return color_text(text, Colors.INFO)


def header(text: str) -> str:
    """Format text as header (bold blue)."""
    return color_text(text, Colors.HEADER)


def bold(text: str) -> str:
    """Format text as bold."""
    return color_text(text, Colors.BOLD)


def dim(text: str) -> str:
    """Format text as dim."""
    return color_text(text, Colors.DIM)
