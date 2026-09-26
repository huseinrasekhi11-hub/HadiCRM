"""
ETag middleware for conditional GET requests.
On slow mobile connections, unchanged payloads are answered with
304 Not Modified (empty body) instead of re-transmitting JSON.
"""
import hashlib

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp


def _apply_auth_vary(request: Request, headers: dict) -> None:
    """
    SECURITY: responses of authenticated GETs are user-specific. Without
    an explicit `Vary: Authorization`, an intermediate cache/proxy could
    reuse one user's ETagged CRM payload for a different bearer identity.
    Existing Vary values (e.g. `Origin` added by CORSMiddleware) are kept.
    """
    if not request.headers.get("authorization"):
        return
    values = [v.strip() for v in headers.get("vary", "").split(",") if v.strip()]
    if "authorization" not in [v.lower() for v in values]:
        values.append("authorization")
    headers["vary"] = ", ".join(values)


class ETagMiddleware(BaseHTTPMiddleware):
    MAX_BODY = 64 * 1024  # only hash reasonably small JSON payloads

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        if request.method != "GET" or response.status_code != 200:
            return response

        # Decide BEFORE buffering. Previously every 200 GET — including a
        # 20 MB attachment download — was read fully into memory just to
        # discover it exceeded MAX_BODY. Only small JSON payloads are hashed.
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("application/json"):
            return response
        content_length = response.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > self.MAX_BODY:
            return response

        body_chunks = []
        async for chunk in response.body_iterator:
            body_chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
        body = b"".join(body_chunks)

        if not body or len(body) > self.MAX_BODY:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        etag = '"' + hashlib.md5(body).hexdigest() + '"'
        if request.headers.get("if-none-match") == etag:
            # Preserve headers added by inner middleware (notably the CORS
            # headers: CORSMiddleware runs inside this one, and a 304
            # without Access-Control-Allow-Origin breaks browser caching).
            # Entity headers describing the (now absent) body are dropped.
            preserved = {
                k: v
                for k, v in response.headers.items()
                if k.lower() not in {"content-type", "content-length"}
            }
            preserved["ETag"] = etag
            _apply_auth_vary(request, preserved)
            return Response(status_code=304, headers=preserved)

        headers = dict(response.headers)
        headers["ETag"] = etag
        _apply_auth_vary(request, headers)
        return Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )
