"""Command-line entry point.

The application is used through the browser; the command line only starts it.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from nyctalus import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nyctalus",
        description="Identify bats from ultrasonic recordings.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0
