"""Installed three-page UX and real audit; explicit response faults, no inference."""

import argparse
import json
import sqlite3
import time
import uuid
from pathlib import Path

from local_console_check import call, expire
from playwright.sync_api import expect, sync_playwright


def counts(database):
    with sqlite3.connect(database) as db:
        return {
            table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ["audit_events", "tool_outbox", "tool_actions"]
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, default=Path(".ai/qa/test-env.json"))
    parser.add_argument("--artifacts", type=Path, default=Path(".ai/qa/artifacts_three_pages"))
    args = parser.parse_args()
    descriptor = json.loads(args.descriptor.read_text())
    assert descriptor["status"] == "running" and descriptor["startedByThisRepo"]
    base = descriptor["baseUrl"]
    database = Path(descriptor["stateDir"]) / "data/agentgate.sqlite3"
    args.artifacts.mkdir(parents=True, exist_ok=True)
    calls, errors, scenarios = [], [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
        )
        page = context.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: calls.append((r.url.removeprefix(base), r.method)))
        try:
            started = time.monotonic()
            page.goto(base)
            expect(page.get_by_role("heading", name="Example conversations")).to_be_visible()
            startup_ms = round((time.monotonic() - started) * 1000)
            primary = page.get_by_role("navigation", name="Main navigation")
            expect(primary.get_by_role("link")).to_have_text(["Chat", "Logs", "Workflow"])
            expect(page.get_by_label("Operator credential")).to_be_hidden()
            baseline, before_calls = counts(database), len(calls)
            for name, heading, outcome in [
                (
                    "02 Personal data outside scope Blocked",
                    "Personal data outside scope",
                    "Blocked · why",
                ),
                (
                    "03 An invitation awaiting review Escalated",
                    "An invitation awaiting review",
                    "Escalated · why",
                ),
                (
                    "04 Instructions hidden in a source Blocked",
                    "Instructions hidden in a source",
                    "Blocked · why",
                ),
                ("01 A scoped HR summary Allowed", "A scoped HR summary", "Allowed · why"),
            ]:
                choice = page.get_by_role("button", name=name, exact=True)
                choice.focus()
                choice.press("Enter")
                expect(choice).to_be_focused()
                expect(choice).to_have_attribute("aria-pressed", "true")
                expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible()
                expect(page.get_by_role("heading", name=outcome, exact=True)).to_be_visible()
                expect(
                    page.get_by_role("region", name="Selected example conversation")
                ).to_contain_text("Illustration only")
            assert counts(database) == baseline
            assert calls[before_calls:] == []
            assert page.locator("#view textarea, #view input, #view img").count() == 0
            assert page.get_by_role("button", name="Approve exact action").count() == 0
            scenarios.append(
                "four keyboard-selected synthetic cases cause zero requests/audit/approval/outbox effects"
            )

            # A real governed denial creates actual audit evidence, no fixture event injection.
            result = call(
                page,
                "/admin/playground",
                {"mode": "document", "document_id": "ux-unregistered-" + uuid.uuid4().hex},
            )
            assert result["data"]["decision"] == "deny" and result["data"]["executed"] is False
            trace = result["data"]["trace_id"]
            assert counts(database)["tool_outbox"] == baseline["tool_outbox"]
            primary.get_by_role("link", name="Logs", exact=True).press("Enter")
            expect(
                page.get_by_role("heading", name="Security timeline", exact=True)
            ).to_be_visible()
            page.locator("#context-nav").get_by_role(
                "link", name="Security timeline", exact=True
            ).press("Enter")
            expect(page.locator("#workspace")).to_be_focused()
            expect(page.get_by_label("Filter loaded events")).to_be_visible()
            page.get_by_label("Filter loaded events").fill(trace)
            page.get_by_label("Decision", exact=True).select_option("deny")
            expect(page.locator("tbody tr")).to_have_count(1)
            page.get_by_text("Inspect event", exact=True).press("Enter")
            expect(page.locator("tbody pre")).to_contain_text(trace)
            expect(page.locator("tbody pre")).to_contain_text('"executed": false')
            page.screenshot(path=str(args.artifacts / "logs-real-denial-1440.png"), full_page=True)
            scenarios.append(
                "real governed denial is correlated/filterable/inspectable with no outbox effect"
            )

            primary.get_by_role("link", name="Workflow", exact=True).press("Enter")
            diagram = page.get_by_role("region", name="Seven-layer control pipeline")
            expect(diagram.get_by_role("button")).to_have_count(7)
            details = page.get_by_role("region", name="Selected layer details")
            for name, gap in [
                ("01 Identity / permissions Who may act?", "OIDC"),
                ("02 Input Bound the request", "PL/EN"),
                ("03 Data Constrain exposure", "PESEL"),
                ("04 Actions Check before dispatch", "descriptor hash pinning"),
                ("05 Output Inspect, then release", "canary"),
                ("06 Consumption Across every step", "Redis"),
                ("07 Supply chain Across every step", "17-feed"),
            ]:
                layer = diagram.get_by_role("button", name=name, exact=True)
                layer.press("Enter")
                expect(layer).to_be_focused()
                expect(details).to_contain_text(gap)
                expect(details).to_contain_text("Partial")
            branches = page.get_by_role("region", name="Action policy branches")
            for text in [
                "Hard deny → stop; no override",
                "Server approval + revalidation",
                "A read is never authorized solely by classification",
                "Destructive / irreversible",
                "Destructive / undeclared",
                "Blocked · no reviewed executor",
            ]:
                expect(branches).to_contain_text(text)
            expect(page.locator(".undeclared-note")).to_contain_text("denied / unimplemented")
            expect(page.locator(".gdpr-cards")).to_contain_text(
                "Audit JSONL is not a subject portability export"
            )
            expect(page.locator(".gdpr-cards")).to_contain_text(
                "Technical logs are not a complete RoPA"
            )
            assert "definition required" not in page.locator("#view").inner_text()
            scenarios.append(
                "seven interactive layers, hard-deny branches and distinct GDPR20/30 purposes/gaps"
            )

            for width in [360, 390, 768, 1440]:
                page.set_viewport_size({"width": width, "height": 900})
                for name in ["Chat", "Logs", "Workflow"]:
                    primary.get_by_role("link", name=name, exact=True).press("Enter")
                    expect(primary.get_by_role("link", name=name, exact=True)).to_have_attribute(
                        "aria-current", "page"
                    )
                    expect(page.locator("#view")).not_to_have_attribute("aria-busy", "true")
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    for link_name in ["Chat", "Logs", "Workflow"]:
                        box = primary.get_by_role("link", name=link_name, exact=True).bounding_box()
                        assert 0 <= box["x"] and box["x"] + box["width"] <= width
                    page.screenshot(
                        path=str(args.artifacts / f"{name.lower()}-{width}.png"), full_page=True
                    )
            scenarios.append(
                "all three top menus and three pages visible without overflow at 360/390/768/1440"
            )

            for route, parent in [
                ("hr", "Chat"),
                ("tool_actions", "Chat"),
                ("outbox", "Chat"),
                ("playground", "Chat"),
                ("timeline?trace=" + trace, "Logs"),
                ("overview", "Logs"),
                ("overview?section=usage", "Logs"),
                ("export", "Logs"),
                ("catalog", "Workflow"),
                ("policy", "Workflow"),
                ("feed", "Workflow"),
                ("overview?section=standards", "Workflow"),
                ("overview?section=controls", "Workflow"),
                ("unknown", "Chat"),
            ]:
                page.goto(base + "/#" + route)
                expect(primary.get_by_role("link", name=parent, exact=True)).to_have_attribute(
                    "aria-current", "page"
                )
                expect(page.locator("#view")).not_to_have_attribute("aria-busy", "true")
            primary.get_by_role("link", name="Logs", exact=True).click()
            primary.get_by_role("link", name="Workflow", exact=True).click()
            page.go_back()
            expect(primary.get_by_role("link", name="Logs", exact=True)).to_have_attribute(
                "aria-current", "page"
            )
            page.go_forward()
            expect(primary.get_by_role("link", name="Workflow", exact=True)).to_have_attribute(
                "aria-current", "page"
            )
            scenarios.append("all legacy/deep routes retain parent, native back/forward")

            page.goto(base + "/#policy?source=deep-link")
            editor = page.get_by_label("Policy JSON")
            expect(editor).to_be_visible()
            edited = editor.input_value() + " "
            editor.fill(edited)
            page.once("dialog", lambda d: d.dismiss())
            primary.get_by_role("link", name="Chat", exact=True).click()
            expect(page).to_have_url(base + "/#policy?source=deep-link")
            expect(editor).to_have_value(edited)
            page.once("dialog", lambda d: d.accept())
            primary.get_by_role("link", name="Logs", exact=True).click()
            expect(
                page.get_by_role("heading", name="Security timeline", exact=True)
            ).to_be_visible()
            scenarios.append(
                "dirty-policy cancel preserves full query/editor; accepted discard navigates"
            )

            # Explicit presentation faults only. These responses never enter server audit/counts.
            page.route(
                "**/admin/events?limit=100", lambda r: r.fulfill(status=200, json={"events": []})
            )
            page.get_by_role("button", name="Refresh").click()
            expect(
                page.get_by_text(
                    "No matching events. Run an action or change the filters.", exact=True
                )
            ).to_be_visible()
            page.unroute("**/admin/events?limit=100")
            page.route(
                "**/admin/events?limit=100",
                lambda r: r.fulfill(status=503, json={"detail": "Controlled QA outage"}),
            )
            page.get_by_role("button", name="Refresh").click()
            expect(page.locator("#notice")).to_contain_text("unavailable")
            expect(
                page.get_by_text(
                    "No current data to display. Check the service and refresh.", exact=True
                )
            ).to_be_visible()
            page.screenshot(path=str(args.artifacts / "logs-error-1440.png"), full_page=True)
            page.unroute("**/admin/events?limit=100")
            held = []
            page.route("**/admin/events?limit=100", lambda r: held.append(r))
            page.get_by_role("button", name="Refresh").click()
            expect(page.locator("#view")).to_have_attribute("aria-busy", "true")
            expect(page.get_by_text("Loading operator state…", exact=True)).to_be_visible()
            primary.get_by_role("link", name="Chat", exact=True).click()
            held.pop().fulfill(status=200, json={"events": []})
            expect(page.get_by_role("heading", name="Example conversations")).to_be_visible()
            page.unroute("**/admin/events?limit=100")
            scenarios.append(
                "controlled empty/error/loading and stale log responses preserve current page"
            )

            before = len(calls)
            expire(context, base, database)
            primary.get_by_role("link", name="Logs", exact=True).click()
            expect(page.locator("#notice")).to_contain_text("Session restored")
            expect(
                page.get_by_role("heading", name="Security timeline", exact=True)
            ).to_be_visible()
            new = calls[before:]
            assert sum(path == "/admin/session/bootstrap" for path, _ in new) == 1
            assert all(
                method == "GET" or path == "/admin/session/bootstrap" for path, method in new
            )
            assert counts(database)["tool_outbox"] == baseline["tool_outbox"]
            scenarios.append("real local session expiry recovers once with no mutation replay")
            assert not errors, errors
        except Exception:
            page.screenshot(path=str(args.artifacts / "failure.png"), full_page=True)
            (args.artifacts / "failure-context.txt").write_text(page.locator("body").inner_text())
            raise
        finally:
            context.close()
            browser.close()
    report = {
        "status": "passed",
        "scenario_groups": len(scenarios),
        "scenarios": scenarios,
        "startup_ms": startup_ms,
        "scope": "installed local console, real denial/audit/session; explicit browser response faults; no inference",
    }
    (args.artifacts / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
