"""Real operator-to-tool integration: no adapter stubs and exact side effects."""

from test_admin import admin as admin
from test_gateway import harness as harness

MAIL = {
    "mode": "mail",
    "recipient": "reviewer@demo.internal",
    "subject": "Reviewed quarterly notes",
    "body": "Synthetic local outbox message.",
    "idempotency_key": "full-stack-mail",
}


def play(admin, payload):
    return admin.client.post("/admin/playground", headers=admin.headers(), json=payload)


def approve(admin, action):
    return admin.client.post(
        f"/admin/approvals/{action['action_id']}/decision",
        headers=admin.headers(),
        json={"tenant_id": "tenant-a", "fingerprint": action["fingerprint"], "approve": True},
    )


def outbox(admin):
    return admin.client.get("/admin/outbox?tenant_id=tenant-a").json()["messages"]


def test_operator_exact_approval_consumes_once_and_reports_current_state(admin):
    admin.login()
    pending = play(admin, MAIL)
    assert pending.status_code == 202
    assert pending.json()["executed"] is False
    assert outbox(admin) == []
    assert admin.client.get("/admin/overview").json()["counts"]["pending"] == 1
    assert admin.client.get("/admin/approvals?tenant_id=tenant-b").json() == {"approvals": []}
    action = admin.client.get("/admin/approvals?tenant_id=tenant-a").json()["approvals"][0]
    assert action["payload"] == {k: v for k, v in MAIL.items() if k != "mode"}
    assert approve(admin, action).status_code == 202
    assert outbox(admin) == []  # Approval has no execution authority by itself.
    assert play(admin, MAIL | {"body": "changed after review"}).status_code == 409
    assert outbox(admin) == []
    sent = play(admin, MAIL)
    assert sent.status_code == 200
    assert sent.json()["executed"] is True
    assert sent.json()["result"]["delivery_state"] == "fixture"
    assert play(admin, MAIL).json()["result"] == sent.json()["result"]
    assert len(outbox(admin)) == 1
    overview = admin.client.get("/admin/overview").json()
    assert overview["counts"] == {"allow": 1, "deny": 1, "redact": 0, "pending": 0}
    assert "mail.send" in overview["coverage"]["enforced"]
    assert overview["coverage"]["mail_delivery"] == "local_outbox_fixture"
    events = [e for e in admin.gateway.store.events() if e.event_type == "action_completed"]
    assert len(events) == 1 and events[0].operation == "mail.send"


def test_live_feed_change_invalidates_approval_without_outbox_effect(admin):
    admin.login()
    assert play(admin, MAIL).status_code == 202
    action = admin.client.get("/admin/approvals?tenant_id=tenant-a").json()["approvals"][0]
    assert approve(admin, action).status_code == 202
    feed = admin.client.get("/admin/feed").json()
    changed = feed["feed"] | {
        "revision": 2,
        "indicators": [
            {
                "id": "deny-mail",
                "kind": "literal_text",
                "value": "Synthetic local",
                "stages": ["tool_action"],
            }
        ],
    }
    assert (
        admin.client.post(
            "/admin/feed",
            headers=admin.headers(),
            json={
                "feed": changed,
                "expected_version": feed["version"],
            },
        ).status_code
        == 200
    )
    denied = play(admin, MAIL)
    assert denied.status_code == 403
    assert denied.json()["executed"] is False
    assert outbox(admin) == []
    assert admin.gateway.store.budget_counters() == []


def test_operator_memory_filters_tenant_classification_and_feed(admin):
    admin.login()
    with admin.gateway.store.connection() as db:
        db.executemany(
            "INSERT INTO memory_entries VALUES (?,?,?,?)",
            [
                ("tenant-a", "ok", "internal", "quarterly contact reader@demo.internal"),
                ("tenant-a", "secret", "secret", "quarterly restricted"),
                ("tenant-b", "other", "internal", "quarterly other tenant"),
            ],
        )
    result = play(admin, {"mode": "memory", "query": "quarterly", "limit": 5})
    assert result.status_code == 200
    assert result.json()["decision"] == "redact"
    assert result.json()["result"]["entries"] == [
        {
            "entry_id": "ok",
            "content": "quarterly contact [REDACTED_EMAIL]",
        }
    ]
    assert "reader@" not in admin.client.get("/admin/events").text


def test_controls_changed_after_authentication_prevent_tool_dispatch(admin, monkeypatch):
    admin.login()
    service = admin.gateway.service
    original = service.tools.execute

    def changed(context, action):
        captured = service.context_controls(context)
        service.controls.activate_policy(
            captured.policy.model_copy(update={"revision": captured.policy.revision + 1}),
            captured.policy.version,
        )
        return original(context, action)

    monkeypatch.setattr(service.tools, "execute", changed)
    denied = play(admin, {"mode": "memory", "query": "quarterly", "limit": 5})
    assert denied.status_code == 409
    assert denied.json()["executed"] is False
    assert admin.gateway.store.budget_counters() == []
    assert not any(e.event_type == "dispatch_intent" for e in admin.gateway.store.events())
