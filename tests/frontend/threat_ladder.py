"""Executable installed ladder/filter regression with real durable denied events.

Uses the owned om-prepare-test-env descriptor, no inference. Fault/old-payload
routes exercise consumer states after real endpoint/auth/evidence assertions.
Artifacts stay ignored; the append-only QA audit evidence is intentionally retained.
"""

import argparse
import json
import sqlite3
import time
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, default=Path(".ai/qa/test-env.json"))
    parser.add_argument("--artifacts", type=Path, default=Path(".ai/qa/artifacts_threat_ladder"))
    args = parser.parse_args()
    descriptor = json.loads(args.descriptor.read_bytes())
    assert descriptor["status"] == "running" and descriptor["startedByThisRepo"] is True
    base = descriptor["baseUrl"]
    state = Path(descriptor["stateDir"]) / "data"
    args.artifacts.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        started = time.monotonic()
        try:
            assert context.request.get(base + "/admin/threat-taxonomy").status == 401
            page.goto(base)
            expect(page.get_by_role("button", name="Unlock console")).to_be_enabled()
            shell_ms = round((time.monotonic() - started) * 1000, 1)
            page.get_by_label("Operator credential").fill((state / "operator.token").read_text())
            page.get_by_label("Operator credential").press("Tab")
            page.keyboard.press("Enter")
            heading = page.get_by_role("heading", name="Authored scenario ladder · L0–L5")
            expect(heading).to_be_visible()
            expect(page.locator(".threat-ladder li")).to_have_count(6)
            expect(
                page.get_by_text(
                    "Gaps: No feed signatures or two-person change approval", exact=True
                )
            ).to_be_visible()
            page.screenshot(path=str(args.artifacts / "ladder-desktop.png"), full_page=True)
            taxonomy = context.request.get(base + "/admin/threat-taxonomy")
            assert taxonomy.ok
            assert [layer["id"] for layer in taxonomy.json()["layers"]] == [
                "identity",
                "input",
                "data",
                "actions",
                "output",
                "consumption",
                "supply_chain",
            ]
            session = context.request.get(base + "/admin/session").json()
            headers = {"Origin": base, "X-CSRF-Token": session["csrf_token"]}
            result = context.request.post(
                base + "/admin/playground",
                headers=headers,
                data={"mode": "document", "document_id": "qa-unregistered-" + uuid.uuid4().hex},
            )
            assert result.status == 403
            body = result.json()
            assert body["executed"] is False and body["reason_codes"] == ["RESOURCE_NOT_ALLOWED"]
            with sqlite3.connect(state / "agentgate.sqlite3") as db:
                events = [
                    json.loads(row[0])
                    for row in db.execute(
                        "SELECT event FROM audit_events WHERE event LIKE ?",
                        ("%" + body["action_id"] + "%",),
                    )
                ]
                assert len(events) == 1 and events[0]["event_type"] == "action_denied"
                assert events[0]["trace_id"] == body["trace_id"]
                assert (
                    db.execute(
                        "SELECT count(*) FROM tool_outbox WHERE action_id=?", (body["action_id"],)
                    ).fetchone()[0]
                    == 0
                )
            page.get_by_role("navigation").get_by_role(
                "link", name="Security timeline", exact=False
            ).click()
            expect(page.get_by_label("Live level", exact=True)).to_be_visible()
            expect(page.locator("#workspace")).to_be_focused()
            page.get_by_label("Decision", exact=True).select_option("deny")
            page.get_by_role("searchbox").fill(body["trace_id"])
            expect(page.locator("tbody tr")).to_have_count(1)
            expect(page.locator("tbody tr")).to_contain_text("Unknown live level")
            expect(page.locator("tbody tr")).to_contain_text("LLM06:2025")
            page.get_by_label("Control layer", exact=True).select_option("data")
            expect(page.locator("tbody tr")).to_have_count(1)
            page.get_by_label("Live level", exact=True).select_option("unknown")
            expect(page.locator("tbody tr")).to_have_count(1)
            for level in ("L0", "L1", "L2", "L3", "L4", "L5"):
                page.get_by_label("Live level", exact=True).select_option(level)
                expect(page.get_by_text("No matching events.", exact=False)).to_be_visible()
            page.get_by_label("Live level", exact=True).select_option("unknown")
            page.get_by_label("Control layer", exact=True).select_option("consumption")
            expect(page.get_by_text("No matching events.", exact=False)).to_be_visible()
            page.get_by_label("Control layer", exact=True).select_option("identity")
            expect(page.locator("tbody tr")).to_have_count(1)
            page.screenshot(
                path=str(args.artifacts / "timeline-control-context.png"), full_page=True
            )
            page.set_viewport_size({"width": 390, "height": 844})
            records = page.get_by_role("region", name="Scrollable records")
            expect(records).to_have_attribute("tabindex", "0")
            records.focus()
            page.keyboard.press("ArrowRight")
            page.screenshot(path=str(args.artifacts / "timeline-mobile.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.get_by_role("navigation").get_by_role("link", name="Overview", exact=False).click()
            expect(heading).to_be_visible()
            page.screenshot(path=str(args.artifacts / "ladder-mobile.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

            # A real response with no context represents an older server, with safe text.
            def old_payload(route):
                response = route.fetch()
                value = response.json()
                for event in value["events"]:
                    event.pop("threat_context", None)
                value["events"][0]["operation"] = "<img src=x onerror=alert(1)>"
                route.fulfill(response=response, json=value)

            page.route("**/admin/events?limit=100", old_payload)
            page.get_by_role("navigation").get_by_role(
                "link", name="Security timeline", exact=False
            ).click()
            expect(page.get_by_label("Live level", exact=True)).to_be_visible()
            expect(page.locator("tbody tr").first).to_contain_text("<img src=x onerror=alert(1)>")
            assert page.locator("#view img").count() == 0
            page.get_by_label("Live level", exact=True).select_option("unknown")
            expect(page.locator("tbody tr").first).to_contain_text("No mapped layer")
            page.unroute("**/admin/events?limit=100", old_payload)

            # Invalid ordered metadata must produce unavailable, not a plausible legend.
            def malformed(route):
                response = route.fetch()
                value = response.json()
                value["levels"][1]["id"] = "L0"
                route.fulfill(response=response, json=value)

            page.route("**/admin/threat-taxonomy", malformed)
            page.get_by_role("navigation").get_by_role("link", name="Overview", exact=False).click()
            expect(page.get_by_text("Ladder unavailable:", exact=False)).to_be_visible()
            expect(page.locator(".threat-ladder li")).to_have_count(0)
            page.unroute("**/admin/threat-taxonomy", malformed)
            page.route(
                "**/admin/events?limit=100",
                lambda route: route.fulfill(status=503, json={"detail": "Unavailable"}),
            )
            page.get_by_role("navigation").get_by_role(
                "link", name="Security timeline", exact=False
            ).click()
            expect(page.get_by_text("No current data to display.", exact=False)).to_be_visible()
            page.unroute("**/admin/events?limit=100")
            # Hold only the taxonomy response; the real shell must report loading.
            held = []
            page.route("**/admin/threat-taxonomy", lambda route: held.append(route))
            with page.expect_request("**/admin/threat-taxonomy"):
                page.get_by_role("navigation").get_by_role(
                    "link", name="Overview", exact=False
                ).click()
            expect(page.get_by_text("Loading operator state…", exact=True)).to_be_visible()
            expect(page.locator("#view")).to_have_attribute("aria-busy", "true")
            assert held
            held[0].fulfill(response=held[0].fetch())
            expect(heading).to_be_visible()
            page.unroute("**/admin/threat-taxonomy")
            assert not errors, errors
            report = {
                "status": "passed",
                "scenarios": [
                    "protected endpoint",
                    "real durable deny/no side effect",
                    "six unknown level filters",
                    "overlapping layer filters",
                    "mobile fit",
                    "old context safe text",
                    "invalid legend unavailable",
                    "timeline unavailable",
                    "loading and keyboard-scroll accessibility",
                ],
                "shell_render_ms": shell_ms,
                "scope": "owned installed product; fixture document denial, no inference",
                "action_id": body["action_id"],
                "trace_id": body["trace_id"],
            }
            (args.artifacts / "result.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report))
        finally:
            session = context.request.get(base + "/admin/session")
            if session.ok:
                context.request.delete(
                    base + "/admin/session",
                    headers={"Origin": base, "X-CSRF-Token": session.json()["csrf_token"]},
                )
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
