import logging
import socket
import sys

import pytest

from nyctalus import __version__
from nyctalus.cli import DEFAULT_PORT, HOST, HideToken, build_parser, free_port, main


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
