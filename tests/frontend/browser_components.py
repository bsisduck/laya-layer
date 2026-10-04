"""Mocked browser API-consumer tests; never enforcement or model evidence."""

import argparse
import json
import time
from urllib.parse import parse_qs, urlsplit

from navigation import navigation
from playwright.sync_api import expect, sync_playwright

from agentgate.policy import Policy
from agentgate.tool_catalog import catalog_document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        calls = []
        held = []
        state = {
            "overview": 200,
            "delay": True,
            "approved": False,
            "empty": False,
            "credential": "active",
            "epoch": 0,
            "catalog": "ready",
        }
        hostile = '<img src=x onerror="window.injected=true">'
        catalog = catalog_document(Policy(policy_id="component", revision=1), "d" * 64)
        catalog["tools"][0]["description"] = hostile
        row = {
            "action_id": "action-fixture",
            "tenant_id": "tenant-a",
            "operation": "mail.send",
            "principal_id": "demo",
            "root_run_id": "root",
            "payload": {
                "recipient": "test@demo.internal",
                "subject": hostile,
                "body": "Synthetic body",
                "idempotency_key": "same-key",
            },
            "fingerprint": "a" * 64,
            "payload_digest": "b" * 64,
            "policy_digest": "c" * 64,
            "registry_digest": "d" * 64,
            "policy_version": "demo:1",
            "expires_at": time.time() + 600,
            "created_at": time.time(),
            "state": "pending",
            "reason": "APPROVAL_REQUIRED",
            "decided_by": None,
        }

        def handle(route):
            request = route.request
            url = urlsplit(request.url)
            body = request.post_data_json if request.post_data else None
            calls.append((url.path, request.method, body, request.headers, parse_qs(url.query)))
            code = 200
            data = {}
            if url.path == "/admin/config":
                data = {"mode": "credential"}
            elif url.path == "/admin/session":
                data = {
                    "authenticated": True,
                    "csrf_token": "component-nonce",
                    "expires_at": time.time() + 600,
                }
            elif url.path == "/admin/overview":
                if state["delay"]:
                    held.append(route)
                    return
                code = state["overview"]
                data = (
                    {"detail": "Component outage"}
                    if code != 200
                    else {
                        "counts": {"allow": 7, "deny": 3, "pending": None},
                        "services": {"gateway": "ready"},
                        "coverage": {"test": "mocked component response"},
                    }
                )
            elif url.path == "/admin/approvals":
                data = {"approvals": [] if state["empty"] else [row]}
            elif url.path == "/admin/department-usage":
                data = {
                    "version": 1,
                    "source": "model-attempt-evidence-v1",
                    "departments": [],
                    "totals": {"attempts": 0},
                    "window": {"start": int(time.time()) - 3600, "end": int(time.time())},
                    "completeness": {"status": "complete"},
                }
            elif url.path == "/admin/catalog":
                if state["catalog"] == "loading":
                    held.append(route)
                    return
                if state["catalog"] == "unavailable":
                    code, data = 503, {"detail": "Catalog outage"}
                elif state["catalog"] == "missing":
                    data = {"version": "old"}
                elif state["catalog"] == "empty":
                    data = catalog | {"tools": []}
                else:
                    data = catalog
            elif url.path.endswith("/decision"):
                state["approved"] = bool(body["approve"])
                data = {
                    "status": "approved",
                    "decision": "require_approval",
                    "action_state": "approved",
                    "executed": False,
                    "reason_codes": ["APPROVAL_APPROVED"],
                    "trace_id": "component-trace",
                }
            elif url.path == "/admin/playground/credential":
                data = {
                    "scope": parse_qs(url.query)["scope"][0],
                    "state": state["credential"],
                    "epoch": state["epoch"],
                    "expires_at": time.time() + 600,
                }
            elif url.path == "/admin/playground/credential/renew":
                assert body == {"scope": "tools", "expected_epoch": 0}
                state["credential"] = "active"
                state["epoch"] = 1
                data = {
                    "scope": "tools",
                    "state": "active",
                    "epoch": 1,
                    "expires_at": time.time() + 600,
                }
            elif url.path == "/admin/playground":
                if body["mode"] == "model":
                    code = 503
                    data = {"detail": "Model service unavailable"}
                else:
                    data = {
                        "status": "pending_approval",
                        "decision": "require_approval",
                        "executed": False,
                        "action_state": "pending",
                        "action_id": "action-fixture",
                    }
            elif url.path == "/admin/outbox":
                data = {"messages": []}
            elif url.path == "/admin/events":
                data = {"events": []}
            else:
                code, data = 404, {"detail": "Not installed"}
            route.fulfill(status=code, content_type="application/json", body=json.dumps(data))

        page.route("**/admin/**", handle)
        page.goto(args.url.rstrip("/") + "/#overview")
        expect(page.get_by_text("Loading operator state…")).to_be_visible()
        expect(page.locator("#view")).to_have_attribute("aria-busy", "true")
        assert held
        state["delay"] = False
        held.pop().fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"counts": {"allow": 7}, "services": {"gateway": "ready"}}),
        )
        expect(page.get_by_role("heading", name="Service & controls")).to_be_visible()
        expect(page.locator(".stat.allow strong")).to_have_text("7")
        expect(page.locator(".stat.deny strong")).to_have_text("—")
        sections = page.get_by_role("group", name="Overview sections")
        expect(sections.get_by_role("link")).to_have_count(4)
        sections.get_by_role("link", name="Department usage", exact=True).press("Enter")
        expect(page.get_by_role("heading", name="Department model usage")).to_be_visible()
        expect(page.get_by_text("No model attempts in this tenant", exact=False)).to_be_visible()
        totals = page.locator("details").filter(
            has=page.get_by_text("Inspect zero/unknown totals", exact=True)
        )
        expect(totals).not_to_have_attribute("open", "")
        expect(totals.locator(".kv")).to_be_hidden()
        evidence = page.locator('[aria-label="Measured department evidence"]')
        assert (
            evidence.locator(":scope > :first-child").inner_text().startswith("No model attempts")
        )
        page.get_by_text("Inspect zero/unknown totals", exact=True).press("Enter")
        expect(totals.locator(".kv")).to_be_visible()
        expect(totals).to_contain_text("selected attempts")
        expect(totals).to_contain_text("Unknown")
        assert page.get_by_role("heading", name="Resource ledger").count() == 0
        expect(sections.get_by_role("link", name="Department usage", exact=True)).to_have_attribute(
            "aria-current", "page"
        )
        assert page.url.endswith("#overview?section=usage")
        expect(
            page.locator("nav").get_by_role(
                "link", name="Department usage", exact=True, include_hidden=True
            )
        ).to_have_attribute("aria-current", "page")
        sections.get_by_role("link", name="Standards evidence", exact=True).press("Enter")
        expect(
            page.get_by_role("heading", name="Standards controls, evidence and gaps")
        ).to_be_visible()
        assert page.get_by_role("heading", name="Department model usage").count() == 0
        page.go_back()
        expect(page.get_by_role("heading", name="Department model usage")).to_be_visible()
        page.go_back()
        expect(page.get_by_role("heading", name="Service & controls")).to_be_visible()
        page.goto(args.url.rstrip("/") + "/#overview?section=standards")
        expect(
            page.get_by_role("heading", name="Standards controls, evidence and gaps")
        ).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

        def navigate(name):
            navigation(page).get_by_role("link", name=name, exact=False).click()

        state["catalog"] = "loading"
        with page.expect_request(lambda request: request.url.endswith("/admin/catalog")):
            navigate("Catalog")
        expect(page.get_by_text("Loading operator state…")).to_be_visible()
        expect(page.locator("#view")).to_have_attribute("aria-busy", "true")
        assert held
        held.pop().fulfill(status=200, content_type="application/json", body=json.dumps(catalog))
        expect(page.get_by_role("heading", name="Approved tool catalog")).to_be_visible()
        expect(page.get_by_text("Exact human approval required", exact=True)).to_be_visible()
        expect(page.get_by_text("Automatic after hard authorization", exact=True)).to_have_count(2)
        expect(page.get_by_text(hostile, exact=True)).to_be_visible()
        assert page.locator("#view img").count() == 0 and page.evaluate("window.injected") is None
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        for mode, outcome in [
            ("missing", "Catalog metadata is unavailable or incompatible."),
            ("empty", "No implemented tools reported"),
            ("unavailable", "Service unavailable."),
        ]:
            state["catalog"] = mode
            page.get_by_role("button", name="Refresh").click()
            expect(page.get_by_text(outcome, exact=False)).to_be_visible()
            assert page.get_by_role("heading", name="mail.send", exact=True).count() == 0

        navigate("Playground")
        page.get_by_role("button", name="Mail", exact=True).click()
        key = page.get_by_label("Idempotency key").input_value()
        payload = page.get_by_label("Action payload · JSON").input_value()
        page.get_by_role("button", name="Run governed action").click()
        expect(page.locator(".result")).to_contain_text("Execution is not confirmed")
        navigate("Approvals")
        page.get_by_text("Review exact payload & authority", exact=True).press("Enter")
        expect(page.get_by_label("Exact immutable mail payload")).to_contain_text(
            json.dumps(hostile)[1:-1]
        )
        assert page.locator("#view img").count() == 0
        assert page.evaluate("window.injected") is None
        approve = page.get_by_role("button", name="Approve exact action")
        expect(approve).to_be_disabled()
        page.get_by_label("I reviewed the exact payload", exact=False).check()
        approve.click()
        expect(page.locator(".result")).to_contain_text("APPROVAL_APPROVED")
        expect(page.locator(".result")).to_contain_text("Execution is not confirmed")
        decision = next(call for call in calls if call[0].endswith("/decision"))
        assert decision[2] == {"tenant_id": "tenant-a", "fingerprint": "a" * 64, "approve": True}
        assert decision[3]["x-csrf-token"] == "component-nonce"
        listing = next(call for call in calls if call[0] == "/admin/approvals")
        assert listing[4] == {"tenant_id": ["tenant-a"], "limit": ["100"]}
        navigate("Playground")
        expect(page.get_by_role("button", name="Mail", exact=True)).to_have_attribute(
            "aria-pressed", "true"
        )
        expect(page.get_by_label("Idempotency key")).to_have_value(key)
        expect(page.get_by_label("Action payload · JSON")).to_have_value(payload)
        page.get_by_role("button", name="Run governed action").click()
        expect(page.locator(".result")).to_be_visible()
        mail = [call[2] for call in calls if call[0] == "/admin/playground"]
        assert mail[0] == mail[1]
        page.get_by_role("button", name="Model", exact=True).click()
        page.get_by_role("button", name="Run governed action").click()
        expect(page.get_by_text("Service unavailable.", exact=False)).to_be_visible()
        assert page.locator(".result").count() == 0
        state["credential"] = "expired"
        page.get_by_role("button", name="Document", exact=True).click()
        expect(page.get_by_role("button", name="Run governed action")).to_be_disabled()
        expect(page.get_by_role("button", name="Renew expired credential")).to_be_visible()
        page.get_by_role("button", name="Renew expired credential").click()
        expect(page.get_by_role("button", name="Run governed action")).to_be_enabled()
        expect(page.get_by_text("Credential renewed.", exact=False)).to_be_visible()
        renewal = next(call for call in calls if call[0].endswith("/renew"))
        assert renewal[3]["x-csrf-token"] == "component-nonce"
        state["credential"] = "revoked"
        page.get_by_role("button", name="Memory", exact=True).click()
        expect(page.get_by_role("button", name="Run governed action")).to_be_disabled()
        expect(page.get_by_text("This authority was revoked", exact=False)).to_be_visible()
        assert page.get_by_role("button", name="Renew expired credential").count() == 0
        navigate("Test outbox")
        expect(page.get_by_text("No messages recorded", exact=False)).to_be_visible()
        navigate("Security timeline")
        expect(page.get_by_text("No matching events", exact=False)).to_be_visible()
        state["empty"] = True
        navigate("Approvals")
        expect(page.get_by_text("No approval records", exact=False)).to_be_visible()
        state["overview"] = 503
        navigate("Overview")
        expect(page.get_by_text("Service unavailable.", exact=False)).to_be_visible()
        assert page.locator(".stat").count() == 0
        state["overview"] = 401
        page.get_by_role("button", name="Refresh").click()
        expect(page.locator("#console")).to_be_hidden()
        assert page.locator("#view").inner_text() == ""
        assert not errors, errors
        browser.close()
    print(
        "PASS: MOCKED browser consumers: catalog loading/missing/empty/503/XSS/mobile, loading/empty/401/503, exact approvals, mail draft/key retry, XSS text rendering, mobile controls. No backend execution proof."
    )


if __name__ == "__main__":
    main()
