"""Loopback CLI/HTTP integration; uses only the shipped synthetic document executor."""

import json
import socket
import subprocess
import sys
import time
from contextlib import contextmanager

import httpx

from agentgate.documents import demo_documents


def command(state, *arguments):
    return subprocess.run(
        [sys.executable, "-m", "agentgate.cli", "--state-dir", str(state), *arguments],
        check=False,
        capture_output=True,
        timeout=15,
    )


@contextmanager
def server(state, port):
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "agentgate.cli",
            "--state-dir",
            str(state),
            "serve",
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=1) as probe:
            while time.monotonic() < deadline:
                assert process.poll() is None, "Gateway exited before readiness"
                try:
                    if probe.get("/health/ready").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.02)
            else:
                raise AssertionError("Gateway readiness deadline")
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_cli_operator_http_activation_export_and_restart(tmp_path):
    state = tmp_path / "state"
    assert command(state, "init-demo").returncode == 0
    bootstrap = command(state, "init-operator")
    assert bootstrap.returncode == 0
    operator = (state / "operator.token").read_text()
    agent = (state / "client.token").read_text()
    assert operator not in bootstrap.stdout.decode()
    assert command(state, "init-operator").returncode == 1
    assert (state / "operator.token").read_text() == operator
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    document = demo_documents()[0].metadata.document_id
    with httpx.Client(base_url=origin, trust_env=False, timeout=3) as client:
        with server(state, port):
            assert (
                client.post(
                    "/admin/session", headers={"Origin": origin}, json={"token": agent}
                ).status_code
                == 401
            )
            login = client.post(
                "/admin/session", headers={"Origin": origin}, json={"token": operator}
            )
            assert login.status_code == 200
            assert "Secure" not in login.headers["set-cookie"]  # Local HTTP mode only.
            headers = {"Origin": origin, "X-CSRF-Token": login.json()["csrf_token"]}
            result = client.post(
                "/admin/playground",
                headers=headers,
                json={"mode": "document", "document_id": document},
            )
            assert result.status_code == 200
            assert result.json()["executed"] is True
            policy = client.get("/admin/policy").json()
            next_policy = policy["policy"] | {"revision": policy["policy"]["revision"] + 1}
            assert (
                client.post(
                    "/admin/policy/activate",
                    headers=headers,
                    json={"policy": next_policy, "expected_version": policy["version"]},
                ).status_code
                == 200
            )
            feed = {
                "feed_id": "local",
                "revision": 2,
                "indicators": [
                    {
                        "id": "live-denial",
                        "kind": "literal_text",
                        "value": document,
                        "stages": ["tool_action"],
                    }
                ],
            }
            assert (
                client.post(
                    "/admin/feed",
                    headers=headers,
                    json={"feed": feed, "expected_version": "local:1"},
                ).status_code
                == 200
            )
            denial = client.post(
                "/admin/playground",
                headers=headers,
                json={"mode": "document", "document_id": document},
            )
            assert denial.status_code == 403
            assert denial.json()["executed"] is False
            assert denial.json()["reason_codes"] == ["THREAT_FEED_BLOCKED"]
            events = client.get("/admin/events").json()
            related = [e for e in events["events"] if e["action_id"] == denial.json()["action_id"]]
            assert [e["event_type"] for e in related] == ["action_denied"]
            assert related[0]["feed_version"] == "local:2"
            exported = client.get("/admin/audit/export", params={"tenant": "tenant-a"})
            assert exported.status_code == 200
            assert len(exported.text.splitlines()) == 3
            assert json.loads(exported.headers["x-agentgate-cursor"])["has_more"] is False
        with server(state, port):
            assert client.get("/admin/session").status_code == 200
            assert client.get("/admin/feed").json()["version"] == "local:2"
            assert client.get("/admin/policy").json()["policy"] == next_policy
            denial = client.post(
                "/admin/playground",
                headers=headers,
                json={"mode": "document", "document_id": document},
            )
            assert denial.status_code == 403
            assert denial.json()["executed"] is False
            assert client.delete("/admin/session", headers=headers).status_code == 200
            assert client.get("/admin/session").status_code == 401
