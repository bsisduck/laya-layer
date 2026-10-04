"""Deterministic usage evidence with fixture providers; no real inference evaluation."""

import json
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient
from test_authority import authority as authority
from test_gateway import harness as harness
from test_models import model as model

from agentgate.app import create_app
from agentgate.authority import issue_child, provision_subject
from agentgate.contracts import Reason
from agentgate.control_plane import ControlPlane
from agentgate.department_usage import TrustedAttribution, report
from agentgate.model_budgets import ModelLedger
from agentgate.model_config import ModelPolicy, ResourceLimits
from agentgate.service import Context
from agentgate.storage import StorageUnavailable, Store, credential_digest


def projection(model, **changes):
    return report(model.store, **({"tenant": "tenant-a", "start": 999, "end": 1001} | changes))


def rows(store, table):
    assert table in {
        "model_attempts",
        "model_attribution",
        "model_settlement",
        "model_accounts",
        "model_reservations",
        "audit_events",
    }
    with store.connection() as db:
        return [dict(r) for r in db.execute(f"SELECT * FROM {table}")]


def test_distinct_usage_tariff_and_unassigned_known_denominators(model):
    limits = ResourceLimits(micro_usd=100000)
    model.limits(
        input_micro_usd=7,
        output_micro_usd=11,
        tenant_day=limits,
        principal_day=limits,
        root_run=limits,
    )
    assert model.call().status_code == 200
    data = projection(model)
    t = data["totals"]
    assert t["attempts"] == t["settled"] == t["known_usage_attempts"] == t["unassigned"] == 1
    assert t["unknown_usage_attempts"] == t["attributed"] == t["outstanding_calls"] == 0
    assert (t["known_input_tokens"], t["known_output_tokens"], t["known_simulated_micro_usd"]) == (
        20,
        3,
        "173",
    )
    assert (
        sum(r["spent"] for r in rows(model.store, "model_accounts") if r["resource"] == "micro_usd")
        == 3 * 173
    )
    assert data["departments"][0]["bucket"] == "unknown_unassigned"
    assert data["completeness"]["status"] == "complete"


def test_two_departments_share_parent_and_attribution_is_immutable(authority):
    h, parent, person, models, provider = authority

    def call(token):
        return h.client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer " + token},
            json={
                "model": "local-demo",
                "messages": [{"role": "user", "content": "Fixture provider request"}],
            },
        )

    assert call(h.token).status_code == 200
    second = person.model_copy(update={"subject_id": "second", "department": "Finance"})
    provision_subject(h.store, second)
    token = issue_child(h.store, parent, second.subject_id, h.service.policy, now=h.service.clock())
    assert call(token).status_code == 200
    provision_subject(
        h.store,
        person.model_copy(update={"department": "Changed", "revision": 2}),
        expected_revision=1,
    )
    assert call(h.token).status_code == 401
    data = report(h.store, "tenant-a", 999, 1001)
    assert data["totals"]["attempts"] == data["totals"]["attributed"] == 2
    assert {b["department"] for b in data["departments"]} == {"HR", "Finance"}
    assert data["totals"]["known_input_tokens"] == 40
    attrs = rows(h.store, "model_attribution")
    assert {r["accounting_principal"] for r in attrs} == {h.identity.principal_id}
    assert {json.loads(r["attribution"])["department"] for r in attrs} == {"HR", "Finance"}
    assert all("delegation_id" not in r["attribution"] for r in attrs)
    assert len(provider.calls) == 2


def test_new_versioned_trusted_issuer_is_minimized_without_local_assumption(model):
    assert model.call().status_code == 200
    attr = {
        "version": 2,
        "human_subject": "issuer-person",
        "department": "Research",
        "provenance": "verified_issuer",
        "subject_revision": 3,
        "issuer_id": "configured-issuer",
        "trust_version": 2,
        "raw_claims": {"email": "private@example.org"},
    }
    minimized = TrustedAttribution.model_validate(attr).model_dump_json(exclude_none=True)
    with model.store.connection() as db:
        db.execute("UPDATE model_attribution SET attribution=?", (minimized,))
    data = projection(model)
    assert data["departments"][0]["provenance"] == [
        {
            "source": "verified_issuer",
            "authority_version": 2,
            "issuer_id": "configured-issuer",
            "trust_version": 2,
        }
    ]
    assert "private@example.org" not in minimized and "human_subject" not in json.dumps(data)


def test_output_denied_after_provider_success_still_counts_actual(model):
    model.provider.content = "AGENTGATE_SECRET[fixture]"
    assert model.call().status_code == 403
    assert len(model.provider.calls) == 1
    t = projection(model)["totals"]
    assert t["attempts"] == t["settled"] == t["known_usage_attempts"] == 1
    assert t["known_input_tokens"] == 20 and t["known_output_tokens"] == 3
    assert model.store.events()[-1].event_type == "output_blocked"


def test_pre_reservation_denials_have_no_evidence_charge_or_provider(model):
    for changes in (
        {"model": "other"},
        {"department": "forged"},
        {"text": "AGENTGATE_SECRET[fixture]"},
    ):
        assert model.call(**changes).status_code in (403, 422)
    assert not model.provider.calls
    assert not rows(model.store, "model_attempts")
    assert not rows(model.store, "model_attribution")
    assert not rows(model.store, "model_settlement")
    assert not rows(model.store, "model_accounts")


def test_timeout_unknown_reservations_restart_and_later_reconciliation(model):
    model.provider.failure = httpx.ReadTimeout("fixture uncertain provider outcome")
    assert model.call().status_code == 503
    t = projection(model)["totals"]
    assert t["uncertain"] == t["unknown_usage_attempts"] == t["outstanding_calls"] == 1
    assert t["known_usage_attempts"] == 0 and t["outstanding_input_tokens"] > 0
    assert projection(model)["completeness"]["status"] == "partial_evidence"
    model.store.initialize()
    assert projection(model)["totals"] == t
    event = model.store.events()[-1].model_copy(
        update={"event_id": "evt-reconciled", "event_type": "action_completed"}
    )
    assert model.models.ledger.finish(event, (20, 3))
    assert projection(model)["totals"]["known_usage_attempts"] == 1
    before = rows(model.store, "model_accounts")
    with pytest.raises(StorageUnavailable):
        model.models.ledger.finish(event, (20, 3))
    assert rows(model.store, "model_accounts") == before
    assert len(rows(model.store, "model_settlement")) == 1


@pytest.mark.parametrize("failure", ["evidence", "audit", "account"])
def test_atomic_settlement_rollback_keeps_reservations_and_no_partial_actual(model, failure):
    original = model.provider.complete

    def fail(payload):
        value = original(payload)
        with model.store.connection() as db:
            statement = {
                "evidence": "CREATE TRIGGER fail_settlement BEFORE INSERT ON model_settlement BEGIN SELECT RAISE(ABORT,'fixture evidence failure'); END",
                "audit": "CREATE TRIGGER fail_terminal BEFORE INSERT ON audit_events WHEN json_extract(NEW.event,'$.event_type')!='dispatch_intent' BEGIN SELECT RAISE(ABORT,'fixture audit failure'); END",
                "account": "CREATE TRIGGER fail_account BEFORE UPDATE ON model_accounts BEGIN SELECT RAISE(ABORT,'fixture account failure'); END",
            }[failure]
            db.execute(statement)
        return value

    model.provider.complete = fail
    assert model.call().status_code == 503
    assert len(model.provider.calls) == 1
    assert rows(model.store, "model_attempts")[0]["state"] == "dispatched"
    assert len(rows(model.store, "model_attribution")) == 1
    assert not rows(model.store, "model_settlement")
    assert all(r["spent"] == 0 for r in rows(model.store, "model_accounts"))
    assert any(r["reserved"] > 0 for r in rows(model.store, "model_accounts"))
    assert [e.event_type for e in model.store.events()] == ["dispatch_intent"]


def test_atomic_attribution_failure_prevents_actual_provider_effect(model):
    with model.store.connection() as db:
        db.execute(
            "CREATE TRIGGER fail_attribution BEFORE INSERT ON model_attribution BEGIN SELECT RAISE(ABORT,'fixture attribution failure'); END"
        )
    assert model.call().status_code == 503
    assert not model.provider.calls
    assert not rows(model.store, "model_attempts") and not rows(model.store, "model_accounts")
    assert not any(e.event_type == "dispatch_intent" for e in model.store.events())


def test_max_tariff_overrun_and_exact_large_aggregate(model):
    limits = ResourceLimits(tokens=10**12, micro_usd=10**12)
    model.limits(output_micro_usd=10**12, tenant_day=limits, principal_day=limits, root_run=limits)
    model.provider.usage = {
        "prompt_tokens": 20,
        "completion_tokens": 10000000,
        "total_tokens": 10000020,
    }
    assert model.call(max_tokens=1).status_code == 503
    exact = 10000000 * 10**12
    settlement = rows(model.store, "model_settlement")[0]
    assert settlement["simulated_micro_usd"] == str(exact) and settlement["over_bound"] == 1
    assert all(r["frozen"] == 1 for r in model.models.ledger.counters())
    assert {r["spent"] for r in model.models.ledger.counters() if r["resource"] == "micro_usd"} == {
        str(exact)
    }
    assert model.call(max_tokens=1).status_code == 429 and len(model.provider.calls) == 1
    assert projection(model)["totals"]["known_simulated_micro_usd"] == str(exact)
    assert projection(model)["totals"]["over_bound_attempts"] == 1
    # Add independently keyed historical evidence to test Python aggregation past int64.
    with model.store.connection() as db:
        db.execute(
            "INSERT INTO model_attempts SELECT 'second',tenant_id,state,created_at,tariff_revision,input_bound,output_bound,input_tariff,output_tariff FROM model_attempts LIMIT 1"
        )
        db.execute(
            "INSERT INTO model_settlement SELECT 'second',version,input_tokens,output_tokens,simulated_micro_usd,over_bound FROM model_settlement LIMIT 1"
        )
    assert projection(model)["totals"]["known_simulated_micro_usd"] == str(2 * exact)


def test_overlarge_reservation_is_denied_before_sql_integer_binding(model):
    model.limits(input_micro_usd=10**12, output_micro_usd=10**12)
    assert model.call().status_code == 429
    assert not model.provider.calls and not rows(model.store, "model_attempts")


def test_two_pending_finishes_add_exactly_after_restart_without_unfreezing(model):
    limits = ResourceLimits(tokens=10**12, micro_usd=10**12)
    contexts = [
        Context(
            action_id=f"act-pending-{n}",
            trace_id=f"trace-{n}",
            identity=model.identity,
            operation="chat.completions",
        )
        for n in range(2)
    ]
    for context, tariff, bound in zip(contexts, (10**12, 7), (1, 0), strict=True):
        policy = ModelPolicy(
            max_concurrent=2,
            output_micro_usd=tariff,
            tenant_day=limits,
            principal_day=limits,
            root_run=limits,
        )
        model.models.ledger.reserve(
            credential_digest(model.token),
            model.identity,
            model.actions.event(context, "dispatch_intent", Reason.ALLOWED, "allow"),
            policy,
            0,
            bound,
            model.actions.clock,
        )

    def terminal(context):
        context.executed = True
        return model.actions.event(context, "output_blocked", Reason.USAGE_INVALID, "deny")

    assert not model.models.ledger.finish(terminal(contexts[0]), (0, 10000000))
    restarted = ModelLedger(Store(model.store.path))
    assert not restarted.finish(terminal(contexts[1]), (0, 3))
    exact = 10000000 * 10**12 + 21
    with model.store.connection() as db:
        money = db.execute(
            "SELECT spent,typeof(spent),frozen,reserved FROM model_accounts WHERE resource='micro_usd'"
        ).fetchall()
    assert all(tuple(r) == (f"exact:{exact}", "text", 1, 0) for r in money)
    assert all(r["frozen"] == 1 for r in restarted.counters())
    assert projection(model)["totals"]["known_simulated_micro_usd"] == str(exact)
    model.limits(tenant_day=limits, principal_day=limits, root_run=limits)
    assert model.call().status_code == 429 and not model.provider.calls


def test_counter_projection_preserves_above_js_safe_integer_without_storage_change(model):
    assert model.call().status_code == 200
    value = 2**53 + 1
    with model.store.connection() as db:
        db.execute(
            "UPDATE model_accounts SET spent=?,frozen=1 WHERE resource='micro_usd'", (value,)
        )
        assert {
            r[0]
            for r in db.execute(
                "SELECT typeof(spent) FROM model_accounts WHERE resource='micro_usd'"
            )
        } == {"integer"}
    assert {r["spent"] for r in model.models.ledger.counters() if r["resource"] == "micro_usd"} == {
        str(value)
    }


def test_historical_migration_preserves_legacy_rows_and_unavailable_evidence(model):
    assert model.call().status_code == 200
    before = rows(model.store, "model_accounts"), rows(model.store, "audit_events")
    with model.store.connection() as db:
        for table in ("model_attribution", "model_settlement", "model_usage_schema"):
            db.execute(f"DROP TABLE {table}")
    assert not model.store.ready()
    model.store.initialize()
    assert model.store.ready()
    assert (rows(model.store, "model_accounts"), rows(model.store, "audit_events")) == before
    t = projection(model)["totals"]
    assert (
        t["historical_attribution_unavailable"]
        == t["historical_usage_unavailable"]
        == t["unknown_usage_attempts"]
        == 1
    )
    assert t["known_usage_attempts"] == t["outstanding_calls"] == 0


def test_period_boundaries_exact_tenant_and_truncation(model, monkeypatch):
    assert model.call().status_code == 200
    assert projection(model, start=1000, end=1001)["totals"]["attempts"] == 1
    assert projection(model, start=999, end=1000)["totals"]["attempts"] == 0
    assert projection(model, tenant="tenant-b")["totals"]["attempts"] == 0
    for changes in (
        {"start": 1, "end": 31 * 86400 + 2},
        {"start": 1001},
        {"tenant": "tenant-a' OR 1=1"},
        {"departments": 65},
    ):
        with pytest.raises(ValueError):
            projection(model, **changes)
    monkeypatch.setattr("agentgate.department_usage.MAX_ATTEMPTS", 0)
    d = projection(model)
    assert d["completeness"]["attempts_truncated"] and d["totals"]["attempts"] == 0


def test_snapshot_is_coherent_during_concurrent_settlement(model, monkeypatch):
    model.provider.failure = httpx.ReadTimeout("fixture")
    assert model.call().status_code == 503
    connection = model.store.connection
    event = model.store.events()[-1].model_copy(update={"event_id": "evt-concurrent"})

    @contextmanager
    def reading():
        with connection() as db:

            def trace(sql):
                if sql.startswith("SELECT a.*"):
                    # Version read has pinned the WAL snapshot before the writer commits.
                    model.models.ledger.finish(event, (20, 3))

            db.set_trace_callback(trace)
            yield db

    # Writer uses a different Store so it doesn't inherit this trace callback.
    model.models.ledger.store = Store(model.store.path)
    monkeypatch.setattr(model.store, "connection", reading)
    t = projection(model)["totals"]
    assert t["uncertain"] == t["unknown_usage_attempts"] == 1 and t["known_usage_attempts"] == 0
    monkeypatch.setattr(model.store, "connection", connection)
    assert projection(model)["totals"]["settled"] == 1


def test_admin_report_requires_operator_and_bounds_inputs(model):
    controls = ControlPlane(model.store, model.actions.clock)
    controls.initialize(model.actions.policy)
    model.actions.controls = controls
    operator = "o" * 43
    with model.store.connection() as db:
        db.execute("INSERT INTO operator_credentials VALUES(1,?)", (credential_digest(operator),))
    origin = "http://127.0.0.1:8769"
    path = "/admin/department-usage?tenant_id=tenant-a&start=999&end=1001"
    with TestClient(
        create_app(model.actions, model.models, admin_origin=origin), base_url=origin
    ) as client:
        assert client.get(path).status_code == 401
        assert (
            client.get(path, headers={"Authorization": "Bearer " + model.token}).status_code == 401
        )
        assert (
            client.post(
                "/admin/session", headers={"Origin": origin}, json={"token": operator}
            ).status_code
            == 200
        )
        assert client.get(path).status_code == 200
        for suffix in ("&start=999", "&unknown=1", "&departments=65"):
            assert client.get(path + suffix).status_code == 422
        assert client.get("/admin/department-usage").status_code == 422
        assert client.get(path, headers={"Origin": "https://outside.invalid"}).status_code == 403
        assert client.get(path).headers["Cache-Control"] == "no-store"
