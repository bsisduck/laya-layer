"""Actual protected metadata, browser outcomes and denied installed REST effects."""

import json
import sqlite3
import time

from playwright.sync_api import expect


def catalog_flow(page, navigate, state, artifacts):
    database = state / "agentgate.sqlite3"

    def effects():
        with sqlite3.connect(database) as db:
            return {
                table: db.execute("SELECT * FROM " + table).fetchall()
                for table in (
                    "tool_outbox",
                    "tool_actions",
                    "tool_reservations",
                    "budget_counters",
                    "model_attempts",
                )
            }

    before = effects()
    started = time.monotonic()
    with page.expect_response(lambda response: response.url.endswith("/admin/catalog")) as event:
        navigate("Catalog")
    response = event.value
    assert response.status == 200 and response.headers["cache-control"] == "no-store"
    catalog = response.json()
    expect(page.get_by_role("heading", name="Approved tool catalog")).to_be_visible()
    render_ms = round((time.monotonic() - started) * 1000, 1)
    assert catalog["version"] == "approved-tools-v1"
    policy = page.request.get(response.url.replace("/catalog", "/policy")).json()
    assert catalog["policy_version"] == policy["version"]
    assert [tool["operation"] for tool in catalog["tools"]] == [
        "documents.read",
        "memory.query",
        "mail.send",
    ]
    for tool in catalog["tools"]:
        card = page.get_by_role("heading", name=tool["operation"], exact=True).locator("..")
        expect(card).to_be_visible()
        expect(card.locator("..")).to_contain_text(tool["adapter"])
        expect(card.locator("..")).to_contain_text(
            f"{tool['risk']['band']} · {tool['risk']['score']}/100"
        )
        assert sum(tool["risk"]["components"].values()) == tool["risk"]["score"]
    assert [tool["risk"]["score"] for tool in catalog["tools"]] == [25, 25, 75]
    assert (
        catalog["tools"][2]["policy"]["recipient_domains"]
        == policy["policy"]["scoped_tools"]["mail_domains"]
    )
    expect(page.get_by_text("Exact human approval required", exact=True)).to_be_visible()
    expect(page.get_by_text("Automatic after hard authorization", exact=True)).to_have_count(2)
    expect(page.get_by_role("heading", name="Dev · gitlab.merge_main")).to_be_visible()
    expect(page.get_by_role("heading", name="Finance · payments.transfer")).to_be_visible()
    expect(
        page.get_by_text("No GitLab or bank connection is installed.", exact=False)
    ).to_be_visible()
    summary = page.locator("summary").filter(has_text="Risk components and policy · mail.send")
    summary.focus()
    page.keyboard.press("Enter")
    expect(summary.locator("..")).to_have_attribute("open", "")
    expect(summary.locator("..")).to_contain_text("recipient domains")
    page.screenshot(path=str(artifacts / "catalog-desktop.png"), full_page=True)
    for width in (390, 768):
        page.set_viewport_size({"width": width, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(artifacts / f"catalog-{width}.png"), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 1000})
    assert effects() == before, "Viewing metadata must not dispatch or spend"

    # Execute direct unavailable calls against the actual installed HTTP boundary.
    base = response.url.removesuffix("/admin/catalog")
    token = (state / "client.token").read_text().strip()
    headers = {"Authorization": "Bearer " + token}
    assert page.request.get(base + "/admin/catalog", headers=headers).status == 401
    discovery = page.request.get(base + "/v1/tools", headers=headers).json()
    assert set(discovery) == {"tools"}
    for operation in ("gitlab.merge_main", "payments.transfer", "documents.delete"):
        assert operation not in discovery["tools"]
        result = page.request.post(
            base + "/v1/actions/execute",
            headers=headers,
            data={"operation": operation, "arguments": {"destructiveHint": False, "risk": 0}},
        )
        assert result.status == 403 and result.json()["executed"] is False
        assert result.json()["reason_codes"] == ["UNKNOWN_OPERATION"]
    assert effects() == before, "Forbidden catalog examples must cause zero effects"
    (artifacts / "catalog-result.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "catalog": catalog,
                "render_ms": render_ms,
                "zero_effects_for_view_and_forbidden_calls": True,
                "scope": "actual rebuilt installed app; credential-mode browser + REST + SQLite; no inference",
            },
            indent=2,
        )
        + "\n"
    )
