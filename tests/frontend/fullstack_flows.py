"""Real browser flows with durable side-effect evidence on an isolated QA install."""

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager

from playwright.sync_api import expect


def api(page, path, body=None):
    return page.evaluate(
        """async ({path,body}) => {
          const session = await (await fetch('/admin/session')).json();
          const response = await fetch(path, body === null ? {} : {
            method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf_token},
            body:JSON.stringify(body)});
          return {status:response.status,data:await response.json()};
        }""",
        {"path": path, "body": body},
    )


@contextmanager
def restore_controls(context, base, state):
    """Restore configuration at newer revisions, never roll back audit or budgets."""
    saved = {}
    for kind in ("policy", "feed"):
        response = context.request.get(base + "/admin/" + kind)
        assert response.ok
        saved[kind] = response.json()[kind]
    try:
        yield
    finally:
        session = context.request.post(
            base + "/admin/session",
            headers={"Origin": base},
            data={"token": (state / "operator.token").read_text().strip()},
        )
        assert session.ok, "QA cleanup could not authenticate"
        headers = {"Origin": base, "X-CSRF-Token": session.json()["csrf_token"]}
        try:
            for kind, document in saved.items():
                current = context.request.get(base + "/admin/" + kind).json()
                if current[kind] == document:
                    continue
                document = document | {"revision": current[kind]["revision"] + 1}
                path = "/admin/policy/activate" if kind == "policy" else "/admin/feed"
                result = context.request.post(
                    base + path,
                    headers=headers,
                    data={kind: document, "expected_version": current["version"]},
                )
                assert result.ok, f"QA cleanup failed to restore {kind}"
        finally:
            context.request.delete(base + "/admin/session", headers=headers)


def execute(page):
    button = page.get_by_role("button", name="Run governed action")
    expect(button).to_be_enabled()
    with page.expect_response(lambda response: response.url.endswith("/admin/playground")) as event:
        button.click()
    data = event.value.json()
    expect(page.locator(".result")).to_be_visible()
    expect(button).to_be_enabled()
    return data


def tools_and_renewal(page, navigate, state, artifacts):
    database = state / "agentgate.sqlite3"
    page.get_by_role("button", name="Memory", exact=True).click()
    result = execute(page)
    assert result["executed"] is True
    text = json.dumps(result)
    assert "Quarterly memory notes for tenant A" in text
    assert "private memory notes for tenant B" not in text

    page.get_by_role("button", name="Mail", exact=True).click()
    payload = {
        "recipient": "reviewer@demo.internal",
        "subject": "Browser QA " + uuid.uuid4().hex,
        "body": "Synthetic local outbox evidence, no external delivery.",
    }
    key = str(uuid.uuid4())
    editor = page.get_by_label("Action payload · JSON")
    editor.fill(json.dumps(payload))
    page.get_by_label("Idempotency key", exact=True).fill(key)
    pending = execute(page)
    assert pending["action_state"] == "pending" and not pending["executed"]
    action = pending["action_id"]

    def count():
        with sqlite3.connect(database) as db:
            return db.execute(
                "SELECT COUNT(*) FROM tool_outbox WHERE action_id=?", (action,)
            ).fetchone()[0]

    assert count() == 0
    navigate("Approvals")
    card = page.locator("article.approval").filter(
        has=page.get_by_role("heading", name=action, exact=True)
    )
    expect(card).to_be_visible()
    assert json.loads(card.get_by_label("Exact immutable mail payload").inner_text()) == payload | {
        "idempotency_key": key
    }
    expect(card.get_by_role("button", name="Approve exact action")).to_be_disabled()
    card.get_by_role("checkbox").check()
    card.get_by_role("button", name="Approve exact action").click()
    expect(card).to_contain_text("Decision returned")
    assert count() == 0  # Approval alone is not execution.
    navigate("Playground")
    expect(page.get_by_label("Idempotency key", exact=True)).to_have_value(key)
    editor = page.get_by_label("Action payload · JSON")
    editor.fill(json.dumps(payload | {"subject": "Changed after review"}))
    conflict = execute(page)
    assert not conflict["executed"] and "IDEMPOTENCY_CONFLICT" in conflict["reason_codes"]
    assert count() == 0
    editor.fill(json.dumps(payload))
    delivered = execute(page)
    assert delivered["executed"] and delivered["result"]["delivery_state"] == "fixture"
    assert count() == 1
    retried = execute(page)
    assert retried["action_id"] == action and retried["executed"] and count() == 1
    navigate("Test outbox")
    expect(page.get_by_role("row").filter(has_text=action)).to_have_count(1)
    page.screenshot(path=str(artifacts / "outbox.png"), full_page=True)

    # Expire only the QA-owned playground tool authority, then use the real UI CAS renewal.
    before = api(page, "/admin/playground/credential?scope=tools")["data"]
    assert before["state"] == "active"
    with sqlite3.connect(database) as db:
        counters = db.execute("SELECT * FROM budget_counters ORDER BY scope,scope_key").fetchall()
        matches = [
            row
            for row in db.execute("SELECT digest,identity FROM credentials WHERE revoked=0")
            if json.loads(row[1])["principal_id"] == "operator-playground"
            and "mail.send" in json.loads(row[1])["operations"]
        ]
        assert len(matches) == 1
        digest, identity = matches[0]
        db.execute("UPDATE credentials SET expires_at=? WHERE digest=?", (time.time() - 1, digest))
    navigate("Playground")
    expect(page.get_by_role("button", name="Run governed action")).to_be_disabled()
    page.get_by_role("button", name="Renew expired credential").click()
    expect(page.get_by_role("button", name="Run governed action")).to_be_enabled()
    expect(page.get_by_text("Credential renewed.", exact=False)).to_be_visible()
    after = api(page, "/admin/playground/credential?scope=tools")["data"]
    assert after["state"] == "active" and after["epoch"] == before["epoch"] + 1
    with sqlite3.connect(database) as db:
        assert (
            db.execute("SELECT * FROM budget_counters ORDER BY scope,scope_key").fetchall()
            == counters
        )
        assert (
            db.execute("SELECT revoked FROM credentials WHERE digest=?", (digest,)).fetchone()[0]
            == 1
        )
        replacement = db.execute(
            "SELECT c.identity FROM credential_renewals r JOIN credentials c ON c.digest=r.new_digest WHERE r.old_digest=?",
            (digest,),
        ).fetchone()[0]
        assert replacement == identity
    page.get_by_role("button", name="Document", exact=True).click()
    page.get_by_label("Example preset").select_option(label="Read internal notes")
    assert execute(page)["executed"]
    return action


def observe_delivery(page, state, action, artifacts):
    until = time.monotonic() + 15
    while True:
        overview = api(page, "/admin/overview")["data"]
        delivery = overview["telemetry"]
        if delivery.get("source_lag_sequences") == 0 and delivery.get("pending_events") == 0:
            break
        assert time.monotonic() < until, "Audit sender did not drain within the QA deadline"
        page.wait_for_timeout(100)
    assert delivery["sender_running"] and delivery["target_kind"] == "local_contract_lab"
    assert delivery["acknowledged_events"] > 0 and delivery["last_delivery_ms"] >= 0
    latency = overview["latency"]
    assert latency["status"] == "measured" and latency["count"] > 0
    series = latency["series"]["operator_playground"]
    assert 0 <= series["p50_ms"] <= series["p95_ms"]
    with sqlite3.connect(state / "collector.sqlite3") as db:
        records = [json.loads(row[0]) for row in db.execute("SELECT record FROM received")]
    assert len(records) == delivery["acknowledged_events"]
    assert any(record["action_id"] == action and record["executed"] for record in records)
    minimized = json.dumps(records)
    assert "reviewer@demo.internal" not in minimized
    assert "Synthetic local outbox evidence" not in minimized
    (artifacts / "measured-overview.json").write_text(
        json.dumps(
            {
                "latency": latency,
                "delivery": delivery,
                "counts": overview["counts"],
                "collector_records": len(records),
                "mail_action_observed": True,
                "browser_scope": "real installed product; optional model evidence recorded separately",
            },
            indent=2,
        )
        + "\n"
    )


def model_generation(page, state, artifacts):
    """Optional real installed-provider check; never replaced by a mocked response."""

    def attempts():
        with sqlite3.connect(state / "agentgate.sqlite3") as db:
            return db.execute("SELECT COUNT(*) FROM model_attempts").fetchone()[0]

    page.get_by_role("button", name="Model", exact=True).click()
    page.get_by_label("Example preset").select_option(label="Input secret control")
    count = attempts()
    denied = execute(page)
    assert denied["decision"] == "deny" and not denied["executed"] and attempts() == count
    page.get_by_label("Example preset").select_option(label="Local summary")
    started = time.monotonic()
    result = execute(page)
    elapsed = (time.monotonic() - started) * 1000
    assert result["agentgate"]["executed"] and result["choices"][0]["message"]["content"].strip()
    assert attempts() == count + 1
    page.screenshot(path=str(artifacts / "model-generation.png"), full_page=True)
    (artifacts / "model-generation.json").write_text(
        json.dumps(
            {
                "input_secret_blocked_without_provider_attempt": True,
                "real_model_reply": True,
                "model": result["model"],
                "usage": result["usage"],
                "agentgate": result["agentgate"],
                "elapsed_ms": round(elapsed, 3),
                "reply_characters": len(result["choices"][0]["message"]["content"]),
                "provider_attempt_delta": attempts() - count,
            },
            indent=2,
        )
        + "\n"
    )
    page.get_by_role("button", name="Document", exact=True).click()
