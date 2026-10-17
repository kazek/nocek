"""Keeping other web pages away from the local server.

The server listens on the loopback address only, but any page open in the
user's browser can still send it requests. Two checks stop that:

  * the Host header must name this server, which defeats DNS rebinding, where
    a hostile name is made to resolve to 127.0.0.1;
  * a request that changes anything must carry the access token, which the
    browser receives once in the address the application opens and keeps as
    a strict same-site cookie. Another site's page cannot read it, and the
    browser does not send it with that page's requests.
"""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from nyctalus.web.errors import error_response

COOKIE = "nyctalus_token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def own_hosts(port: int) -> set[str]:
    return {f"127.0.0.1:{port}", f"localhost:{port}"}


class Guard(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, token: str, port: int) -> None:
        super().__init__(app)
        self.token = token
        self.hosts = own_hosts(port)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.headers.get("host") not in self.hosts:
            return error_response(403, "forbidden-host")
        if request.method not in SAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and origin.removeprefix("http://") not in self.hosts:
                return error_response(403, "forbidden-origin")
            if not self.valid(request.cookies.get(COOKIE)):
                return error_response(403, "missing-token")
        return await call_next(request)

    def valid(self, presented: str | None) -> bool:
        return presented is not None and hmac.compare_digest(presented, self.token)
