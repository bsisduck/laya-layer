from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from pydantic import ValidationError

from agentgate.control_plane import (
    ArtifactMetadata,
    ControlConflict,
    ControlPlane,
    ControlSnapshot,
    Indicator,
    ThreatBlocked,
    ThreatFeed,
)
from agentgate.policy import Policy
from agentgate.storage import StorageUnavailable, Store


@pytest.fixture
def controls(tmp_path):
    store = Store(tmp_path / "state.sqlite3")
    store.initialize()
    controls = ControlPlane(store, clock=lambda: 1000.0)
    controls.initialize(Policy(policy_id="test", revision=1))
    return controls


def test_policy_activation_is_durable_and_replay_conflicts(controls):
    original = controls.snapshot()
    new = original.policy.model_copy(update={"revision": 2})
    changed = controls.activate_policy(new, "test:1")
    assert changed.generation == 2
    restarted = ControlPlane(Store(controls.store.path))
    restarted.initialize(original.policy)
    assert restarted.snapshot() == changed
    for policy, expected in [(new, "test:1"), (original.policy, "test:2")]:
        with pytest.raises(ControlConflict):
            controls.activate_policy(policy, expected)
    assert controls.snapshot() == changed
    assert controls.events() == [
        dict(sequence=1, timestamp=1000.0, kind="policy_activated", version="test:2", generation=2)
    ]
    assert original.policy.version == "test:1"


def test_invalid_policy_and_failed_audit_keep_last_good(controls):
    snapshot = controls.snapshot()
    with pytest.raises(ValidationError):
        controls.activate_policy(snapshot.policy.model_copy(update={"revision": -1}), "test:1")
    with controls.store.connection() as db:
        db.execute(
            "CREATE TRIGGER reject_activation BEFORE INSERT ON control_events "
            "BEGIN SELECT RAISE(ABORT, 'test failure'); END"
        )
    with pytest.raises(StorageUnavailable):
        controls.activate_policy(snapshot.policy.model_copy(update={"revision": 2}), "test:1")
    assert controls.snapshot() == snapshot


def test_competing_process_objects_compare_and_swap(controls):
    barrier = Barrier(2)

    def update(revision):
        other = ControlPlane(Store(controls.store.path))
        value = controls.snapshot().policy.model_copy(update={"revision": revision})
        barrier.wait()
        try:
            return other.activate_policy(value, "test:1")
        except ControlConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, (2, 3)))
    assert sum(result is not None for result in results) == 1
    assert len(controls.events()) == 1
    assert controls.snapshot().generation == 2


@pytest.mark.parametrize(
    "kind,value",
    [
        ("regex", ".*"),
        ("blocked_domain", "evil.invalid/path"),
        ("blocked_domain", "*.evil.invalid"),
        ("blocked_domain", "EVIL.invalid"),
        ("blocked_sha256", "x" * 64),
        ("blocked_source", "file:///tmp/evil.pkl"),
        ("blocked_source", "https://user:secret@evil.invalid/"),
        ("blocked_source", "https://evil.invalid/%2e%2e/"),
        ("literal_text", " "),
        ("literal_text", "x" * 513),
    ],
)
def test_reject_unsafe_matchers(kind, value):
    with pytest.raises(ValidationError):
        Indicator(id="deny", kind=kind, value=value)


def test_feed_limits_duplicate_ids_and_stage_validation():
    indicator = Indicator(id="deny", kind="literal_text", value="STOP")
    for indicators in [(indicator,) * 2, (indicator,) * 129]:
        with pytest.raises(ValidationError):
            ThreatFeed(indicators=indicators)
    with pytest.raises(ValidationError):
        Indicator(id="x", kind="literal_text", value="x", stages=("not-a-stage",))


@pytest.mark.parametrize("stage", ["tool_action", "tool_result", "model_input", "model_output"])
def test_callback_denies_actual_dispatch_or_release(stage):
    snapshot = ControlSnapshot(
        Policy(policy_id="test", revision=1),
        ThreatFeed(
            indicators=(
                Indicator(id="literal", kind="literal_text", value="STOP", stages=(stage,)),
            )
        ),
    )
    calls = []

    def executor(text):
        calls.append(text)
        return text

    if stage in ("tool_action", "model_input"):
        with pytest.raises(ThreatBlocked) as error:
            snapshot.inspect(stage, "STOP")
            executor("STOP")
        assert calls == []
    else:
        released = []
        with pytest.raises(ThreatBlocked) as error:
            output = executor("STOP")
            snapshot.inspect(stage, output)
            released.append(output)
        assert calls == ["STOP"]
        assert released == []
    assert error.value.indicator_ids == ("literal",)


def test_domain_source_digest_and_safe_artifact_metadata(controls):
    feed = ThreatFeed(
        revision=2,
        indicators=(
            Indicator(id="domain", kind="blocked_domain", value="evil.invalid"),
            Indicator(id="source", kind="blocked_source", value="https://models.invalid/bad"),
            Indicator(id="digest", kind="blocked_sha256", value="a" * 64),
        ),
    )
    snapshot = controls.activate_feed(feed, "local:1")
    for text in (
        "https://EVIL.invalid./file",
        "a@sub.evil.invalid",
        "evil.invalid",
        "https://models.invalid/bad",
        "a" * 64,
    ):
        with pytest.raises(ThreatBlocked):
            snapshot.inspect("model_input", text)
    for text in ("evil.invalid.safe.example", "not-evil.invalid", "https://models.invalid/good"):
        snapshot.inspect("model_input", text)
    safe = ArtifactMetadata(
        sha256="b" * 64, source="https://models.invalid/good", serialization="safetensors"
    )
    snapshot.inspect("artifact_intake", "", artifacts=(safe,))
    for artifact in (
        safe.model_copy(update={"sha256": "a" * 64}),
        safe.model_copy(update={"source": "https://models.invalid/bad"}),
        safe.model_copy(update={"source": "https://evil.invalid/"}),
        safe.model_copy(update={"serialization": "pickle"}),
    ):
        with pytest.raises(ThreatBlocked):
            snapshot.inspect("artifact_intake", "", artifacts=(artifact,))
    with pytest.raises(ControlConflict):
        controls.activate_feed(feed, "local:1")
    assert ControlPlane(controls.store).snapshot() == snapshot


def test_unsafe_serialization_never_executes_or_loads(tmp_path):
    # Deliberately no pickle fixture: the simulator receives metadata, not bytes.
    snapshot = ControlSnapshot(Policy(policy_id="test", revision=1), ThreatFeed())
    for serialization in ("pickle", "joblib", "torch_pickle"):
        with pytest.raises(ThreatBlocked) as error:
            snapshot.inspect(
                "artifact_intake",
                "",
                artifacts=(
                    ArtifactMetadata(
                        sha256="b" * 64,
                        source="https://untrusted.invalid/model",
                        serialization=serialization,
                    ),
                ),
            )
        assert error.value.indicator_ids == ("unsafe-serialization",)
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError):
        snapshot.inspect("model_output", "x" * 262145)


# These are HTTP/document integration tests, not model evaluation.
from test_gateway import Harness  # noqa: E402
from test_gateway import harness as harness  # noqa: E402


def attach_controls(harness: Harness):
    plane = ControlPlane(harness.store, harness.service.clock)
    plane.initialize(harness.service.policy)
    harness.service.controls = plane
    return plane


def test_feed_blocks_document_before_executor_and_budget(harness):
    plane = attach_controls(harness)
    plane.activate_feed(
        ThreatFeed(
            revision=2,
            indicators=(
                Indicator(
                    id="blocked-document",
                    kind="literal_text",
                    value="tenant-a-notes",
                    stages=("tool_action",),
                ),
            ),
        ),
        "local:1",
    )
    result = harness.read()
    assert result.status_code == 403
    assert result.json()["reason_codes"] == ["THREAT_FEED_BLOCKED"]
    assert harness.executor.calls == []
    assert harness.store.budget_counters() == []
    assert [e.event_type for e in harness.store.events()] == ["action_denied"]
    assert harness.store.events()[0].feed_version == "local:2"


def test_feed_withholds_document_output_after_execution(harness):
    plane = attach_controls(harness)
    plane.activate_feed(
        ThreatFeed(
            revision=2,
            indicators=(
                Indicator(
                    id="blocked-output",
                    kind="literal_text",
                    value="quarterly",
                    stages=("tool_result",),
                ),
            ),
        ),
        "local:1",
    )
    result = harness.read()
    assert result.status_code == 403
    assert result.json()["executed"] is True
    assert "result" not in result.json()
    assert harness.executor.calls == [("tenant-a-notes", "tenant-a")]
    assert [e.event_type for e in harness.store.events()] == ["dispatch_intent", "output_blocked"]


def test_policy_reload_between_decision_and_intent_reauthorizes(harness, monkeypatch):
    plane = attach_controls(harness)
    original = harness.store.dispatch_intent
    calls = []

    def activate_before_lock(*args):
        if not calls:
            current = plane.snapshot().policy
            plane.activate_policy(
                current.model_copy(
                    update={
                        "revision": 2,
                        "documents_read": current.documents_read.model_copy(update={"roles": ()}),
                    }
                ),
                "test:1",
            )
        calls.append(True)
        return original(*args)

    monkeypatch.setattr(harness.store, "dispatch_intent", activate_before_lock)
    result = harness.read()
    assert result.status_code == 403
    assert result.json()["policy_version"] == "test:2"
    assert harness.executor.calls == []
    assert harness.store.budget_counters() == []
    assert [e.event_type for e in harness.store.events()] == ["action_denied"]


def test_feed_reload_between_decision_and_intent_rechecks(harness, monkeypatch):
    plane = attach_controls(harness)
    original = harness.store.dispatch_intent

    def activate_before_lock(*args):
        plane.activate_feed(
            ThreatFeed(
                revision=2,
                indicators=(Indicator(id="block", kind="literal_text", value="tenant-a-notes"),),
            ),
            "local:1",
        )
        return original(*args)

    monkeypatch.setattr(harness.store, "dispatch_intent", activate_before_lock)
    assert harness.read().status_code == 403
    assert harness.executor.calls == []


def test_inflight_uses_dispatched_snapshot_then_next_action_uses_reload(harness, monkeypatch):
    plane = attach_controls(harness)
    original = harness.executor.read

    def read_with_activation(document_id, tenant_id):
        current = plane.snapshot().policy
        plane.activate_policy(
            current.model_copy(
                update={
                    "revision": 2,
                    "output": current.output.model_copy(update={"redact_emails": False}),
                }
            ),
            "test:1",
        )
        return original(document_id, tenant_id)

    monkeypatch.setattr(harness.executor, "read", read_with_activation)
    first = harness.read("tenant-a-contact").json()
    assert first["decision"] == "redact"
    assert first["policy_version"] == "test:1"
    monkeypatch.setattr(harness.executor, "read", original)
    second = harness.read("tenant-a-contact").json()
    assert second["decision"] == "allow"
    assert second["policy_version"] == "test:2"
    assert [e.policy_version for e in harness.store.events()] == [
        "test:1",
        "test:1",
        "test:2",
        "test:2",
    ]
