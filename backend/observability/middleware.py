"""ASGI middleware that mints/honours X-Request-ID and binds it to contextvars."""

from starlette.types import ASGIApp, Receive, Scope, Send

from .request_context import new_request_id, request_id_var


class RequestIdMiddleware:
    HEADER = b"x-request-id"

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = None
        for k, v in scope.get("headers", ()):
            if k == self.HEADER:
                incoming = v.decode("latin-1").strip()[:64] or None
                break
        rid = incoming or new_request_id()
        token = request_id_var.set(rid)

        async def send_wrapped(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", ()))
                headers.append((self.HEADER, rid.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapped)
        finally:
            request_id_var.reset(token)
