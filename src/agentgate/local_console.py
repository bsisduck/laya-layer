"""Explicit trusted-host capability; browser origins do not identify a person."""

from urllib.parse import urlsplit

from fastapi import Request


def validate_local_console(origin: str, serving_address: tuple[str, int] | None) -> None:
    if serving_address is None:
        raise ValueError("Local console requires an explicit loopback serving address")
    host, port = serving_address
    if host not in ("127.0.0.1", "::1") or type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Local console requires a literal loopback binding and port")
    authority = f"[{host}]" if host == "::1" else host
    parsed = urlsplit(origin)
    if parsed.scheme not in ("http", "https") or origin != f"{parsed.scheme}://{authority}:{port}":
        raise ValueError("Local console origin must exactly match its loopback binding")


def local_request(request: Request, origin: str, serving_address: tuple[str, int]) -> bool:
    # Check the actual ASGI socket address too, so a remote bind cannot be enabled
    # merely by supplying a loopback Host. Proxy headers must never rewrite it.
    return (
        tuple(request.scope.get("server") or ()) == serving_address
        and request.scope.get("scheme") == urlsplit(origin).scheme
        and not any(
            key.lower() == b"forwarded" or key.lower().startswith(b"x-forwarded-")
            for key, _ in request.scope["headers"]
        )
    )
