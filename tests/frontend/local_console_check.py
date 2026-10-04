"""Functional/E2E checks against this checkout's rebuilt, owned local installation.

No API mocks or inference. Session expiry/capacity faults affect only owned QA state.
"""

import argparse
import asyncio
import json
import sqlite3
import subprocess
import time
import uuid
from pathlib import Path

import httpx
from catalog_flows import catalog_flow
from local_console_state import snapshot
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from navigation import navigation
from playwright.sync_api import expect, sync_playwright

from agentgate.storage import credential_digest

ROOT = Path(__file__).resolve().parents[2]


def expire(context, base, database):
    cookie = next(
        c for c in context.cookies(base + "/admin/session") if c["name"] == "agentgate_operator"
    )
    with sqlite3.connect(database) as db:
        db.execute(
            "UPDATE operator_sessions SET expires_at=? WHERE digest=?",
            (time.time() - 1, credential_digest(cookie["value"])),
        )


def call(page, path, body=None):
    return page.evaluate(
        """async ({path, body}) => {
      const s = await (await fetch('/admin/session')).json();
      const r = await fetch(path, body === null ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf_token}, body:JSON.stringify(body)});
      return {status:r.status, data:await r.json()};
    }""",
        {"path": path, "body": body},
    )


def navigate(page, name):
    link = navigation(page).get_by_role("link", name=name, exact=False)
    link.focus()
    page.keyboard.press("Enter")
    expect(page.locator("#workspace")).to_be_focused()
    expect(page.locator("#view")).not_to_have_attribute("aria-busy", "true")


def run_action(page):
    button = page.get_by_role("button", name="Run governed action")
    expect(button).to_be_enabled()
    with page.expect_response(lambda r: r.url.endswith("/admin/playground")) as event:
        button.click()
    expect(page.locator(".result")).to_be_visible()
    expect(button).to_be_enabled()
    return event.value.json()


def no_credentials(page, state):
    expect(page.locator("#topbar-mode")).to_have_text("Local console / trusted computer")
    expect(page.locator("#topbar-mode")).to_be_visible()
    expect(page.get_by_label("Operator credential")).to_be_hidden()
    expect(page.get_by_role("button", name="Unlock console")).to_be_hidden()
    expect(page.get_by_role("button", name="Lock & sign out")).to_be_hidden()
    assert (
        page.evaluate("Object.keys(localStorage).length + Object.keys(sessionStorage).length") == 0
    )
    assert page.evaluate("document.cookie") == ""
    for path in state.glob("*.token"):
        token = path.read_text().strip()
        assert token not in page.content()
        assert not page.evaluate(
            "token => [...document.querySelectorAll('input,textarea')].some(el => el.value.includes(token))",
            token,
        )
    assert page.evaluate("window.credentialFlashed") is False


async def installed_mcp(base, state):
    # Real official-SDK HTTP/MCP integration; local console cookies confer no agent auth.
    token = (state / "client.token").read_text().strip()
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + token}, timeout=10) as http:
        async with streamable_http_client(base + "/mcp", http_client=http) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert {tool.name for tool in tools.tools} == {
                    "documents.read",
                    "memory.query",
                    "mail.send",
                }
                result = await session.call_tool(
                    "documents.read", {"document_id": "tenant-b-notes"}
                )
                assert result.is_error
                assert result.structured_content["executed"] is False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    descriptor = json.loads(args.descriptor.read_bytes())
    assert descriptor["source"] == str(ROOT) and descriptor["status"] == "running"
    base = descriptor["baseUrl"]
    state = Path(descriptor["stateDir"]) / "data"
    assert state == ROOT / ".runtime/qa-install/data"
    assert descriptor["consoleMode"] == "local"
    database = state / "agentgate.sqlite3"
    args.artifacts.mkdir(parents=True, exist_ok=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    preserved = (
        "operator_credentials",
        "credentials",
        "operator_credential_epochs",
        "credential_renewals",
    )
    authority_before = snapshot(database, preserved)
    startup_before = snapshot(
        database,
        (
            *preserved,
            "active_controls",
            "control_events",
            "budget_counters",
            "tool_actions",
            "tool_outbox",
            "audit_events",
        ),
    )
    tokens_before = {p.name: p.read_bytes() for p in state.glob("*.token")}
    counts = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
            )
            context.add_init_script("""window.credentialFlashed = false;
              new MutationObserver(() => {
                const input = document.querySelector('#credential');
                if (input && input.getClientRects().length) window.credentialFlashed = true;
              }).observe(document, {childList:true, subtree:true, attributes:true});""")
            page = context.new_page()
            errors = []
            writes = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda r: writes.append(r.url.removeprefix(base)) if r.method == "POST" else None,
            )
            started = time.monotonic()
            page.goto(base)
            expect(page.get_by_role("heading", name="Example conversations")).to_be_visible()
            startup_ms = round((time.monotonic() - started) * 1000)
            expect(page.locator("#console-mode")).to_be_visible()
            no_credentials(page, state)
            assert writes.count("/admin/session/bootstrap") == 1
            assert "/admin/hr/setup" not in writes and "/admin/hr/bind" not in writes
            navigate(page, "Overview")
            expect(page.get_by_role("heading", name="Service & controls")).to_be_visible()
            assert startup_before == snapshot(database, startup_before.keys())
            cookie = next(
                c
                for c in context.cookies(base + "/admin/session")
                if c["name"] == "agentgate_operator"
            )
            assert (
                cookie["httpOnly"] and cookie["sameSite"] == "Strict" and cookie["path"] == "/admin"
            )
            page.screenshot(path=str(args.artifacts / "overview.png"), full_page=True)
            page.reload()
            expect(page.get_by_role("heading", name="Service & controls")).to_be_visible()
            assert writes.count("/admin/session/bootstrap") == 1

            catalog_flow(
                page,
                lambda name: navigate(page, name),
                state,
                args.artifacts,
                console_mode="local",
            )
            no_credentials(page, state)
            assert authority_before == snapshot(database, preserved)
            navigate(page, "Playground")
            allowed = run_action(page)
            assert allowed["executed"] and allowed["decision"] == "allow"
            expect(page.locator(".result .tag")).to_have_text("allow")
            authority_before = snapshot(database, preserved)
            forbidden_before = snapshot(
                database, ("tool_outbox", "budget_counters", "tool_actions")
            )
            page.get_by_label("Example preset").select_option(label="Deny cross-tenant read")
            denied = run_action(page)
            assert denied["executed"] is False
            assert snapshot(database, forbidden_before.keys()) == forbidden_before
            expect(page.locator(".result .tag")).to_have_text("deny")
            expect(page.locator(".result")).to_contain_text("Execution is not confirmed")
            with sqlite3.connect(database) as db:
                assert not db.execute(
                    "SELECT 1 FROM audit_events WHERE event LIKE ? AND event LIKE ?",
                    (f'%"action_id":"{denied["action_id"]}"%', '%"executed":true%'),
                ).fetchall()

            # Pending mail is inert; expired approval is rejected before storage changes.
            page.get_by_role("button", name="Mail", exact=True).click()
            key = "local-qa-" + uuid.uuid4().hex
            page.get_by_label("Idempotency key", exact=True).fill(key)
            pending = run_action(page)
            assert pending["executed"] is False and pending["action_state"] == "pending"
            navigate(page, "Approvals")
            expect(page.get_by_role("heading", name="Approval inbox")).to_be_visible()
            card = page.locator(".approval").filter(has_text=pending["action_id"])
            # Existing UI uses one labelled review checkbox and explicit approve control.
            card.get_by_text("Review exact payload & authority", exact=True).click()
            card.get_by_label(
                "I reviewed the exact payload, identity, expiry and fingerprint."
            ).check()
            before = snapshot(
                database,
                (
                    "tool_actions",
                    "tool_outbox",
                    "budget_counters",
                    "active_controls",
                    "control_events",
                    "audit_events",
                ),
            )
            decision_path = f"/admin/approvals/{pending['action_id']}/decision"
            expire(context, base, database)
            with page.expect_response(lambda r: r.url.endswith(decision_path)) as event:
                card.get_by_role("button", name="Approve exact action").click()
            assert event.value.status == 401
            expect(page.get_by_text("Session restored.", exact=False)).to_be_visible()
            expect(page.get_by_role("heading", name="Approval inbox")).to_be_visible()
            assert writes.count(decision_path) == 1
            assert snapshot(database, before.keys()) == before
            card = page.locator(".approval").filter(has_text=pending["action_id"])
            card.get_by_text("Review exact payload & authority", exact=True).click()
            card.get_by_label(
                "I reviewed the exact payload, identity, expiry and fingerprint."
            ).check()
            card.get_by_role("button", name="Approve exact action").click()
            expect(card).to_contain_text("approved")
            with sqlite3.connect(database) as db:
                assert (
                    db.execute(
                        "SELECT decided_by FROM tool_actions WHERE action_id=?",
                        (pending["action_id"],),
                    ).fetchone()[0]
                    == "local-console"
                )
                assert (
                    db.execute(
                        "SELECT count(*) FROM tool_outbox WHERE action_id=?",
                        (pending["action_id"],),
                    ).fetchone()[0]
                    == 0
                )

            # Deliberate exact resumption adds one local outbox row; repeated keys cannot duplicate.
            navigate(page, "Playground")
            page.get_by_role("button", name="Mail", exact=True).click()
            page.get_by_label("Idempotency key", exact=True).fill(key)
            sent = run_action(page)
            assert sent["executed"] and sent["action_id"] == pending["action_id"]
            assert run_action(page)["result"] == sent["result"]
            navigate(page, "Test outbox")
            expect(page.get_by_role("heading", name="Local test outbox")).to_be_visible()
            with sqlite3.connect(database) as db:
                assert (
                    db.execute(
                        "SELECT count(*) FROM tool_outbox WHERE action_id=?",
                        (pending["action_id"],),
                    ).fetchone()[0]
                    == 1
                )

            # Each consequential mutation is attempted once; recovery restores read state only.
            for route, editor_label, path in [
                ("Policy studio", "Policy JSON", "/admin/policy/activate"),
                ("Threat feed", "Feed JSON", "/admin/feed"),
            ]:
                navigate(page, route)
                editor = page.get_by_label(editor_label, exact=True)
                candidate = json.loads(editor.input_value())
                editor.fill(json.dumps(candidate | {"revision": candidate["revision"] + 1}))
                page.get_by_role("button", name="Review activation").click()
                page.get_by_label("I reviewed this exact document.").check()
                before = snapshot(
                    database,
                    (
                        "active_controls",
                        "control_events",
                        "audit_events",
                        "tool_outbox",
                        "budget_counters",
                    ),
                )
                expire(context, base, database)
                with page.expect_response(lambda r, path=path: r.url.endswith(path)) as event:
                    page.get_by_role("button", name="Activate reviewed version").click()
                assert event.value.status == 401
                expect(page.get_by_text("Session restored.", exact=False)).to_be_visible()
                expect(page.get_by_label(editor_label, exact=True)).to_have_value(
                    json.dumps(candidate, indent=2)
                )
                assert writes.count(path) == 1
                assert snapshot(database, before.keys()) == before
            navigate(page, "Playground")
            expect(page.get_by_role("button", name="Run governed action")).to_be_enabled()
            before = snapshot(
                database, ("audit_events", "tool_outbox", "budget_counters", "tool_actions")
            )
            attempts = writes.count("/admin/playground")
            expire(context, base, database)
            with page.expect_response(lambda r: r.url.endswith("/admin/playground")) as event:
                page.get_by_role("button", name="Run governed action").click()
            assert event.value.status == 401
            expect(page.get_by_text("Session restored.", exact=False)).to_be_visible()
            expect(page.get_by_role("button", name="Run governed action")).to_be_enabled()
            assert writes.count("/admin/playground") == attempts + 1
            assert snapshot(database, before.keys()) == before
            assert "/admin/playground/credential/renew" not in writes

            navigate(page, "Security timeline")
            expect(page.get_by_label("Decision", exact=True)).to_be_visible()
            navigate(page, "Audit export")
            with page.expect_download() as download:
                page.get_by_role("button", name="Download audit page").click()
            assert '"trace_id"' in Path(download.value.path()).read_text()
            navigate(page, "Overview")
            for width in (390, 768):
                page.set_viewport_size({"width": width, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                no_credentials(page, state)
                page.screenshot(path=str(args.artifacts / f"overview-{width}.png"), full_page=True)
            # Cookie/session cannot authenticate the agent REST or MCP surfaces.
            for path, payload in [
                (
                    "/v1/actions/execute",
                    {"operation": "documents.read", "arguments": {"document_id": "tenant-a-notes"}},
                ),
                ("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            ]:
                result = context.request.post(base + path, data=payload)
                assert result.status == 401
            context.close()

            # Real bounded-session capacity failure: one bootstrap, sanitized UI, manual retry.
            fault_rows = []
            with sqlite3.connect(database) as db:
                existing = db.execute(
                    "SELECT count(*) FROM operator_sessions WHERE expires_at>?", (time.time(),)
                ).fetchone()[0]
                operator = db.execute(
                    "SELECT digest FROM operator_credentials WHERE id=1"
                ).fetchone()[0]
                for _ in range(32 - existing):
                    digest = credential_digest(uuid.uuid4().hex)
                    db.execute(
                        "INSERT INTO operator_sessions VALUES (?,?,?)",
                        (digest, operator, time.time() + 900),
                    )
                    fault_rows.append(digest)
            try:
                failure = browser.new_context()
                p = failure.new_page()
                failures = []
                p.on("request", lambda r: failures.append(r.url) if r.method == "POST" else None)
                p.goto(base)
                expect(p.get_by_role("button", name="Retry connection")).to_be_visible()
                expect(p.get_by_label("Operator credential")).to_be_hidden()
                expect(p.get_by_text("Cannot open the local console.", exact=False)).to_be_visible()
                assert len(failures) == 1 and failures[0].endswith("/admin/session/bootstrap")
                p.screenshot(path=str(args.artifacts / "startup-failure.png"), full_page=True)
                with sqlite3.connect(database) as db:
                    db.executemany(
                        "DELETE FROM operator_sessions WHERE digest=?",
                        [(digest,) for digest in fault_rows],
                    )
                p.get_by_role("button", name="Retry connection").press("Enter")
                expect(p.get_by_role("heading", name="Service & controls")).to_be_visible()
                assert len(failures) == 2
                assert all(url.endswith("/admin/session/bootstrap") for url in failures)
                failure.close()
            finally:
                with sqlite3.connect(database) as db:
                    db.executemany(
                        "DELETE FROM operator_sessions WHERE digest=?",
                        [(digest,) for digest in fault_rows],
                    )
            assert not errors, errors
            counts = {path: writes.count(path) for path in set(writes)}
        finally:
            browser.close()
    asyncio.run(installed_mcp(base, state))
    assert authority_before == snapshot(database, preserved)
    assert tokens_before == {p.name: p.read_bytes() for p in state.glob("*.token")}
    evidence = {
        "head": head,
        "base": base,
        "startup_ms": startup_ms,
        "post_counts": counts,
        "result": "PASS",
        "inference": "none",
        "outbox_action": pending["action_id"],
    }
    (args.artifacts / "results.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
