"""Public, credential-free operator shell; admin APIs own authorization."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

WEB_ROOT = Path(__file__).with_name("web")
HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
        "connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'; object-src 'none'"
    ),
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def attach_web_routes(app: FastAPI) -> None:
    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(WEB_ROOT / "index.html", headers=HEADERS)

    @app.get("/static/{name}", include_in_schema=False)
    def asset(name: str) -> FileResponse:
        # Flat allowlist: never serve Python, credentials, dotfiles, or arbitrary paths.
        if name not in {path.name for path in WEB_ROOT.iterdir() if path.suffix in {".css", ".js"}}:
            raise HTTPException(404)
        media_type = "text/javascript" if name.endswith(".js") else "text/css"
        return FileResponse(WEB_ROOT / name, media_type=media_type, headers=HEADERS)
