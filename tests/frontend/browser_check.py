"""Run real control-plane UI checks against a disposable QA server.

Usage: python tests/frontend/browser_check.py --url http://127.0.0.1:8765
       --state-dir .runtime/ui-control-state --artifacts .ai/qa/artifacts_dashboard
Requires separately installed Python Playwright/Chromium; no product dependency.
"""

import argparse
import json
import sqlite3
from pathlib import Path

from catalog_flows import catalog_flow
from fullstack_flows import model_generation, observe_delivery, restore_controls, tools_and_renewal
from navigation import navigation
from playwright.sync_api import expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument(
        "--model", action="store_true", help="Also run the actual configured local model"
    )
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url.rstrip("/") + "/#overview")
        page.wait_for_load_state("networkidle")
        assert "Laya Sec Layer" in page.title(), "QA port is not the AgentGate application"
        expect(page.get_by_role("button", name="Unlock console")).to_be_enabled()
        page.screenshot(path=str(args.artifacts / "login.png"), full_page=True)
        # Real agent credentials are refused by the operator boundary.
        page.get_by_label("Operator credential").fill((args.state_dir / "client.token").read_text())
        page.get_by_role("button", name="Unlock console").click()
        expect(page.locator("#login-status")).to_contain_text("denied")
        expect(page.locator("#console")).to_be_hidden()
        page.get_by_label("Operator credential").fill(
            (args.state_dir / "operator.token").read_text()
        )
        # Keyboard-only login and navigation activation.
        page.get_by_label("Operator credential").press("Tab")
        expect(page.get_by_role("button", name="Unlock console")).to_be_focused()
        page.keyboard.press("Enter")
        expect(page.get_by_role("heading", name="Service & controls")).to_be_visible()
        with restore_controls(context, args.url.rstrip("/"), args.state_dir):
            cookies = context.cookies(args.url + "/admin/session")
            cookie = next(item for item in cookies if item["name"] == "agentgate_operator")
            assert cookie["httpOnly"] and cookie["sameSite"] == "Strict"
            assert page.evaluate("Object.keys(localStorage).length") == 0
            assert page.evaluate("Object.keys(sessionStorage).length") == 0
            page.reload()
            expect(page.get_by_role("heading", name="Service & controls")).to_be_visible()

            def navigate(name: str) -> None:
                navigation(page).get_by_role("link", name=name, exact=False).click()
                expect(page.locator("#workspace")).to_be_focused()

            catalog_flow(page, navigate, args.state_dir, args.artifacts)

            navigate("Playground")
            expect(page.get_by_label("Example preset")).to_be_visible()
            for preset, decision in [
                ("Read internal notes", "allow"),
                ("Redact contact email", "redact"),
                ("Deny cross-tenant read", "deny"),
            ]:
                page.get_by_label("Example preset").select_option(label=preset)
                page.get_by_role("button", name="Run governed action").click()
                expect(page.locator(".result .tag")).to_have_text(decision)
                expect(page.get_by_role("button", name="Run governed action")).to_be_enabled()
                if decision == "redact":
                    assert "analyst@demo.internal" not in page.locator(".result").inner_text()
                if decision == "deny":
                    expect(page.locator(".result")).to_contain_text("Execution is not confirmed")
            page.screenshot(path=str(args.artifacts / "playground-denied.png"), full_page=True)
            action = tools_and_renewal(page, navigate, args.state_dir, args.artifacts)
            if args.model:
                model_generation(page, args.state_dir, args.artifacts)
            navigate("Security timeline")
            expect(page.get_by_label("Decision", exact=True)).to_be_visible()
            page.get_by_label("Decision", exact=True).select_option("deny")
            expect(page.locator("tbody tr").first).to_be_visible()
            page.get_by_role("searchbox").fill("no-such-trace")
            expect(page.get_by_text("No matching events.", exact=False)).to_be_visible()
            page.get_by_role("searchbox").fill("")
            page.get_by_label("Decision", exact=True).select_option("")
            page.locator("summary").first.click()
            page.screenshot(path=str(args.artifacts / "timeline.png"), full_page=True)

            navigate("Policy studio")
            editor = page.get_by_label("Policy JSON", exact=True)
            expect(editor).to_be_visible()
            initial_policy = json.loads(editor.input_value())
            candidate = initial_policy | {"revision": initial_policy["revision"] + 1}
            editor.fill(json.dumps(candidate, indent=2))
            page.get_by_role("button", name="Validate on server").click()
            expect(page.get_by_text("Valid ·", exact=False)).to_be_visible()
            page.get_by_role("button", name="Review activation").click()
            expect(page.get_by_role("button", name="Activate reviewed version")).to_be_disabled()
            page.get_by_label("I reviewed this exact document.").check()
            page.get_by_role("button", name="Activate reviewed version").click()
            expect(
                page.get_by_text(
                    f"Activated {candidate['policy_id']}:{candidate['revision']}.", exact=True
                )
            ).to_be_visible()
            # Advance policy directly while the editor holds an older version: UI CAS must reject.
            newer = candidate | {"revision": candidate["revision"] + 1}
            status = page.evaluate(
                """async (candidate) => {
              const session = await (await fetch('/admin/session')).json();
              return (await fetch('/admin/policy/activate', {method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf_token},body:JSON.stringify({policy:candidate,expected_version:candidate.policy_id+':'+(candidate.revision-1)})})).status;
            }""",
                newer,
            )
            assert status == 200
            editor.fill(json.dumps(candidate | {"revision": newer["revision"] + 1}, indent=2))
            page.get_by_role("button", name="Review activation").click()
            page.get_by_label("I reviewed this exact document.").check()
            page.get_by_role("button", name="Activate reviewed version").click()
            expect(page.get_by_text("Version conflict.", exact=False)).to_be_visible()
            page.screenshot(path=str(args.artifacts / "policy-conflict.png"), full_page=True)
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="Refresh").click()
            expect(editor).to_have_value(json.dumps(newer, indent=2))

            navigate("Threat feed")
            feed_editor = page.get_by_label("Feed JSON", exact=True)
            expect(feed_editor).to_be_visible()
            feed = json.loads(feed_editor.input_value())
            updated = feed | {
                "revision": feed["revision"] + 1,
                "indicators": [
                    {
                        "id": "browser-qa-literal",
                        "kind": "literal_text",
                        "value": "quarterly",
                        "stages": ["tool_result"],
                    }
                ],
            }
            feed_editor.fill(json.dumps(updated, indent=2))
            page.get_by_role("button", name="Review activation").click()
            page.get_by_label("I reviewed this exact document.").check()
            page.get_by_role("button", name="Activate reviewed version").click()
            expect(
                page.get_by_text(f"Activated {feed['feed_id']}:{updated['revision']}.", exact=True)
            ).to_be_visible()
            navigate("Playground")
            page.get_by_label("Example preset").select_option(label="Read internal notes")
            page.get_by_role("button", name="Run governed action").click()
            expect(page.locator(".result .tag")).to_have_text("deny")
            expect(page.locator(".result")).to_contain_text("THREAT")

            navigate("Approvals")
            expect(page.get_by_role("heading", name="Approval inbox")).to_be_visible()
            navigate("Test outbox")
            expect(page.get_by_role("heading", name="Local test outbox")).to_be_visible()
            navigate("Audit export")
            with page.expect_download() as event:
                page.get_by_role("button", name="Download audit page").click()
            download = event.value
            records = Path(download.path()).read_text()
            assert '"trace_id"' in records and '"principal_id"' in records
            assert "analyst@demo.internal" not in records
            expect(page.get_by_text("Export cursor", exact=True)).to_be_visible()

            observe_delivery(page, args.state_dir, action, args.artifacts)
            navigate("Overview")
            expect(page.get_by_role("heading", name="Service & controls")).to_be_visible()
            page.screenshot(path=str(args.artifacts / "overview.png"), full_page=True)
            for width in (390, 768):
                page.set_viewport_size({"width": width, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(args.artifacts / f"overview-{width}.png"), full_page=True)
            # Session is revoked server-side, privileged state removed, refresh stays locked.
            page.get_by_role("button", name="Lock & sign out").click()
            expect(page.locator("#console")).to_be_hidden()
            assert page.locator("#view").inner_text() == ""
            page.reload()
            expect(page.get_by_role("button", name="Unlock console")).to_be_enabled()
            expect(page.locator("#console")).to_be_hidden()
            assert not errors, errors
        browser.close()
    with sqlite3.connect(args.state_dir / "agentgate.sqlite3") as db:
        events = [json.loads(row[0]) for row in db.execute("SELECT event FROM audit_events")]
        assert any(event["decision"] == "redact" and event["executed"] for event in events)
        assert any(event["decision"] == "deny" and not event["executed"] for event in events)
    print(
        "PASS: real catalog metadata/REST zero-effects and document/memory/approval/outbox/renewal/control-plane browser flows, CAS conflict, feed enforcement, export, session revocation, keyboard and 390/768/1440px layouts; "
        + ("real configured model generation verified." if args.model else "no inference.")
    )


if __name__ == "__main__":
    main()
