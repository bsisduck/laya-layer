"""Mocked operations/menu/inbox presentation against installed wheel assets; no inference."""

import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, default=Path(".ai/qa/test-env.json"))
    parser.add_argument("--artifacts", type=Path, default=Path(".ai/qa/artifacts_workspace"))
    args = parser.parse_args()
    descriptor = json.loads(args.descriptor.read_text())
    assert descriptor["status"] == "running" and descriptor["startedByThisRepo"]
    base = descriptor["baseUrl"]
    args.artifacts.mkdir(parents=True, exist_ok=True)
    state = {"summary": 200, "activity": 200, "hold": False}
    held, calls, errors, scenarios = [], [], [], []
    summary = {
        "counts": {"allow": 7, "deny": 2, "redact": 1, "pending": 4},
        "count_window": {
            "scope": "latest terminal events",
            "audit_rows": 50,
            "limit": 1000,
            "pending_scope": "all unexpired pending records",
        },
        "coverage": {"pending_approvals": 4},
        "services": {"gateway": "ready", "mcp": "enabled", "semantic": "unknown"},
    }
    approval = {
        "action_id": "workspace-action-fixture",
        "state": "pending",
        "operation": "mail.send",
        "tenant_id": "tenant-a",
        "principal_id": "fixture-owner",
        "root_run_id": "fixture-root",
        "authority": {
            "human_subject": "fixture-human",
            "provenance": "local_demo",
            "department": "HR",
        },
        "expires_at": time.time() + 600,
        "fingerprint": "f" * 64,
        "payload": {
            "recipient": "synthetic@demo.internal",
            "subject": "Synthetic review",
            "body": "<img src=x onerror=alert(1)>",
        },
    }

    def handle(route):
        path = urlsplit(route.request.url).path
        calls.append(
            (
                path,
                route.request.method,
                route.request.post_data_json if route.request.post_data else None,
            )
        )
        code, data = 200, {}
        if path == "/admin/config":
            data = {"mode": "local"}
        elif path in ("/admin/session", "/admin/session/bootstrap"):
            data = {
                "authenticated": True,
                "csrf_token": "mock-workspace-nonce",
                "expires_at": time.time() + 600,
            }
        elif path == "/admin/overview":
            if state["hold"]:
                held.append(route)
                return
            code, data = (
                state["summary"],
                summary if state["summary"] == 200 else {"detail": "Summary fixture unavailable"},
            )
        elif path == "/admin/events":
            code = state["activity"]
            data = (
                {
                    "events": [
                        {
                            "trace_id": "fixture-trace",
                            "operation": "documents.read",
                            "event_type": "dispatch_intent",
                            "decision": "allow",
                            "executed": False,
                            "timestamp": time.time(),
                        }
                    ]
                }
                if code == 200
                else {"detail": "Activity fixture unavailable"}
            )
        elif path == "/admin/policy":
            data = {"version": "fixture:1", "policy": {"revision": 1}}
        elif path == "/admin/approvals":
            data = {"approvals": [approval]}
        elif path.endswith("/decision"):
            data = {"decision": "allow", "executed": False, "reason_codes": ["APPROVAL_APPROVED"]}
        route.fulfill(status=code, content_type="application/json", body=json.dumps(data))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
        # Deliver an actual native media change after opening the mobile drawer.
        # Holding the callback makes the otherwise intermittent ordering deterministic.
        page.add_init_script("""(() => {
            window.__deferMenuResize = false;
            window.__pendingMenuResize = [];
            const nativeMatchMedia = window.matchMedia.bind(window);
            window.matchMedia = query => {
                const media = nativeMatchMedia(query);
                if (query !== '(max-width: 760px)') return media;
                const add = media.addEventListener.bind(media);
                media.addEventListener = (type, listener, options) => add(type, event => {
                    const deliver = () => listener.call(media, event);
                    if (window.__deferMenuResize) window.__pendingMenuResize.push(deliver);
                    else deliver();
                }, options);
                return media;
            };
        })();""")
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/admin/**", handle)
        try:
            page.goto(base)
            expect(page.get_by_role("heading", name="Recent audit activity")).to_be_visible()
            expect(page.get_by_role("link", name="Operations", exact=True)).to_have_attribute(
                "aria-current", "page"
            )
            expect(page.locator(".stat.pending strong")).to_have_text("4")
            expect(page.get_by_text("Global · all unexpired records")).to_be_visible()
            expect(page.get_by_text("enabled", exact=True)).to_be_visible()
            expect(page.get_by_text("unknown", exact=True)).to_have_count(2)
            expect(page.get_by_text("dispatch intent", exact=True)).to_be_visible()
            assert "Healthy" not in page.locator("#view").inner_text()
            assert page.get_by_role("heading", name="Department model usage").count() == 0
            assert page.locator(".threat-ladder").count() == 0
            assert page.get_by_role("navigation").locator(".nav-group").count() == 3
            for name in ["Review approvals · tenant-a", "Open HR workbench"]:
                box = page.get_by_role("link", name=name, exact=False).bounding_box()
                assert box["y"] + box["height"] < 900
            scenarios.append(
                "default operations, truthful statuses/global backlog and lifecycle stages"
            )

            state["summary"] = 503
            page.get_by_role("button", name="Refresh").click()
            expect(page.get_by_text("Operations summary unavailable.", exact=False)).to_be_visible()
            expect(page.get_by_text("dispatch intent", exact=True)).to_be_visible()
            assert page.locator(".stat").count() == 0
            page.screenshot(
                path=str(args.artifacts / "overview-summary-error-1440.png"), full_page=True
            )
            state["summary"], state["activity"] = 200, 503
            page.get_by_role("button", name="Refresh").click()
            expect(page.locator(".stat.allow strong")).to_have_text("7")
            expect(page.get_by_text("Recent activity unavailable.", exact=False)).to_be_visible()
            page.screenshot(
                path=str(args.artifacts / "overview-activity-error-1440.png"), full_page=True
            )
            state["activity"], state["hold"] = 200, True
            page.get_by_role("button", name="Refresh").click()
            expect(page.locator("#view")).to_have_attribute("aria-busy", "true")
            page.locator("nav").get_by_role("link", name="Approvals", exact=True).click()
            expect(page.get_by_role("heading", name="Approval inbox")).to_be_visible()
            held.pop().fulfill(status=200, json=summary)
            expect(page.get_by_role("heading", name="Approval inbox")).to_be_visible()
            assert page.get_by_role("heading", name="Service & controls").count() == 0
            state["hold"] = False
            scenarios.append("partial overview errors, loading and late-response navigation")

            review = page.get_by_text("Review exact payload & authority", exact=True)
            expect(page.get_by_label("Exact immutable mail payload")).to_be_hidden()
            review.press("Enter")
            expect(page.get_by_label("Exact immutable mail payload")).to_be_visible()
            for value in ["fixture-human", "fixture-owner", "f" * 64, "fixture-root"]:
                expect(page.locator(".approval-review")).to_contain_text(value)
            assert page.locator("#view img").count() == 0
            approve = page.get_by_role("button", name="Approve exact action")
            expect(approve).to_be_disabled()
            page.get_by_role("checkbox").check()
            page.screenshot(path=str(args.artifacts / "approval-expanded-1440.png"), full_page=True)
            approve.press("Enter")
            expect(page.locator(".approval")).to_contain_text("Decision returned")
            decisions = [call for call in calls if call[0].endswith("/decision")]
            assert len(decisions) == 1 and decisions[0][2] == {
                "tenant_id": "tenant-a",
                "fingerprint": "f" * 64,
                "approve": True,
            }
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(args.artifacts / "approval-expanded-390.png"), full_page=True)
            scenarios.append("progressive exact approval details and consent-bound payload")

            opener = page.get_by_role("button", name="Open navigation", exact=True)
            opener.press("Enter")
            dialog = page.get_by_role("dialog", name="Navigation menu")
            expect(dialog).to_be_visible()
            expect(page.locator(".main-shell")).to_have_attribute("inert", "")
            first = dialog.get_by_role("link", name="Laya Sec Layer overview", exact=True)
            first.focus()
            first.press("Shift+Tab")
            expect(dialog.get_by_role("link", name="Playground", exact=True)).to_be_focused()
            page.keyboard.press("Tab")
            expect(first).to_be_focused()
            page.screenshot(path=str(args.artifacts / "menu-390.png"))
            page.keyboard.press("Escape")
            expect(opener).to_be_focused()
            expect(page.locator(".main-shell")).not_to_have_attribute("inert", "")
            opener.press("Enter")
            page.locator("#nav-backdrop").click(position={"x": 370, "y": 400})
            expect(opener).to_be_focused()
            opener.press("Enter")
            dialog.get_by_role("link", name="Approvals", exact=True).press("Enter")
            expect(page.locator("#workspace")).to_be_focused()
            expect(opener).to_have_attribute("aria-expanded", "false")
            opener.press("Enter")
            page.set_viewport_size({"width": 1440, "height": 900})
            expect(page.locator("#navigation-rail")).to_be_visible()
            expect(page.locator("#navigation-rail")).not_to_have_attribute("role", "dialog")
            expect(page.locator(".main-shell")).not_to_have_attribute("inert", "")
            scenarios.append("mobile menu focus trap, Escape, backdrop, same hash and resize")

            page.evaluate("window.__deferMenuResize = true")
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_function("() => window.__pendingMenuResize.length === 1")
            opener.press("Enter")
            expect(dialog).to_be_visible()
            page.evaluate("""() => {
                window.__deferMenuResize = false;
                window.__pendingMenuResize.splice(0).forEach(deliver => deliver());
            }""")
            expect(dialog).to_be_visible()
            expect(opener).to_have_attribute("aria-expanded", "true")
            expect(page.locator(".main-shell")).to_have_attribute("inert", "")
            expect(dialog.get_by_role("button", name="Close navigation")).to_be_focused()
            page.screenshot(path=str(args.artifacts / "menu-delayed-resize-390.png"))
            dialog.get_by_role("link", name="Policy studio").press("Enter")
            expect(page.get_by_label("Policy JSON")).to_be_visible()
            expect(page.locator("#workspace")).to_be_focused()
            page.set_viewport_size({"width": 1440, "height": 900})
            expect(page.locator("#navigation-rail")).not_to_have_attribute("hidden", "")
            scenarios.append(
                "delayed native resize preserves the newly opened drawer and Policy link"
            )

            for route, active in [
                ("overview?section=standards", "Standards evidence"),
                ("overview?section=unknown", "Overview"),
                ("unknown", "Overview"),
            ]:
                page.goto(base + "/#" + route)
                expect(page.locator("#view")).not_to_have_attribute("aria-busy", "true")
                current = page.locator("nav a[aria-current=page]")
                expect(current).to_have_count(1)
                expect(current).to_have_text(active)
            page.locator("nav").get_by_role("link", name="Approvals", exact=True).click()
            expect(page.get_by_role("heading", name="Approval inbox")).to_be_visible()
            page.go_back()
            expect(page.get_by_role("heading", name="Recent audit activity")).to_be_visible()
            page.set_viewport_size({"width": 390, "height": 844})
            opener.press("Enter")
            dialog.get_by_role("link", name="Policy studio").press("Enter")
            editor = page.get_by_label("Policy JSON")
            expect(editor).to_be_visible()
            editor.fill('{"revision": 2}')
            page.once("dialog", lambda event: event.dismiss())
            opener.press("Enter")
            with page.expect_event("dialog") as discard:
                dialog.get_by_role("link", name="Overview", exact=True).press("Enter")
            assert discard.value.type == "confirm"
            assert discard.value.message == "Discard the unsaved editor changes?"
            expect(page).to_have_url(base + "/#policy")
            expect(editor).to_have_value('{"revision": 2}')
            expect(page.locator("#workspace")).to_be_focused()
            expect(opener).to_have_attribute("aria-expanded", "false")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            scenarios.append(
                "overview query normalization, browser Back and dirty-editor cancellation focus"
            )
            assert not errors, errors
        except Exception:
            page.screenshot(path=str(args.artifacts / "failure.png"), full_page=True)
            raise
        finally:
            browser.close()
    report = {
        "status": "passed",
        "scenario_groups": len(scenarios),
        "scenarios": scenarios,
        "scope": "mocked API consumers on installed wheel; no backend enforcement/inference claim",
    }
    (args.artifacts / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
