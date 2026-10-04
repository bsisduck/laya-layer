"""Mocked HR presentation regressions; no enforcement or inference evidence."""

import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    calls, held, errors = [], [], []
    state = {"hold": False, "fail": False, "parent": "active", "summary_missing": True}
    hr = {
        "version": "hr-local-v1",
        "data": "synthetic",
        "configured": True,
        "parent": {"state": "active", "epoch": 0},
        "identity": {"agent_id": "hr-assistant", "principal_id": "hr-demo-account"},
        "requester": {"department": "HR"},
        "effective_documents": ["hr-candidate-001", "hr-cv-injection-001"],
        "resources": ["hr-candidate-001", "hr-cv-injection-001"],
        "permissions": {"profiles": []},
    }
    released = {
        "decision": "allow",
        "executed": True,
        "trace_id": "source-fixture",
        "result": {"content": "Synthetic source fixture"},
    }

    def handle(route):
        path = urlsplit(route.request.url).path
        body = route.request.post_data_json if route.request.post_data else None
        calls.append((path, route.request.method, body))
        code, data = 200, {}
        if path == "/admin/config":
            data = {"mode": "local"}
        elif path in ("/admin/session", "/admin/session/bootstrap"):
            data = {
                "authenticated": True,
                "csrf_token": "mock-nonce",
                "expires_at": time.time() + 600,
            }
        elif path == "/admin/hr":
            data = hr | {"parent": {"state": state["parent"], "epoch": 0}}
        elif path == "/admin/hr/bind":
            data = {"handle": "fixture-handle", "expires_at": time.time() + 300}
        elif path == "/admin/hr/read":
            if state["hold"]:
                held.append(route)
                return
            code, data = (
                (503, {"detail": "Mock read unavailable"}) if state["fail"] else (200, released)
            )
        elif path == "/admin/hr/summary":
            data = {
                "completion": {
                    "agentgate": {
                        "decision": "allow",
                        "executed": True,
                        "trace_id": "model-fixture",
                    },
                    "choices": []
                    if state["summary_missing"]
                    else [{"message": {"content": "Mock provider summary"}}],
                },
                "source": {"trace_id": "source-fixture"},
            }
        elif path == "/admin/hr/propose":
            code, data = (
                403,
                {
                    "decision": "deny",
                    "executed": False,
                    "trace_id": "action-fixture",
                    "reason_codes": ["RECIPIENT_DOMAIN_NOT_ALLOWED"],
                },
            )
        route.fulfill(status=code, content_type="application/json", body=json.dumps(data))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/admin/**", handle)
        try:
            page.goto(args.url.rstrip("/") + "/#hr")
            start = page.get_by_role("button", name="Start HR session", exact=True)
            read = page.get_by_role("button", name="Read selected source", exact=True)
            selection = page.get_by_label("Synthetic source")
            progress = page.get_by_role("list", name="HR workflow progress")
            expect(progress.get_by_role("listitem")).to_have_count(3)
            expect(read).to_be_disabled()
            assert read.evaluate("e => getComputedStyle(e).cursor") == "not-allowed"
            start.focus()
            assert start.evaluate("e => getComputedStyle(e).outlineStyle") != "none"
            start.press("Enter")
            expect(read).to_be_enabled()
            read.press("Enter")
            expect(progress).to_contain_text("Output released")
            state["hold"] = True
            read.press("Enter")
            expect(read).to_have_attribute("aria-busy", "true")
            expect(selection).to_be_disabled()
            expect(progress).not_to_contain_text("Output released")
            assert selection.input_value() == "hr-candidate-001" and len(held) == 1
            assert read.evaluate("e => getComputedStyle(e).cursor") == "wait"
            held.pop().fulfill(
                status=200, content_type="application/json", body=json.dumps(released)
            )
            expect(selection).to_be_enabled()
            expect(read).not_to_have_attribute("aria-busy", "true")
            expect(
                page.get_by_text("Read decision received: Synthetic candidate record.")
            ).to_be_visible()
            selection.select_option("hr-cv-injection-001")
            expect(progress).not_to_contain_text("Output released")
            expect(page.get_by_text("Synthetic source fixture", exact=True)).to_have_count(0)
            read.press("Enter")
            expect(selection).to_be_disabled()
            held.pop().fulfill(
                status=403,
                content_type="application/json",
                body=json.dumps(
                    {
                        "decision": "deny",
                        "executed": True,
                        "trace_id": "withheld-fixture",
                        "reason_codes": ["SEMANTIC_BLOCKED"],
                    }
                ),
            )
            expect(
                page.get_by_text(
                    "The protected operation ran, but its output was withheld.", exact=False
                )
            ).to_be_visible()
            expect(progress).to_contain_text("Blocked")
            state["hold"], state["fail"] = False, True
            read.press("Enter")
            expect(page.get_by_text("Service unavailable. Mock read unavailable")).to_be_visible()
            expect(progress).not_to_contain_text("Output released")
            page.get_by_role("button", name="Request model summary").press("Enter")
            expect(page.get_by_role("heading", name="Summary unavailable")).to_be_visible()
            expect(progress).to_contain_text("Unavailable · review evidence")
            expect(progress).not_to_contain_text("Blocked")
            state["summary_missing"] = False
            summary_control = page.get_by_role("button", name="Request model summary")
            expect(summary_control).to_be_enabled()
            summary_control.press("Enter")
            expect(page.get_by_role("heading", name="Provider summary")).to_be_visible()
            expect(
                page.get_by_role("link", name="Open model audit trace", exact=False)
            ).to_have_count(1)
            expect(
                page.get_by_role("link", name="Open source audit trace", exact=False)
            ).to_have_count(1)
            count = sum(path == "/admin/hr/propose" for path, _, _ in calls)
            for label, bad, good in [
                ("Message recipient", "", "candidate@demo.internal"),
                ("Message recipient", "invalid", "candidate@demo.internal"),
                ("Message subject", " ", "Synthetic subject"),
                ("Message content", " ", "Synthetic body"),
            ]:
                page.get_by_label(label).fill(bad)
                page.get_by_role("button", name="Propose exact message").press("Enter")
                expect(page.get_by_label(label)).to_be_focused()
                assert sum(path == "/admin/hr/propose" for path, _, _ in calls) == count
                page.get_by_label(label).fill(good)
            # Enter on a text field performs the same validated explicit submission.
            page.get_by_label("Message subject").press("Enter")
            expect(page.get_by_text("No exact approval was returned.", exact=False)).to_be_visible()
            assert sum(path == "/admin/hr/propose" for path, _, _ in calls) == count + 1
            assert (
                page.get_by_role("heading", name="Review the exact proposed message").count() == 0
            )
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(args.artifacts / "hr-states-390.png"), full_page=True)
            # Navigation resets selected source and read progress together.
            page.get_by_role("navigation").get_by_role("link", name="Catalog", exact=False).click()
            page.get_by_role("navigation").get_by_role(
                "link", name="HR workspace", exact=False
            ).click()
            expect(selection).to_have_value("hr-candidate-001")
            expect(progress).not_to_contain_text("Output released")
            expect(page.get_by_role("heading", name="Provider summary")).to_have_count(0)
            for parent in ["expired", "revoked"]:
                state["parent"] = parent
                page.get_by_role("button", name="Refresh").click()
                expect(page.get_by_role("button", name="Start a new HR session")).to_be_disabled()
                if parent == "expired":
                    expect(
                        page.get_by_role("button", name="Renew expired HR parent")
                    ).to_be_visible()
                else:
                    expect(
                        page.get_by_text("HR authority is inactive or revoked.", exact=False)
                    ).to_be_visible()
                    expect(
                        page.get_by_role("button", name="Renew expired HR parent")
                    ).to_have_count(0)
            assert not errors, errors
        except Exception:
            page.screenshot(path=str(args.artifacts / "failure.png"), full_page=True)
            raise
        finally:
            browser.close()
    print(
        "PASS: MOCKED HR source locking, release/withheld/error states, validation/keyboard, explicit approval evidence, navigation reset and inactive authority. No enforcement or inference proof."
    )


if __name__ == "__main__":
    main()
