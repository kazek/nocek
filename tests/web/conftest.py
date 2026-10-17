from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nocek.web.app import create_app
from nocek.web.security import COOKIE
from nocek.web.state import AppState

PORT = 6475
TOKEN = "test-token"
BASE = f"http://127.0.0.1:{PORT}"


@pytest.fixture
def app_state(tmp_path: Path) -> Iterator[AppState]:
    state = AppState(tmp_path / "config" / "settings.json", TOKEN, PORT)
    yield state
    state.close()


@pytest.fixture
def client(app_state: AppState) -> TestClient:
    """A browser that has been given the token, as the application's own page is."""
    c = TestClient(create_app(app_state), base_url=BASE)
    c.cookies.set(COOKIE, TOKEN)
    return c


@pytest.fixture
def stranger(app_state: AppState) -> TestClient:
    """A browser without the token: another web page sending requests."""
    return TestClient(create_app(app_state), base_url=BASE)
