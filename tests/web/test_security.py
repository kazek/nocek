from fastapi.testclient import TestClient

from nocek.web.security import COOKIE
from tests.web.conftest import BASE, PORT, TOKEN


def test_reading_needs_no_token(stranger: TestClient) -> None:
    assert stranger.get("/api/health").status_code == 200


def test_changing_needs_the_token(stranger: TestClient, client: TestClient) -> None:
    refused = stranger.put("/api/settings", json={"sieve": False})
    allowed = client.put("/api/settings", json={"sieve": False})

    assert refused.status_code == 403
    assert refused.json()["error"] == "missing-token"
    assert allowed.status_code == 200


def test_a_wrong_token_is_refused(stranger: TestClient) -> None:
    stranger.cookies.set(COOKIE, "guessed")

    assert stranger.put("/api/settings", json={"sieve": False}).status_code == 403


def test_another_host_name_is_refused(client: TestClient) -> None:
    # DNS rebinding: a hostile name resolving to 127.0.0.1.
    response = client.get("/api/health", headers={"host": f"evil.example:{PORT}"})

    assert response.status_code == 403
    assert response.json()["error"] == "forbidden-host"


def test_localhost_is_this_server(client: TestClient) -> None:
    assert client.get("/api/health", headers={"host": f"localhost:{PORT}"}).status_code == 200


def test_another_origin_is_refused_even_with_the_cookie(client: TestClient) -> None:
    response = client.put(
        "/api/settings", json={"sieve": False}, headers={"origin": "https://evil.example"}
    )

    assert response.status_code == 403
    assert response.json()["error"] == "forbidden-origin"


def test_the_opening_address_hands_over_the_token(stranger: TestClient) -> None:
    response = stranger.get(f"/?token={TOKEN}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    cookie = response.headers["set-cookie"]
    assert f"{COOKIE}={TOKEN}" in cookie
    assert "samesite=strict" in cookie.lower()
    assert "httponly" in cookie.lower()


def test_a_wrong_opening_token_sets_nothing(stranger: TestClient) -> None:
    response = stranger.get("/?token=guessed", follow_redirects=False)

    assert "set-cookie" not in response.headers


def test_serves_the_page(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Nocek" in response.text
    assert BASE.startswith("http://127.0.0.1")
