"""Command-line entry point.

The application is used through the browser; the command line only starts it.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import socket
import sys
import urllib.request
import webbrowser
from collections.abc import Sequence
from logging.handlers import RotatingFileHandler

from nocek import __version__
from nocek.storage import settings

DEFAULT_PORT = 6475  # B-A-T-S on a phone keypad
HOST = "127.0.0.1"

log = logging.getLogger("nocek")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nocek",
        description="Identify bats from ultrasonic recordings.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"port to listen on (default {DEFAULT_PORT}; the next free one if taken)",
    )
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser")
    commands = parser.add_subparsers(dest="command", metavar="command")
    shortcut = commands.add_parser(
        "shortcut", help="add Nocek to the system's menu, to start it without a terminal"
    )
    shortcut.add_argument("--remove", action="store_true", help="remove the shortcut instead")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "shortcut":
        return make_shortcut(remove=args.remove)
    setup_logging()
    if running(args.port):
        # Started again, from a shortcut say: show the one already running.
        log.info("Nocek is already running at http://%s:%d", HOST, args.port)
        if not args.no_browser:
            webbrowser.open(f"http://{HOST}:{args.port}/?token={settings.token()}")
        return 0
    serve(free_port(args.port), open_browser=not args.no_browser)
    return 0


def make_shortcut(remove: bool) -> int:
    from nocek import shortcut

    made = shortcut.for_this_system()
    try:
        if remove:
            print(f"Removed {made.path}" if made.remove() else f"There was no {made.path}")
        else:
            made.create()
            print(f"Nocek can now be started from {made.path}")
    except (OSError, shortcut.ShortcutError) as error:
        print(f"Could not {'remove' if remove else 'make'} the shortcut: {error}", file=sys.stderr)
        return 1
    return 0


def running(port: int) -> bool:
    """Whether Nocek already answers on this port."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/health", timeout=1) as response:
            return "version" in json.loads(response.read())
    except (OSError, ValueError):
        return False


def serve(port: int, open_browser: bool) -> None:
    import uvicorn

    from nocek.web.app import create_app
    from nocek.web.state import AppState

    token = settings.token()
    state = AppState(settings.config_dir() / "settings.json", token, port)
    address = f"http://{HOST}:{port}/?token={token}"

    class Server(uvicorn.Server):
        async def startup(self, sockets: list[socket.socket] | None = None) -> None:
            await super().startup(sockets)
            log.info("Nocek is running at http://%s:%d", HOST, port)
            if open_browser:
                webbrowser.open(address)

    def stop_server() -> None:
        log.info("Quit from the interface")
        server.should_exit = True

    try:
        app = create_app(state, on_quit=stop_server)
        server = Server(uvicorn.Config(app, host=HOST, port=port, log_config=None))
        server.run()
    finally:
        state.close()


def free_port(wanted: int, attempts: int = 20) -> int:
    """The wanted port, or the first free one after it.

    Tested the way the server will bind it: with SO_REUSEADDR, so a port
    still holding connections from a server that just stopped counts as
    free, as it is to the server. (On Windows that option would let a port
    in use be taken over, so there it is left off.)
    """
    for port in range(wanted, wanted + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if sys.platform != "win32":
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((HOST, port))
            except OSError:
                continue
            return port
    raise SystemExit(f"no free port between {wanted} and {wanted + attempts - 1}")


class HideToken(logging.Filter):
    """Keep the access token out of the log: the opening address carries it."""

    PATTERN = re.compile(r"token=[^&\s\"]+")

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.PATTERN.sub("token=…", str(record.msg))
        if record.args:
            record.args = tuple(
                self.PATTERN.sub("token=…", a) if isinstance(a, str) else a
                for a in (record.args if isinstance(record.args, tuple) else (record.args,))
            )
        return True


def setup_logging() -> None:
    folder = settings.log_dir()
    folder.mkdir(parents=True, exist_ok=True)
    file = RotatingFileHandler(folder / "nocek.log", maxBytes=1_000_000, backupCount=3)
    file.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handlers: list[logging.Handler] = [file]
    if sys.stderr is not None:  # started without a console, as pythonw does, there is none
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(message)s"))
        handlers.append(console)
    for handler in handlers:
        handler.addFilter(HideToken())
    logging.basicConfig(level=logging.INFO, handlers=handlers, force=True)
