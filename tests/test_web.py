"""The public shell contains no operator data and cannot shadow API routes."""

import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentgate.web_routes import WEB_ROOT, attach_web_routes


@pytest.fixture
def web_client():
    app = FastAPI()
    attach_web_routes(app)
    return TestClient(app)


def test_shell_and_assets_are_local_with_restrictive_headers(web_client):
    response = web_client.get("/")
    assert response.status_code == 200
    assert '<script type="module" src="/static/app.js">' in response.text
    assert "https://" not in response.text
    for name in [
        "",
        *[f"static/{p.name}" for p in WEB_ROOT.iterdir() if p.suffix in {".js", ".css"}],
    ]:
        result = web_client.get("/" + name)
        assert result.status_code == 200
        assert result.headers["cache-control"] == "no-store"
        assert "frame-ancestors 'none'" in result.headers["content-security-policy"]
        assert "unsafe-inline" not in result.headers["content-security-policy"]
        assert result.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    "path",
    [
        "/admin/session",
        "/static/../app.py",
        "/static/%2e%2e%2fapp.py",
        "/static/index.html",
        "/static/.env",
        "/unknown",
    ],
)
def test_shell_does_not_expose_source_or_mask_missing_routes(web_client, path):
    assert web_client.get(path).status_code == 404


def test_browser_modules_parse_and_avoid_executable_content_sinks():
    for path in WEB_ROOT.glob("*.js"):
        subprocess.run(["node", "--check", str(path)], check=True, capture_output=True)
        source = path.read_text()
        for forbidden in (
            "innerHTML",
            "outerHTML",
            "insertAdjacentHTML",
            "localStorage",
            "sessionStorage",
            "eval(",
            "new Function(",
        ):
            assert forbidden not in source, (path.name, forbidden)


def test_assets_in_wheel_and_source_distribution(tmp_path):
    import tarfile
    import zipfile

    subprocess.run(["uv", "build", "--out-dir", str(tmp_path)], check=True, capture_output=True)
    required = {f"agentgate/web/{path.name}" for path in WEB_ROOT.iterdir() if path.is_file()}
    with zipfile.ZipFile(next(tmp_path.glob("*.whl"))) as wheel:
        assert required <= set(wheel.namelist())
    with tarfile.open(next(tmp_path.glob("*.tar.gz"))) as archive:
        names = {name.split("/src/", 1)[-1] for name in archive.getnames()}
        assert required <= names


def test_frontend_request_and_state_contracts():
    subprocess.run(["node", "--test", "tests/frontend/contracts.mjs"], check=True)
