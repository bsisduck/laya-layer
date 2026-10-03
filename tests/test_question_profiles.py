"""Protocol fixtures only: these assert adapter behavior, not model quality."""

from types import SimpleNamespace

import pytest

from agentgate.inference_engine import PROFILES, QUESTIONS, evaluate
from agentgate.semantics import REVISIONS


@pytest.mark.parametrize(
    "version,choice,probabilities",
    [
        (
            "content-role-v1",
            "unclear",
            {"task_data": 0.1, "behavior_instruction": 0.2, "unclear": 0.7},
        ),
        ("content-role-v2", "A", {"A": 0.63, "B": 0.37}),
        ("content-role-v2", "B", {"A": 0.23, "B": 0.77}),
    ],
)
def test_exact_question_state_and_scores(version, choice, probabilities):
    profile = PROFILES[version]
    state = {"operation": "documents.read", profile.state_key: "Synthetic text"}
    observed = []

    def predict(actual_state, questions, **kwargs):
        assert actual_state == state and questions == profile.questions
        observed.append(True)
        return {
            "answers": {profile.key: {"choice": choice, "probabilities": probabilities}},
            "usage": {"truncated": False, "state_tokens_dropped": 0, "input_tokens": 99},
        }

    def build_sequence(tok, actual_state, question, *args, **kwargs):
        assert actual_state == state and question == profile.questions[profile.key]
        return (
            list(range(99)),
            list(profile.labels),
            {"options_distinct": len(profile.labels)},
            {"truncated": False},
        )

    model = SimpleNamespace(
        tok=SimpleNamespace(mask_token="[MASK]"),
        cfg={"head_max_len": 512},
        _to_internal=lambda q: q,
        predict=predict,
    )
    common = SimpleNamespace(build_sequence=build_sequence, serialize_state=lambda s: str(s))
    result = evaluate(
        model,
        common,
        {
            "request_id": "req-1",
            "operation": "documents.read",
            "untrusted_content": "Synthetic text",
            "question_set_id": version,
        },
        "laya_standard",
        REVISIONS["laya_standard"],
    )
    assert observed == [True]
    assert result["question_set_id"] == version
    assert result["raw_scores"] == {profile.labels[k]: v for k, v in probabilities.items()}
    assert result["selected_labels"] == {"content_role": profile.labels[choice]}
    assert result["status"] == ("abstain" if choice == "unclear" else "ok")


@pytest.mark.parametrize("version", list(PROFILES))
@pytest.mark.parametrize("collapsed,truncated", [(True, False), (False, True)])
def test_incomplete_preflight_never_calls_model(version, collapsed, truncated):
    profile = PROFILES[version]

    def predict(*args, **kwargs):
        pytest.fail("Incomplete content dispatched")

    count = len(profile.labels) - int(collapsed)
    model = SimpleNamespace(
        tok=SimpleNamespace(mask_token="[MASK]"),
        cfg={"head_max_len": 512},
        _to_internal=lambda q: q,
        predict=predict,
    )
    common = SimpleNamespace(
        build_sequence=lambda *a, **k: (
            [0],
            [0] * count,
            {"options_distinct": count},
            {"truncated": truncated},
        ),
        serialize_state=lambda s: str(s),
    )
    result = evaluate(
        model,
        common,
        {
            "request_id": "req-1",
            "operation": "documents.read",
            "untrusted_content": "Synthetic",
            "question_set_id": version,
        },
        "laya_standard",
        REVISIONS["laya_standard"],
    )
    assert result["status"] == "incomplete"
    assert result["selected_labels"] == result["raw_scores"] == {}
    assert result["coverage"]["windows_evaluated"] == 0


def test_v1_question_remains_unchanged():
    import json
    from pathlib import Path

    protocol = json.loads(
        (Path(__file__).resolve().parents[1] / "evaluation/protocol-v1.json").read_text()
    )
    assert QUESTIONS == protocol["questions"]
