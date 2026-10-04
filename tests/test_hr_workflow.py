"""Deterministic HR product enforcement/rollback, not real-model evaluation."""

import json
import secrets
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from test_gateway import Harness
from test_gateway import harness as harness
from test_models import ObservedProvider
from test_semantics import FixtureEvaluator

from agentgate.app import create_app
from agentgate.authority import provision_subject
from agentgate.budgets import ToolBudgets
from agentgate.control_plane import ThreatFeed
from agentgate.hr_workflow import MAX_BINDINGS, PERSON, HRWorkflow
from agentgate.model_config import ModelPolicy
from agentgate.models import ModelService
from agentgate.storage import credential_digest

ORIGIN = "https://hr.test"


@pytest.fixture
def hr(harness: Harness):
    harness.service.policy = harness.service.policy.model_copy(
        update={
            "models": ModelPolicy(),
            "tool_budgets": ToolBudgets(tenant_day=1000, principal_day=500, root_run=100),
        }
    )
    provider = ObservedProvider(harness.store)
    provider.content = "Fixture provider summary; not real inference."
    models = ModelService(harness.service, provider)
    app = create_app(harness.service, models, admin_origin=ORIGIN)
    token = secrets.token_urlsafe(32)
    with harness.store.connection() as db:
        db.execute("INSERT INTO operator_credentials VALUES (1,?)", (credential_digest(token),))
    with TestClient(app, base_url=ORIGIN) as client:
        harness.client = client
        harness.operator_token = token
        harness.hr = app.state.hr_workflow
        harness.provider = provider
        login = client.post("/admin/session", headers={"Origin": ORIGIN}, json={"token": token})
        harness.csrf = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        yield harness


def post(h, path, data=None):
    return h.client.post("/admin/hr/" + path, headers=h.csrf, json=data or {})


def setup(h):
    preview = h.client.get("/admin/hr/setup-preview")
    assert preview.status_code == 200, preview.text
    p = preview.json()
    result = post(h, "setup", {k: p[k] for k in ("expected_generation", "preview_digest")})
    assert result.status_code == 200, result.text
    return p


def bind(h):
    result = post(h, "bind")
    assert result.status_code == 200, result.text
    return result.json()["handle"]


def read(h, handle, resource="hr-candidate-001", path="read"):
    return post(h, path, {"handle": handle, "resource": resource})


def proposal(h, handle, key="exact", **changes):
    return post(
        h,
        "propose",
        {
            "handle": handle,
            "proposal_key": key,
            "recipient": "candidate@demo.internal",
            "subject": "Synthetic follow-up",
            "body": "Exact synthetic invitation.",
        }
        | changes,
    )


def approve(h, action_id, approve=True):
    row = next(
        r
        for r in h.service.tools.list_approvals(tenant_id="tenant-a")
        if r["action_id"] == action_id
    )
    return h.client.post(
        "/admin/approvals/" + action_id + "/decision",
        headers=h.csrf,
        json={"tenant_id": "tenant-a", "fingerprint": row["fingerprint"], "approve": approve},
    )


def resume(h, handle, action_id):
    return post(h, "resume", {"handle": handle, "action_id": action_id})


def count(h, table):
    with h.store.connection() as db:
        return db.execute("SELECT count(*) FROM " + table).fetchone()[0]


def test_get_and_preview_are_read_only_and_preserve_active_controls(hr):
    before = {
        t: count(hr, t)
        for t in ("credentials", "human_subjects", "control_events", "budget_counters")
    }
    controls = hr.service.current_controls()
    feed = ThreatFeed(revision=2)
    hr.service.controls.activate_feed(feed, controls.feed.version)
    controls = hr.service.current_controls()
    for _ in range(3):
        assert hr.client.get("/admin/hr").json()["parent"]["state"] == "unissued"
        assert hr.client.get("/admin/hr/setup-preview").status_code == 200
    assert {t: count(hr, t) for t in before} == before | {
        "control_events": before["control_events"] + 1
    }
    p = setup(hr)
    after = hr.service.current_controls()
    assert after.feed == feed
    for key in (
        "semantic_required",
        "semantic_mode",
        "tool_budgets",
        "models",
        "ingress",
        "output",
    ):
        assert getattr(controls.policy, key) == getattr(after.policy, key)
    assert count(hr, "budget_counters") == before["budget_counters"]
    assert p["policy"]["delegation"]["version"] == 1
    assert hr.client.get("/admin/hr").json()["configured"]


def test_stale_feed_cas_and_mutated_preview_cannot_activate(hr):
    p = hr.client.get("/admin/hr/setup-preview").json()
    hr.service.controls.activate_feed(ThreatFeed(revision=2), "local:1")
    assert (
        post(hr, "setup", {k: p[k] for k in ("expected_generation", "preview_digest")}).status_code
        == 409
    )
    assert count(hr, "human_subjects") == 0
    assert (
        post(hr, "setup", {"expected_generation": 2, "preview_digest": "0" * 64}).status_code == 409
    )


def test_missing_setup_finite_inputs_csrf_and_no_asserted_authority(hr):
    assert post(hr, "bind").status_code == 409
    for path, body in [
        ("bind", {"roles": ["admin"]}),
        ("setup", {"policy": {}}),
        ("read", {"handle": "x" * 43, "resource": "/etc/passwd"}),
        ("read", {"handle": "x" * 43, "resource": "tenant-a-notes"}),
        ("read", {"handle": "x" * 43, "resource": "hr-candidate-001", "classification": "public"}),
    ]:
        assert post(hr, path, body).status_code == 422
    assert hr.client.post("/admin/hr/bind", headers={"Origin": ORIGIN}, json={}).status_code == 403
    setup(hr)
    handle = bind(hr)
    assert read(hr, "x" * 43).status_code == 410
    assert hr.executor.calls == []
    assert hr.provider.calls == []
    assert count(hr, "tool_outbox") == 0
    for binding in hr.hr.entries.values():
        assert binding.token not in hr.client.get("/admin/hr").text
        assert binding.token not in repr(binding)
        assert binding.token != handle
        for path in hr.store.path.parent.glob("audit.sqlite3*"):
            assert binding.token.encode() not in path.read_bytes()


def test_real_scoped_read_asymmetric_denials_and_parent_denial(hr):
    setup(hr)
    handle = bind(hr)
    assert read(hr, handle).json()["result"]["content"].startswith("Synthetic candidate")
    before = list(hr.executor.calls)
    for resource in ("hr-private-notes", "finance-record-001"):
        r = read(hr, handle, resource)
        assert r.status_code == 403 and not r.json()["executed"]
    assert hr.executor.calls == before
    assert hr.provider.calls == []
    assert count(hr, "tool_outbox") == 0
    parent = hr.hr.parent_token(0)
    for path, body in [
        (
            "/v1/actions/execute",
            {"operation": "documents.read", "arguments": {"document_id": "hr-candidate-001"}},
        ),
        (
            "/v1/actions/execute",
            {
                "operation": "mail.send",
                "arguments": {
                    "recipient": "candidate@demo.internal",
                    "subject": "Parent",
                    "body": "Parent",
                    "idempotency_key": "parent",
                },
            },
        ),
        (
            "/v1/chat/completions",
            {"model": "local-demo", "messages": [{"role": "user", "content": "Parent"}]},
        ),
    ]:
        r = hr.client.post(path, headers={"Authorization": "Bearer " + parent}, json=body)
        assert r.status_code == 403 and not r.json()["executed"]
    assert hr.executor.calls == before
    assert hr.provider.calls == [] and count(hr, "tool_outbox") == 0


def test_exact_approval_resume_replay_and_payload_conflict(hr):
    setup(hr)
    handle = bind(hr)
    p = proposal(hr, handle)
    assert p.status_code == 202 and not p.json()["executed"]
    action_id = p.json()["action_id"]
    assert count(hr, "tool_outbox") == 0
    assert approve(hr, action_id).status_code == 202
    assert count(hr, "tool_outbox") == 0
    assert proposal(hr, handle, body="Mutated").status_code == 409
    assert count(hr, "tool_outbox") == 0
    for _ in range(3):
        assert resume(hr, handle, action_id).status_code == 200
    assert count(hr, "tool_outbox") == 1
    events = [e for e in hr.store.events() if e.action_id == action_id]
    decided = next(e for e in events if e.event_type == "approval_decided")
    assert decided.authority["human_subject"] == PERSON.subject_id
    assert decided.authority["accounting_principal"] == "hr-demo-account"
    assert decided.approval_actor["actor_id"] == "operator"
    assert decided.authority["version"] == 1


@pytest.mark.parametrize("change", ["reject", "policy", "subject", "expiry"])
def test_consent_invalidity_has_zero_outbox_effect(hr, change):
    setup(hr)
    handle = bind(hr)
    action_id = proposal(hr, handle).json()["action_id"]
    approve(hr, action_id, approve=change != "reject")
    if change == "policy":
        p = hr.service.policy
        hr.service.controls.activate_policy(
            p.model_copy(update={"revision": p.revision + 1}), p.version
        )
    if change == "subject":
        provision_subject(
            hr.store, PERSON.model_copy(update={"revision": 2, "roles": ()}), expected_revision=1
        )
    if change == "expiry":
        hr.now[0] += 301
    r = resume(hr, handle, action_id)
    assert r.status_code in (403, 410)
    assert count(hr, "tool_outbox") == 0
    assert hr.provider.calls == []


def test_sessions_restart_expiry_and_deliberate_new_binding(hr):
    setup(hr)
    handle = bind(hr)
    original = hr.client.cookies.get("agentgate_operator")
    second = hr.client.post(
        "/admin/session", headers={"Origin": ORIGIN}, json={"token": hr.operator_token}
    ).json()
    hr.csrf = {"Origin": ORIGIN, "X-CSRF-Token": second["csrf_token"]}
    before = count(hr, "credentials")
    assert read(hr, handle).status_code == 410
    assert count(hr, "credentials") == before
    new = bind(hr)
    assert new != handle
    restarted = HRWorkflow(hr.service)
    assert restarted.entries == {}
    with pytest.raises(Exception, match="binding unavailable"):
        restarted.select(new, credential_digest(hr.client.cookies.get("agentgate_operator")))
    hr.now[0] += 301
    assert read(hr, new).status_code == 410
    assert count(hr, "credentials") == before + 1
    newer = bind(hr)
    assert newer not in (new, handle)
    assert count(hr, "delegated_bindings") == 1  # Old expired rows cleaned only on mutation.
    assert original not in json.dumps(hr.client.get("/admin/hr").json())


def test_issuance_rollback_map_and_audit_are_atomic(hr, monkeypatch):
    setup(hr)
    before = {t: count(hr, t) for t in ("credentials", "delegated_bindings", "control_events")}
    with hr.store.connection() as db:
        db.execute(
            "CREATE TRIGGER fail_hr_child BEFORE INSERT ON delegated_bindings BEGIN SELECT RAISE(ABORT,'fault'); END"
        )
    assert post(hr, "bind").status_code == 503
    assert hr.hr.entries == {}
    assert {t: count(hr, t) for t in before} == before
    with hr.store.connection() as db:
        db.execute("DROP TRIGGER fail_hr_child")
    bind(hr)


def test_setup_partial_failure_leaves_require_delegation_inert_retryable(hr):
    with hr.store.connection() as db:
        db.execute(
            "CREATE TRIGGER fail_person BEFORE INSERT ON human_subjects BEGIN SELECT RAISE(ABORT,'fault'); END"
        )
    p = hr.client.get("/admin/hr/setup-preview").json()
    assert (
        post(hr, "setup", {k: p[k] for k in ("expected_generation", "preview_digest")}).status_code
        == 503
    )
    assert count(hr, "human_subjects") == 0 and count(hr, "delegated_bindings") == 0
    assert hr.service.policy.delegation.required[0].agent_id == "hr-assistant"
    assert post(hr, "bind").status_code == 409
    with hr.store.connection() as db:
        db.execute("DROP TRIGGER fail_person")
    setup(hr)
    bind(hr)


def test_fresh_summary_source_and_untrusted_role_provider_failure(hr):
    setup(hr)
    handle = bind(hr)
    r = read(hr, handle, path="summary")
    assert r.status_code == 200, r.text
    assert r.json()["completion"]["choices"][0]["message"]["content"].startswith("Fixture")
    assert len(hr.executor.calls) == len(hr.provider.calls) == 1
    assert hr.provider.calls[0]["messages"][-1]["role"] == "tool"
    with hr.store.connection() as db:
        attribution = db.execute("SELECT * FROM model_attribution").fetchone()
        assert attribution["accounting_principal"] == "hr-demo-account"
        assert json.loads(attribution["attribution"]) == {
            "version": 1,
            "human_subject": PERSON.subject_id,
            "department": "HR",
            "provenance": "local_demo",
            "subject_revision": PERSON.revision,
        }
        assert db.execute("SELECT count(*) FROM model_settlement").fetchone()[0] == 1
    before = len(hr.executor.calls)
    read(hr, handle, path="summary")
    assert len(hr.executor.calls) == before + 1
    hr.provider.raw = b"not json"
    failed = read(hr, handle, path="summary")
    assert failed.status_code == 503 and failed.json()["decision"] == "deny"
    assert "completion" not in failed.json()
    assert count(hr, "model_attempts") == 3


def test_summary_source_authority_changed_before_model_dispatch(hr, monkeypatch):
    setup(hr)
    handle = bind(hr)
    original = hr.hr.execute

    def changed(*args, **kwargs):
        r = original(*args, **kwargs)
        p = hr.service.policy
        hr.service.controls.activate_policy(
            p.model_copy(update={"revision": p.revision + 1}), p.version
        )
        return r

    monkeypatch.setattr(hr.hr, "execute", changed)
    assert read(hr, handle, path="summary").status_code == 409
    assert hr.provider.calls == [] and count(hr, "model_attempts") == 0


def test_semantic_failure_and_injection_are_actual_core_outcomes(hr):
    setup(hr)
    handle = bind(hr)
    # No semantic configured: injection is actually released, never a scenario-ID deny.
    assert read(hr, handle, "hr-cv-injection-001").status_code == 200
    p = hr.service.policy
    hr.service.controls.activate_policy(
        p.model_copy(update={"revision": p.revision + 1, "semantic_required": True}), p.version
    )
    hr.service.semantic = FixtureEvaluator(label="behavior_instruction")
    r = read(hr, handle, "hr-cv-injection-001", path="summary")
    assert r.status_code == 403 and r.json()["reason_codes"] == ["SEMANTIC_BLOCKED"]
    assert hr.provider.calls == []
    hr.service.semantic = None
    before = len(hr.executor.calls)
    r = read(hr, handle, path="summary")
    assert r.status_code == 503 and r.json()["reason_codes"] == ["REQUIRED_SEMANTIC_UNAVAILABLE"]
    assert len(hr.executor.calls) == before and hr.provider.calls == []


def test_parent_renewal_is_explicit_and_keeps_fixed_accounting(hr):
    setup(hr)
    handle = bind(hr)
    assert post(hr, "parent/renew", {"expected_epoch": 0}).status_code == 409
    hr.now[0] += 86401
    assert read(hr, handle).status_code == 401
    assert hr.client.get("/admin/hr").status_code == 401  # Separate operator expiry.
    session = hr.client.post(
        "/admin/session", headers={"Origin": ORIGIN}, json={"token": hr.operator_token}
    ).json()
    hr.csrf = {"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]}
    assert hr.client.get("/admin/hr").json()["parent"]["state"] == "expired"
    assert post(hr, "bind").status_code == 410
    assert post(hr, "parent/renew", {"expected_epoch": 0}).status_code == 200
    assert post(hr, "parent/renew", {"expected_epoch": 0}).status_code == 409
    newer = bind(hr)
    assert newer != handle
    assert read(hr, newer).status_code == 200
    with hr.store.connection() as db:
        rows = db.execute(
            "SELECT identity FROM credentials WHERE json_extract(identity,'$.principal_id')='hr-demo-account'"
        ).fetchall()
    assert len({r[0] for r in rows}) == 1


def test_conflicting_revoked_subject_and_incompatible_controls_not_overwritten(hr):
    provision_subject(hr.store, PERSON.model_copy(update={"revoked": True}))
    assert hr.client.get("/admin/hr/setup-preview").status_code == 409
    assert post(hr, "bind").status_code == 409
    assert hr.client.get("/admin/hr").json()["incompatibility"]
    with hr.store.connection() as db:
        assert json.loads(db.execute("SELECT record FROM human_subjects").fetchone()[0])["revoked"]


def test_capacity_across_private_map_and_restart_is_bounded(hr):
    setup(hr)
    sessions = []
    with hr.store.connection() as db:
        op = db.execute("SELECT digest FROM operator_credentials").fetchone()[0]
        for i in range(MAX_BINDINGS + 1):
            session = credential_digest("capacity-" + str(i))
            db.execute("INSERT INTO operator_sessions VALUES (?,?,?)", (session, op, 1800.0))
            sessions.append(session)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(hr.hr.bind, sessions[:MAX_BINDINGS]))
    assert len(results) == len(hr.hr.entries) == count(hr, "delegated_bindings") == MAX_BINDINGS
    with pytest.raises(Exception, match="capacity"):
        hr.hr.bind(sessions[-1])
    restarted = HRWorkflow(hr.service)
    with pytest.raises(Exception, match="capacity"):
        restarted.bind(sessions[-1])
    assert count(hr, "delegated_bindings") == MAX_BINDINGS


@pytest.mark.parametrize("stage", ["admission", "reservation", "subject", "feed"])
def test_summary_guard_after_consumer_check_and_transaction_has_zero_provider_attempts(
    hr, monkeypatch, stage
):
    setup(hr)
    handle = bind(hr)
    models = hr.client.app.state.models

    def narrow():
        controls = hr.service.current_controls()
        if stage == "subject":
            provision_subject(
                hr.store,
                PERSON.model_copy(update={"revision": 2, "roles": ()}),
                expected_revision=1,
            )
        elif stage == "feed":
            hr.service.controls.activate_feed(ThreatFeed(revision=2), controls.feed.version)
        else:
            delegation = controls.policy.delegation
            human = next(p for p in delegation.profiles if p.role_id == "HR-BP")
            # Remove only document authority; preserve chat, identity, budgets and all other roles.
            changed = human.model_copy(
                update={"grants": tuple(g for g in human.grants if g.operation != "documents.read")}
            )
            policy = controls.policy.model_copy(
                update={
                    "revision": controls.policy.revision + 1,
                    "delegation": delegation.model_copy(
                        update={
                            "profiles": tuple(
                                changed if p.role_id == "HR-BP" else p for p in delegation.profiles
                            )
                        }
                    ),
                }
            )
            hr.service.controls.activate_policy(policy, controls.policy.version)

    if stage == "admission":
        complete = models.complete

        def before_complete(*args, **kwargs):
            narrow()
            return complete(*args, **kwargs)

        monkeypatch.setattr(models, "complete", before_complete)
    else:
        reserve = models.ledger.reserve

        def before_reservation(*args, **kwargs):
            narrow()
            return reserve(*args, **kwargs)

        monkeypatch.setattr(models.ledger, "reserve", before_reservation)
    result = read(hr, handle, path="summary")
    assert result.status_code in (401, 409), result.text
    assert result.json()["executed"] is False
    assert hr.provider.calls == []
    assert (
        count(hr, "model_attempts")
        == count(hr, "model_reservations")
        == count(hr, "model_attribution")
        == count(hr, "model_settlement")
        == count(hr, "tool_outbox")
        == 0
    )
    assert len(hr.executor.calls) == 1  # Actual released read under the original controls.


def test_two_live_sessions_cannot_use_each_others_handles_or_approvals(hr):
    setup(hr)
    first = bind(hr)
    action_id = proposal(hr, first).json()["action_id"]
    with TestClient(hr.client.app, base_url=ORIGIN) as second:
        session = second.post(
            "/admin/session", headers={"Origin": ORIGIN}, json={"token": hr.operator_token}
        ).json()
        headers = {"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]}
        other = second.post("/admin/hr/bind", headers=headers, json={}).json()["handle"]
        assert (
            second.post(
                "/admin/hr/read",
                headers=headers,
                json={"handle": first, "resource": "hr-candidate-001"},
            ).status_code
            == 410
        )
        assert read(hr, other).status_code == 410
        assert (
            second.post(
                "/admin/hr/resume", headers=headers, json={"handle": other, "action_id": action_id}
            ).status_code
            == 404
        )
        assert read(hr, first).status_code == 200
        assert count(hr, "tool_outbox") == 0


def test_delayed_issuance_uses_clock_inside_transaction(hr, monkeypatch):
    setup(hr)
    original = hr.hr.event

    def delay(db, kind, snapshot):
        if kind == "hr_child_issued_local_v1":
            hr.now[0] += 120
        return original(db, kind, snapshot)

    monkeypatch.setattr(hr.hr, "event", delay)
    h = bind(hr)
    assert hr.hr.entries[h].expires == hr.now[0] + 300
    assert read(hr, h).status_code == 200


def test_end_expiry_after_selection_returns_unavailable_without_mutation(hr, monkeypatch):
    setup(hr)
    handle = bind(hr)
    original = hr.hr.select
    before = count(hr, "control_events")

    def expire(selected, session):
        binding = original(selected, session)
        hr.now[0] += 301
        return binding

    monkeypatch.setattr(hr.hr, "select", expire)
    assert post(hr, "end", {"handle": handle}).status_code == 410
    assert count(hr, "control_events") == before
    assert handle in hr.hr.entries
    with hr.store.connection() as db:
        assert (
            db.execute(
                "SELECT revoked FROM credentials WHERE digest=?",
                (credential_digest(hr.hr.entries[handle].token),),
            ).fetchone()[0]
            == 0
        )
    assert count(hr, "tool_outbox") == 0


def test_explicit_rebinding_invalidates_previous_consent_without_transfer(hr):
    setup(hr)
    old = bind(hr)
    action_id = proposal(hr, old).json()["action_id"]
    approve(hr, action_id)
    newer = bind(hr)
    assert old != newer and len(hr.hr.entries) == 1
    assert read(hr, old).status_code == 410
    assert resume(hr, newer, action_id).status_code == 404
    assert count(hr, "tool_outbox") == 0
    with hr.store.connection() as db:
        assert (
            db.execute(
                "SELECT revoked FROM credentials WHERE digest=(SELECT child_digest FROM delegated_bindings ORDER BY rowid LIMIT 1)"
            ).fetchone()[0]
            == 1
        )


def test_setup_retains_live_observe_semantics_feed_unrelated_grants_and_spend(hr):
    from agentgate.authority_contracts import DelegationPolicy, RoleProfile
    from agentgate.control_plane import Indicator

    worker = FixtureEvaluator()
    worker.question_set_id = "fixture-profile-retained"
    hr.service.semantic = worker
    initial = hr.service.current_controls()
    policy = initial.policy.model_copy(
        update={
            "revision": initial.policy.revision + 1,
            "semantic_required": True,
            "semantic_mode": "observe",
            "delegation": DelegationPolicy(profiles=(RoleProfile(role_id="unrelated-reader"),)),
        }
    )
    hr.service.controls.activate_policy(policy, initial.policy.version)
    hr.service.controls.activate_feed(
        ThreatFeed(
            revision=2,
            indicators=(
                Indicator(id="unrelated-feed", kind="literal_text", value="UNRELATED_ONLY"),
            ),
        ),
        initial.feed.version,
    )
    with hr.store.connection() as db:
        db.execute(
            "INSERT INTO budget_counters(scope,scope_key,reserved,spent) VALUES (?, ?, 0, 7)",
            ("root_run", json.dumps(["tenant-a", "preserved-run"])),
        )
    before = hr.service.current_controls()
    setup(hr)
    after = hr.service.current_controls()
    assert after.policy.semantic_required and after.policy.semantic_mode == "observe"
    assert after.feed == before.feed and after.policy.models == before.policy.models
    assert after.policy.tool_budgets == before.policy.tool_budgets
    assert after.policy.delegation.profiles[0].role_id == "unrelated-reader"
    assert hr.service.semantic is worker and worker.question_set_id == "fixture-profile-retained"
    assert hr.store.budget_counters()[0]["spent"] == 7


def test_setup_unavailable_required_semantics_cannot_activate_or_issue(hr):
    p = hr.service.policy
    hr.service.controls.activate_policy(
        p.model_copy(update={"revision": p.revision + 1, "semantic_required": True}), p.version
    )
    preview = hr.client.get("/admin/hr/setup-preview").json()
    before = hr.service.current_controls()
    response = post(hr, "setup", {k: preview[k] for k in ("expected_generation", "preview_digest")})
    assert response.status_code == 503
    assert hr.service.current_controls() == before and count(hr, "human_subjects") == 0
    assert hr.hr.entries == {}


@pytest.mark.parametrize("control", ["domain", "classification"])
def test_incompatible_global_controls_are_retained_without_broadening(hr, control):
    p = hr.service.policy
    change = (
        {
            "scoped_tools": p.scoped_tools.model_copy(
                update={"mail_domains": ("elsewhere.internal",)}
            )
        }
        if control == "domain"
        else {
            "documents_read": p.documents_read.model_copy(update={"classifications": ("public",)})
        }
    )
    hr.service.controls.activate_policy(
        p.model_copy(update={"revision": p.revision + 1} | change), p.version
    )
    before = hr.service.current_controls()
    assert hr.client.get("/admin/hr/setup-preview").status_code == 409
    assert hr.client.get("/admin/hr").json()["incompatibility"]
    assert hr.service.current_controls() == before and count(hr, "human_subjects") == 0


def test_proposals_are_bounded_and_missing_provider_never_fabricates_summary(hr):
    setup(hr)
    handle = bind(hr)
    for i in range(16):
        assert proposal(hr, handle, key="p" + str(i)).status_code == 202
    assert proposal(hr, handle, key="extra").status_code == 429
    assert count(hr, "tool_outbox") == 0
    hr.client.app.state.models = None
    r = read(hr, handle, path="summary")
    assert r.status_code == 503 and "no summary generated" in r.json()["detail"]
    assert hr.provider.calls == [] and count(hr, "model_attempts") == 0
