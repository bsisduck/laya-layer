"""Owned installed HR/browser E2E with DB effects and a labelled HTTP provider fixture.

No shared inference. Teardown in finally stops only this checkout's QA/application.
The second phase runs the same installed CLI/wheel against a controlled provider.
"""

import json
import os
import secrets
import socket
import sqlite3
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
from fullstack_flows import api
from playwright.sync_api import expect, sync_playwright


def credential_digest(token):
    return sha256(token.encode()).hexdigest()


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / ".ai/qa/artifacts_hr"


@contextmanager
def isolated_qa_data():
    """Preserve this checkout's stopped QA ledger; each run gets fresh private data."""
    installation = ROOT / ".runtime/qa-install"
    descriptor = ROOT / ".ai/qa/test-env.json"
    if descriptor.exists():
        assert json.loads(descriptor.read_text())["source"] == str(ROOT)
    assert not installation.is_symlink()
    subprocess.run([str(ROOT / ".ai/scripts/test-env-down.sh")], cwd=ROOT, check=True)
    run_id = uuid.uuid4().hex
    data = installation / "data"
    previous = ROOT / f".runtime/hr-e2e-previous-{run_id}"
    assert not data.is_symlink()
    had_data = data.exists()
    if had_data:
        data.rename(previous)
    try:
        yield
    finally:
        try:
            subprocess.run([str(ROOT / ".ai/scripts/test-env-down.sh")], cwd=ROOT, check=True)
        finally:
            if data.exists():
                # Retain private audit/effect evidence; never reset a ledger for reruns.
                data.rename(ROOT / f".runtime/hr-e2e-evidence-{run_id}")
            if had_data:
                previous.rename(data)


def rows(database, table, action_id=None):
    with sqlite3.connect(database) as db:
        return db.execute(
            "SELECT count(*) FROM " + table + (" WHERE action_id=?" if action_id else ""),
            (action_id,) if action_id else (),
        ).fetchone()[0]


def snapshot(database):
    with sqlite3.connect(database) as db:
        return {
            t: db.execute("SELECT * FROM " + t).fetchall()
            for t in (
                "active_controls",
                "tool_outbox",
                "budget_counters",
                "tool_actions",
                "credentials",
                "delegated_bindings",
                "model_attempts",
            )
        }


def click(page, label, path):
    control = page.get_by_role("button", name=label, exact=True)
    expect(control).to_be_enabled()
    with page.expect_response(
        lambda r: r.url.endswith(path) and r.request.method == "POST"
    ) as event:
        control.press("Enter")
    data = event.value.json()
    page.wait_for_load_state("networkidle")
    return event.value.status, data


def navigate(page, name):
    control = page.get_by_role("navigation").get_by_role("link", name=name, exact=False)
    control.focus()
    page.keyboard.press("Enter")
    expect(page.locator("#workspace")).to_be_focused()
    expect(page.locator("#view")).not_to_have_attribute("aria-busy", "true")


def restore(admin, saved):
    session = admin.post("/admin/session/bootstrap", json={})
    headers = {"X-CSRF-Token": session.json()["csrf_token"]}
    current = admin.get("/admin/policy").json()
    result = admin.post(
        "/admin/policy/activate",
        headers=headers,
        json={
            "policy": saved | {"revision": current["policy"]["revision"] + 1},
            "expected_version": current["version"],
        },
    )
    assert result.status_code == 200, "Owned QA policy rollback failed"


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ProviderFixture(BaseHTTPRequestHandler):
    calls = []
    invalid = False

    def log_message(self, *args):
        pass

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).calls.append(data)
        raw = (
            b"invalid fixture response"
            if type(self).invalid
            else json.dumps(
                {
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "Fixture provider summary of the synthetic candidate. No real inference.",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
                }
            ).encode()
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(raw)


def run():
    os.umask(0o077)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    process = provider = browser = admin = pw = None
    saved = state = page = token_file = log = None
    result = {}
    try:
        subprocess.run(
            [str(ROOT / ".ai/scripts/test-env-up.sh"), "--force-rebuild", "--local-console"],
            cwd=ROOT,
            check=True,
        )
        descriptor = json.loads((ROOT / ".ai/qa/test-env.json").read_text())
        assert (
            descriptor["source"] == str(ROOT)
            and descriptor["startedByThisRepo"]
            and descriptor["consoleMode"] == "local"
        )
        state = Path(descriptor["stateDir"]) / "data"
        assert state == ROOT / ".runtime/qa-install/data"
        database = state / "agentgate.sqlite3"
        base = descriptor["baseUrl"]
        binary = Path(descriptor["stateDir"]) / "runtime/gateway/bin/agentgate"
        python = binary.with_name("python")
        imported = subprocess.check_output(
            [str(python), "-c", "import agentgate; print(agentgate.__file__)"], text=True
        ).strip()
        assert "site-packages" in imported and str(ROOT / "src") not in imported
        admin = httpx.Client(base_url=base, timeout=15, trust_env=False, headers={"Origin": base})
        session = admin.post("/admin/session/bootstrap", json={}).json()
        headers = {"X-CSRF-Token": session["csrf_token"]}
        saved = admin.get("/admin/policy").json()["policy"]
        # Explicit owned test fixture preparation: remove only this test's preset to exercise setup.
        baseline = json.loads(json.dumps(saved))
        if baseline.get("delegation"):
            baseline["delegation"]["profiles"] = [
                p
                for p in baseline["delegation"]["profiles"]
                if p["role_id"] not in ("HR-BP", "hr-assistant", "Dev", "Finance")
            ]
            baseline["delegation"]["required"] = [
                r for r in baseline["delegation"]["required"] if r["agent_id"] != "hr-assistant"
            ]
        baseline["documents_read"]["roles"] = [
            r for r in baseline["documents_read"]["roles"] if r != "hr-assistant"
        ]
        baseline["scoped_tools"]["mail_roles"] = [
            r for r in baseline["scoped_tools"]["mail_roles"] if r != "hr-assistant"
        ]
        baseline["revision"] += 1
        response = admin.post(
            "/admin/policy/activate",
            headers=headers,
            json={
                "policy": baseline,
                "expected_version": f"{saved['policy_id']}:{saved['revision']}",
            },
        )
        assert response.status_code == 200
        before_start = snapshot(database)
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
        )
        page = context.new_page()
        errors, writes = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "request",
            lambda r: writes.append(r.url.removeprefix(base)) if r.method == "POST" else None,
        )
        page.goto(base)
        expect(page.get_by_role("heading", name="Synthetic candidate workspace")).to_be_visible()
        expect(page.get_by_label("Operator credential")).to_be_hidden()
        assert snapshot(database) == before_start  # Opening only creates operator session.
        assert "/admin/hr/setup" not in writes and "/admin/hr/bind" not in writes
        page.get_by_role("button", name="Preview HR setup").press("Enter")
        expect(page.get_by_role("button", name="Activate reviewed HR setup")).to_be_visible()
        assert snapshot(database) == before_start
        click(page, "Activate reviewed HR setup", "/admin/hr/setup")
        expect(page.get_by_role("button", name="Start HR session", exact=True)).to_be_visible()
        _, binding = click(page, "Start HR session", "/admin/hr/bind")
        _, allowed = click(page, "Read selected source", "/admin/hr/read")
        assert allowed["executed"] and "Synthetic candidate" in allowed["result"]["content"]
        read_panel = page.locator("section.panel").filter(
            has=page.get_by_role("heading", name="2. Read / summarize", exact=True)
        )
        expect(read_panel.get_by_role("heading", name="Source decision")).to_be_visible()
        expect(read_panel).to_contain_text(allowed["result"]["content"])
        expect(page.locator(".hr-steps")).to_contain_text("Output released")
        effects = {
            t: rows(database, t) for t in ("tool_reservations", "tool_outbox", "model_attempts")
        }
        for label in ("HR private notes / agent excludes", "Finance record / human excludes"):
            page.get_by_label("Synthetic source").select_option(label=label)
            status, denied = click(page, "Read selected source", "/admin/hr/read")
            assert status == 403 and not denied["executed"]
            assert {t: rows(database, t) for t in effects} == effects
            expect(read_panel).to_contain_text("This operation was not dispatched")
        page.get_by_label("Synthetic source").select_option(
            label="Untrusted CV / benign injection test"
        )
        status, injection = click(page, "Read selected source", "/admin/hr/read")
        assert (
            status == 200 and injection["executed"]
        )  # Semantic off is honest, not hardcoded denial.
        page.get_by_label("Synthetic source").select_option(label="Synthetic candidate record")
        subject = "Installed HR " + uuid.uuid4().hex[:12]
        draft_panel = page.locator("section.panel").filter(
            has=page.get_by_role("heading", name="3. Draft / review follow-up", exact=True)
        )
        attempts = writes.count("/admin/hr/propose")
        for label, invalid, valid in (
            ("Message recipient", "", "candidate@demo.internal"),
            ("Message recipient", "invalid", "candidate@demo.internal"),
            ("Message subject", "   ", subject),
            ("Message content", "   ", "Synthetic local follow-up"),
        ):
            page.get_by_label(label).fill(invalid)
            page.get_by_role("button", name="Propose exact message").press("Enter")
            expect(page.get_by_label(label)).to_be_focused()
            expect(draft_panel.locator(".status.error")).to_be_visible()
            assert writes.count("/admin/hr/propose") == attempts
            page.get_by_label(label).fill(valid)
        page.get_by_label("Message subject").fill(subject)
        _, proposed = click(page, "Propose exact message", "/admin/hr/propose")
        action = proposed["action_id"]
        card = (
            page.locator("section.panel")
            .filter(
                has=page.get_by_role(
                    "heading", name="Review the exact proposed message", exact=True
                )
            )
            .last
        )
        expect(card).to_be_visible()
        for value in (
            "hr-local-employee",
            "hr-assistant",
            "candidate@demo.internal",
            "fixture outbox",
            "high",
            "consent expires",
        ):
            expect(card).to_contain_text(value)
        assert rows(database, "tool_outbox", action) == 0
        expect(draft_panel.locator(".hr-feedback")).to_contain_text("not dispatched")
        page.screenshot(path=str(ARTIFACTS / "exact-review.png"), full_page=True)
        page.get_by_label("I reviewed this exact recipient and content").check()
        click(page, "Approve exact message", f"/admin/approvals/{action}/decision")
        assert rows(database, "tool_outbox", action) == 0
        page.get_by_label("Message content").fill("Changed payload must conflict")
        status, mismatch = click(page, "Propose exact message", "/admin/hr/propose")
        assert (
            status == 409
            and not mismatch["executed"]
            and rows(database, "tool_outbox", action) == 0
        )
        click(page, "Resume approved message", "/admin/hr/resume")
        expect(page.get_by_role("button", name="Replay exact resume")).to_be_visible()
        assert rows(database, "tool_outbox", action) == 1
        expect(draft_panel).to_contain_text("Observed local outbox records for this action: 1")
        click(page, "Replay exact resume", "/admin/hr/resume")
        assert rows(database, "tool_outbox", action) == 1
        new_draft = page.get_by_role("button", name="Start new draft")
        expect(new_draft).to_be_enabled()
        new_draft.focus()
        new_draft.press("Enter")
        expect(page.get_by_label("Message recipient")).to_be_focused()
        expect(page.get_by_role("heading", name="Review the exact proposed message")).to_have_count(
            0
        )
        _, next_proposed = click(page, "Propose exact message", "/admin/hr/propose")
        assert next_proposed["action_id"] != action and not next_proposed["executed"]
        assert rows(database, "tool_outbox", next_proposed["action_id"]) == 0
        assert rows(database, "tool_outbox", action) == 1
        page.get_by_role("link", name="Open action audit trace", exact=False).last.click()
        expect(page.get_by_label("Filter loaded events")).not_to_have_value("")

        navigate(page, "HR workspace")
        expect(page.get_by_role("button", name="Start a new HR session")).to_be_visible()
        for width in (390, 768):
            page.set_viewport_size({"width": width, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(ARTIFACTS / f"hr-{width}.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
        assert (
            page.evaluate("Object.keys(localStorage).length + Object.keys(sessionStorage).length")
            == 0
        )
        click(page, "End HR session", "/admin/hr/end")
        for label in (
            "End HR session",
            "Read selected source",
            "Request model summary",
            "Propose exact message",
        ):
            expect(page.get_by_role("button", name=label, exact=True)).to_be_disabled()
        click(page, "Start HR session", "/admin/hr/bind")
        # Expiry fault is private owned QA data; no protected mutation replay.
        with sqlite3.connect(database) as db:
            db.execute(
                "UPDATE credentials SET expires_at=? WHERE authority_kind='delegated' AND json_extract(identity,'$.principal_id')='hr-demo-account'",
                (time.time() - 1,),
            )
        frozen = snapshot(database)
        status, expired = click(page, "Read selected source", "/admin/hr/read")
        assert status == 410 and "binding expired" in expired["detail"]
        assert snapshot(database) == frozen
        page.reload()
        expect(page.get_by_role("button", name="Start HR session", exact=True)).to_be_visible()
        assert snapshot(database) == frozen
        # Session recovery drops the handle and never retries the interrupted proposal.
        _, old_binding = click(page, "Start HR session", "/admin/hr/bind")
        cookie = next(
            c for c in context.cookies(base + "/admin/session") if c["name"] == "agentgate_operator"
        )
        with sqlite3.connect(database) as db:
            db.execute(
                "UPDATE operator_sessions SET expires_at=? WHERE digest=?",
                (time.time() - 1, credential_digest(cookie["value"])),
            )
        frozen = snapshot(database)
        attempts = writes.count("/admin/hr/propose")
        status, _ = click(page, "Propose exact message", "/admin/hr/propose")
        assert status == 401
        expect(page.get_by_role("button", name="Start HR session", exact=True)).to_be_visible()
        assert writes.count("/admin/hr/propose") == attempts + 1 and snapshot(database) == frozen
        assert not errors, errors
        result["product"] = {
            "outbox_action": action,
            "outbox_rows": 1,
            "injection_decision": injection["decision"],
            "inference": "not run",
            "installed_module": imported,
        }
        context.close()
        # Stop the real product supervisor before using that same installed wheel.
        subprocess.run([str(ROOT / ".ai/scripts/test-env-down.sh")], cwd=ROOT, check=True)
        admin.close()
        admin = None
        provider = ThreadingHTTPServer(("127.0.0.1", 0), ProviderFixture)
        threading.Thread(target=provider.serve_forever, daemon=True).start()
        token_file = state / ("hr-qa-upstream-" + uuid.uuid4().hex + ".token")
        token_file.write_text(secrets.token_urlsafe(32))
        gateway_port = port()
        base = f"http://127.0.0.1:{gateway_port}"
        log = (ARTIFACTS / "installed-fixture-gateway.log").open("wb")
        process = subprocess.Popen(
            [
                str(binary),
                "--state-dir",
                str(state),
                "serve",
                "--policy",
                str(state / "policy.yaml"),
                "--port",
                str(gateway_port),
                "--local-console",
                "--model-url",
                f"http://127.0.0.1:{provider.server_port}/v1",
                "--model-token-file",
                str(token_file),
            ],
            cwd=ROOT,
            stdout=log,
            stderr=log,
        )
        admin = httpx.Client(base_url=base, timeout=15, trust_env=False, headers={"Origin": base})
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                if admin.get("/health/ready").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            raise AssertionError("Installed fixture gateway failed to start")
        second = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = second.new_page()
        # Install before navigation so the binding's expiry timer belongs to this clock.
        page.clock.install()
        page.goto(base)
        expect(page.get_by_role("button", name="Start HR session", exact=True)).to_be_visible()
        frozen = snapshot(database)
        restarted = api(
            page,
            "/admin/hr/read",
            {"handle": old_binding["handle"], "resource": "hr-candidate-001"},
        )
        assert restarted["status"] == 410 and snapshot(database) == frozen
        _, fresh_binding = click(page, "Start HR session", "/admin/hr/bind")
        status, summary = click(page, "Request model summary", "/admin/hr/summary")
        assert (
            status == 200
            and "Fixture provider summary"
            in summary["completion"]["choices"][0]["message"]["content"]
        )
        assert (
            len(ProviderFixture.calls) == 1
            and ProviderFixture.calls[0]["messages"][-1]["role"] == "tool"
        )
        expect(page.get_by_role("heading", name="Provider summary")).to_be_visible()
        expect(page.get_by_role("link", name="Open model audit trace", exact=False)).to_have_count(
            1
        )
        expect(page.get_by_role("link", name="Open source audit trace", exact=False)).to_have_count(
            1
        )
        page.screenshot(path=str(ARTIFACTS / "fixture-summary.png"), full_page=True)
        ProviderFixture.invalid = True
        status, failure = click(page, "Request model summary", "/admin/hr/summary")
        assert status == 503 and failure["decision"] == "deny" and "completion" not in failure
        expect(page.get_by_text(failure["reason_codes"][0], exact=True)).to_be_visible()
        expect(page.get_by_role("heading", name="Provider summary")).to_have_count(0)
        expect(
            page.get_by_text(
                "The protected operation ran, but its output was withheld.", exact=False
            )
        ).to_be_visible()
        result["fixture_provider"] = {
            "calls": len(ProviderFixture.calls),
            "source_role": "tool",
            "failed_output_withheld": True,
            "real_inference": False,
        }
        with sqlite3.connect(database) as db:
            attribution = db.execute(
                "SELECT accounting_principal,attribution FROM model_attribution"
            ).fetchall()
            assert len(attribution) == 2
            assert all(
                owner == "hr-demo-account" and json.loads(record)["department"] == "HR"
                for owner, record in attribution
            )
            assert db.execute("SELECT count(*) FROM model_settlement").fetchone()[0] == 1
            first, last = db.execute(
                "SELECT min(created_at),max(created_at) FROM model_attempts"
            ).fetchone()
        page.get_by_role("link", name="Measured usage →", exact=True).click()
        usage = page.locator(".department-usage-panel")
        expect(usage.get_by_role("heading", name="Department model usage")).to_be_visible()
        # The expiry test clock is independent of server reservation time. Select
        # the actual fixture attempts' UTC period instead of the browser's default.
        expect(usage.get_by_role("button", name="Load usage")).to_be_enabled()
        usage.get_by_label("UTC start", exact=True).fill(
            time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(int(first) - 1))
        )
        usage.get_by_label("UTC end", exact=True).fill(
            time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(int(last) + 1))
        )
        usage.get_by_role("button", name="Load usage").click()
        expect(usage.get_by_role("row").filter(has_text="local_demo")).to_have_count(1)
        navigate(page, "HR workspace")
        result["department_consumer"] = {
            "attributed_hr_attempts": 2,
            "known_settlements": 1,
            "accepted_usage_link": True,
        }
        # Move close to expiry with no request pending; cross it within the API deadline.
        remaining = fresh_binding["expires_at"] * 1000 - page.evaluate("Date.now()")
        page.clock.fast_forward(max(0, int(remaining - 5000)))

        def expire_during_read(route):
            expect(page.get_by_label("Synthetic source")).to_be_disabled()
            expect(page.locator(".hr-steps")).not_to_contain_text("Output released")
            response = route.fetch()
            assert response.status == 200  # Actual authorized release, held before browser receipt.
            page.clock.fast_forward(6000)
            expect(
                page.get_by_role("button", name="Read selected source", exact=True)
            ).to_be_disabled()
            route.fulfill(response=response)

        page.route("**/admin/hr/read", expire_during_read)
        status, release = click(page, "Read selected source", "/admin/hr/read")
        assert status == 200 and release["executed"]
        for label in (
            "Read selected source",
            "Request model summary",
            "Propose exact message",
            "End HR session",
        ):
            expect(page.get_by_role("button", name=label, exact=True)).to_be_disabled()
        expect(
            page.locator(".hr-identity")
            .locator("..")
            .get_by_text("HR session expired. Old approvals cannot transfer.", exact=False)
        ).to_be_visible()
        restore(admin, saved)
        assert (
            admin.get("/admin/policy").json()["policy"] | {"revision": saved["revision"]} == saved
        )
        result["rollback"] = (
            "active policy restored at newer revision; durable audit/outbox retained"
        )
        saved = None
        assert rows(database, "tool_outbox", action) == 1
        second.close()
        browser.close()
        browser = None
        token_file.unlink()
        log.close()
        result["head"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        result["result"] = "PASS"
        (ARTIFACTS / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
    except Exception:
        if page is not None and not page.is_closed():
            page.screenshot(path=str(ARTIFACTS / "failure.png"), full_page=True)
        raise
    finally:
        try:
            if admin is not None and saved is not None:
                restore(admin, saved)
        finally:
            if admin is not None:
                admin.close()
            if browser is not None:
                browser.close()
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if provider is not None:
                provider.shutdown()
                provider.server_close()
            if pw is not None:
                pw.stop()
            if token_file is not None:
                token_file.unlink(missing_ok=True)
            if log is not None:
                log.close()
            subprocess.run([str(ROOT / ".ai/scripts/test-env-down.sh")], cwd=ROOT, check=True)


def main():
    os.umask(0o077)
    with isolated_qa_data():
        run()


if __name__ == "__main__":
    main()
