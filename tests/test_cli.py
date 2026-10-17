import json
import logging
import socket
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from nocek import __version__
from nocek.cli import DEFAULT_PORT, HOST, HideToken, build_parser, free_port, main, running
from nocek.shortcut import DesktopEntry


def test_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_defaults() -> None:
    args = build_parser().parse_args([])

    assert args.port == DEFAULT_PORT == 6475
    assert not args.no_browser


def test_takes_the_next_port_when_one_is_taken() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind((HOST, 0))
        port = taken.getsockname()[1]

        assert free_port(port) != port


def test_the_token_never_reaches_the_log() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1", "GET", "/?token=s3cret&x=1", "1.1", 303),
        None,
    )

    HideToken().filter(record)

    assert "s3cret" not in record.getMessage()
    assert "/?token=…&x=1" in record.getMessage()


@pytest.mark.skipif(sys.platform == "win32", reason="TIME_WAIT behaves differently on Windows")
def test_a_port_just_released_by_a_server_is_free_again() -> None:
    # A server that served a request and stopped leaves its port in TIME_WAIT.
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, 0))
    server.listen()
    port = server.getsockname()[1]
    client = socket.create_connection((HOST, port))
    accepted, _ = server.accept()
    accepted.close()  # the server side closes first, so it holds TIME_WAIT
    server.close()
    client.close()

    assert free_port(port) == port


def test_finds_a_nocek_already_running(client_port: int) -> None:
    assert running(client_port)


def test_nothing_running_on_a_free_port() -> None:
    assert not running(free_port(DEFAULT_PORT + 100))


def test_a_second_start_opens_the_first(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr("nocek.cli.running", lambda port: True)
    monkeypatch.setattr("nocek.cli.setup_logging", lambda: None)
    monkeypatch.setattr("nocek.cli.settings.token", lambda: "t0ken")
    monkeypatch.setattr("webbrowser.open", opened.append)
    monkeypatch.setattr("nocek.cli.serve", lambda *a, **k: pytest.fail("second server"))

    assert main([]) == 0
    assert opened == [f"http://{HOST}:{DEFAULT_PORT}/?token=t0ken"]


def test_the_shortcut_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    made = DesktopEntry(tmp_path / "nocek.desktop", Path("/usr/bin/python3"))
    monkeypatch.setattr("nocek.shortcut.for_this_system", lambda: made)

    assert main(["shortcut"]) == 0
    assert made.path.exists()
    assert main(["shortcut", "--remove"]) == 0
    assert not made.path.exists()


@pytest.fixture
def client_port() -> Iterator[int]:
    """A stand-in Nocek answering /api/health."""

    class Health(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = json.dumps({"version": __version__}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer((HOST, 0), Health)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
